from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    Expense,
    ExpenseParticipant,
    GroupMember,
    ImportBatch,
    ImportIssue,
    ImportRow,
    Settlement,
)


class ExpenseService:
    SCALE = Decimal('0.01')

    @staticmethod
    def validate_participants(group_id, date, participants):
        user_ids = [participant['user'].id for participant in participants]
        active_members = GroupMember.objects.filter(
            group_id=group_id,
            user_id__in=user_ids,
            join_date__lte=date,
        ).filter(Q(leave_date__gte=date) | Q(leave_date__isnull=True))
        if active_members.count() != len(user_ids):
            raise ValueError('All participants must be active group members for the expense date.')

    @staticmethod
    def quantize_amount(value: Decimal) -> Decimal:
        return value.quantize(ExpenseService.SCALE, rounding=ROUND_HALF_UP)

    @classmethod
    def apply_split(cls, expense: Expense, participants_data):
        split_type = expense.split_type
        total_amount = expense.total_amount
        participants = []

        if split_type == 'equal':
            count = len(participants_data)
            share = cls.quantize_amount(total_amount / Decimal(count))
            remainder = total_amount - share * count
            for index, data in enumerate(participants_data):
                amount = share + (cls.quantize_amount(remainder) if index == 0 else Decimal('0.00'))
                participants.append({**data, 'amount': amount})
        elif split_type == 'exact':
            participants = participants_data
        elif split_type == 'percentage':
            total_allocated = Decimal('0.00')
            for index, data in enumerate(participants_data):
                amount = cls.quantize_amount(total_amount * data['percentage'] / Decimal('100'))
                if index == len(participants_data) - 1:
                    amount = total_amount - total_allocated
                participants.append({**data, 'amount': amount})
                total_allocated += amount
        return participants


class BalanceService:
    @staticmethod
    def compute_member_balances(group_id):
        expenses = Expense.objects.filter(group_id=group_id)
        settlements = Settlement.objects.filter(group_id=group_id)

        paid = expenses.values('payer').annotate(total_paid=Sum('total_amount'))
        owed = ExpenseParticipant.objects.filter(expense__group_id=group_id).values('user').annotate(total_owed=Sum('amount'))
        settled = settlements.values('payer').annotate(total_paid=Sum('amount'))
        received = settlements.values('payee').annotate(total_received=Sum('amount'))

        balances = defaultdict(lambda: Decimal('0'))
        for item in paid:
            balances[item['payer']] += item['total_paid']
        for item in owed:
            balances[item['user']] -= item['total_owed']
        for item in settled:
            balances[item['payer']] -= item['total_paid']
        for item in received:
            balances[item['payee']] += item['total_received']

        return balances

    @staticmethod
    def simplified_settlements(net_balances):
        debtors = []
        creditors = []
        for user_id, balance in net_balances.items():
            if balance < 0:
                debtors.append((user_id, -balance))
            elif balance > 0:
                creditors.append((user_id, balance))

        debtors.sort(key=lambda x: x[1])
        creditors.sort(key=lambda x: x[1])

        settlements = []
        i = j = 0
        while i < len(debtors) and j < len(creditors):
            debtor_id, debt_amount = debtors[i]
            creditor_id, credit_amount = creditors[j]
            amount = min(debt_amount, credit_amount)
            settlements.append({
                'from_user_id': debtor_id,
                'to_user_id': creditor_id,
                'amount': amount,
            })
            debt_amount -= amount
            credit_amount -= amount
            if debt_amount == 0:
                i += 1
            else:
                debtors[i] = (debtor_id, debt_amount)
            if credit_amount == 0:
                j += 1
            else:
                creditors[j] = (creditor_id, credit_amount)
        return settlements


