from __future__ import annotations

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