class ImportService:
    @staticmethod
    @transaction.atomic
    def create_batch(group, imported_by, source_file_name, raw_csv_sha256):
        return ImportBatch.objects.create(
            group=group,
            imported_by=imported_by,
            source_file_name=source_file_name,
            raw_csv_sha256=raw_csv_sha256,
            status='pending',
        )

    @staticmethod
    @transaction.atomic
    def add_row(import_batch, row_number, raw_data):
        return ImportRow.objects.create(
            import_batch=import_batch,
            row_number=row_number,
            raw_data=raw_data,
            status='pending',
        )

    @staticmethod
    def report_issue(import_batch, import_row, rule_code, severity, description, recommendation, requires_approval):
        return ImportIssue.objects.create(
            import_batch=import_batch,
            import_row=import_row,
            rule_code=rule_code,
            severity=severity,
            description=description,
            recommendation=recommendation,
            requires_approval=requires_approval,
        )


class CSVImportService:
    REQUIRED_COLUMNS = [
        'payer',
        'date',
        'total_amount',
        'currency',
        'split_type',
        'participants',
    ]

    @staticmethod
    def checksum_content(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def parse_csv_rows(content: bytes) -> list[dict]:
        decoded = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
        rows = []
        for row_number, row in enumerate(reader, start=1):
            rows.append({'row_number': row_number, 'raw_data': {k: v.strip() for k, v in row.items()}})
        return rows

    @staticmethod
    def normalize_participants(value: str) -> list[dict]:
        if not value:
            return []
        try:
            participants = json.loads(value)
            if isinstance(participants, list):
                return participants
        except json.JSONDecodeError:
            pass
        segments = [segment.strip() for segment in value.split(';') if segment.strip()]
        parsed = []
        for segment in segments:
            if ':' in segment:
                identifier, fraction = segment.split(':', 1)
                parsed.append({'identifier': identifier.strip(), 'value': fraction.strip()})
        return parsed

    @staticmethod
    def resolve_user_id(group, identifier: str):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if '@' in identifier:
            return User.objects.filter(email__iexact=identifier).values_list('id', flat=True).first()
        return User.objects.filter(username__iexact=identifier).values_list('id', flat=True).first()

    @classmethod
    def parse_row_data(cls, row: dict, group):
        errors = []
        parsed = {}

        payer_identifier = row.get('payer')
        if not payer_identifier:
            errors.append(('missing_payer', 'high', 'Missing payer', 'Provide a payer value.', True))
        else:
            payer_id = cls.resolve_user_id(group, payer_identifier)
            if not payer_id:
                errors.append(('unknown_member', 'high', 'Unknown payer', f'Could not resolve payer {payer_identifier}.', True))
            parsed['payer_id'] = payer_id

        if not row.get('description'):
            row['description'] = 'Imported expense'
        parsed['description'] = row['description']
        parsed['category'] = row.get('category', '')

        date_value = row.get('date')
        try:
            parsed['date'] = timezone.datetime.fromisoformat(date_value).date() if date_value else None
        except (TypeError, ValueError):
            errors.append(('invalid_date', 'high', 'Invalid date', f'Expense date is invalid: {date_value}', True))
            parsed['date'] = None

        try:
            parsed['total_amount'] = Decimal(row.get('total_amount', '0'))
            if parsed['total_amount'] <= 0:
                errors.append(('negative_amount', 'high', 'Negative or zero amount', 'Expense total must be greater than zero.', True))
        except ArithmeticError:
            errors.append(('invalid_amount', 'high', 'Invalid amount', f'Unable to parse total amount: {row.get("total_amount")}', True))
            parsed['total_amount'] = Decimal('0')

        parsed['currency'] = row.get('currency', '')
        if parsed['currency'] != group.currency:
            errors.append(('currency_mismatch', 'medium', 'Currency mismatch', f'Expected {group.currency}, got {parsed["currency"]}.', True))

        split_type = row.get('split_type', '').lower()
        if split_type not in {'equal', 'exact', 'percentage'}:
            errors.append(('invalid_split', 'high', 'Invalid split type', f'Unknown split type: {split_type}', True))
        parsed['split_type'] = split_type

        participants_raw = row.get('participants', '')
        participants = cls.normalize_participants(participants_raw)
        normalized = []
        for participant in participants:
            identifier = participant.get('user_email') or participant.get('username') or participant.get('user_id') or participant.get('identifier')
            if not identifier:
                continue
            user_id = cls.resolve_user_id(group, identifier)
            if not user_id:
                errors.append(('unknown_member', 'medium', 'Unknown participant', f'Could not resolve participant {identifier}.', True))
                continue
            amount = participant.get('amount')
            percentage = participant.get('percentage')
            fallback_value = participant.get('value')
            if fallback_value is not None:
                if split_type == 'percentage':
                    percentage = fallback_value
                else:
                    amount = fallback_value
            if amount is not None:
                try:
                    amount = Decimal(str(amount))
                except ArithmeticError:
                    amount = None
            if percentage is not None:
                try:
                    percentage = Decimal(str(percentage))
                except ArithmeticError:
                    percentage = None
            normalized.append({'user_id': user_id, 'amount': amount, 'percentage': percentage})
        parsed['participants'] = normalized

        if split_type == 'exact':
            total = sum((item['amount'] or Decimal('0')) for item in normalized)
            if total != parsed['total_amount']:
                errors.append(('amount_mismatch', 'medium', 'Amount mismatch', 'Exact participant amounts do not match total.', True))
        elif split_type == 'percentage':
            percent_total = sum((item['percentage'] or Decimal('0')) for item in normalized)
            if percent_total != Decimal('100'):
                errors.append(('invalid_split', 'medium', 'Percentage mismatch', 'Participant percentages do not sum to 100.', True))

        if not parsed['category']:
            errors.append(('missing_category', 'low', 'Missing category', 'Category is recommended for expense classification.', False))

        parsed['source_reference'] = row.get('source_reference', '')
        return parsed, errors

    @classmethod
    def create_import_batch(cls, group, imported_by, source_file_name, raw_content):
        raw_csv_sha256 = cls.checksum_content(raw_content)
        batch = ImportService.create_batch(group, imported_by, source_file_name, raw_csv_sha256)
        rows = cls.parse_csv_rows(raw_content)
        issues_count = 0
        valid_rows = 0

        for row in rows:
            import_row = ImportService.add_row(batch, row['row_number'], row['raw_data'])
            parsed_data, issues = cls.parse_row_data(row['raw_data'], group)
            import_row.parsed_data = parsed_data
            import_row.status = 'valid' if not issues else 'anomaly'
            import_row.save()
            if not issues:
                valid_rows += 1
            else:
                issues_count += len(issues)
                for rule_code, severity, description, recommendation, approval in issues:
                    ImportService.report_issue(
                        batch,
                        import_row,
                        rule_code,
                        severity,
                        description,
                        recommendation,
                        approval,
                    )
        batch.total_rows = len(rows)
        batch.valid_rows = valid_rows
        batch.issue_count = issues_count
        batch.status = 'needs_review' if issues_count else 'completed'
        batch.completed_at = timezone.now()
        batch.save()
        return batch

    @staticmethod
    def commit_batch(batch, approve_all: bool = False):
        unresolved = batch.issues.filter(resolved=False, requires_approval=True).exists()
        if unresolved and not approve_all:
            raise ValueError('Batch has unresolved approval-required issues.')

        for row in batch.rows.filter(status='valid'):
            parsed = row.parsed_data
            if not parsed:
                continue
            expense = Expense.objects.create(
                group=batch.group,
                payer_id=parsed['payer_id'],
                description=parsed['description'],
                category=parsed['category'],
                total_amount=parsed['total_amount'],
                currency=parsed['currency'],
                date=parsed['date'],
                split_type=parsed['split_type'],
                source_reference=parsed['source_reference'],
                created_by=batch.imported_by,
            )
            for part in parsed['participants']:
                ExpenseParticipant.objects.create(
                    expense=expense,
                    user_id=part['user_id'],
                    amount=part['amount'] or Decimal('0'),
                    percentage=part['percentage'],
                )
        batch.status = 'completed'
        batch.completed_at = timezone.now()
        batch.save()
        return batch
