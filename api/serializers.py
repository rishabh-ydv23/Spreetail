from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from rest_framework import serializers

from .models import (
    Expense,
    ExpenseParticipant,
    Group,
    GroupMember,
    ImportBatch,
    ImportIssue,
    ImportRow,
    Settlement,
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'full_name', 'is_active']
        read_only_fields = ['id', 'is_active']


class GroupSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'currency', 'created_by', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class GroupMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(source='user', queryset=User.objects.all())
    username = serializers.CharField(source='user.username', read_only=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = GroupMember
        fields = ['id', 'group', 'user_id', 'username', 'full_name', 'join_date', 'leave_date', 'role', 'created_at']
        read_only_fields = ['id', 'group', 'username', 'full_name', 'created_at']

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        join_date = attrs.get('join_date', getattr(self.instance, 'join_date', None))
        leave_date = attrs.get('leave_date', getattr(self.instance, 'leave_date', None))
        user = attrs.get('user', getattr(self.instance, 'user', None))
        group_id = self.context.get('view').kwargs.get('group_pk') if self.context.get('view') else None

        if leave_date is not None and leave_date < join_date:
            raise serializers.ValidationError('leave_date must be the same as or later than join_date.')

        if group_id and user:
            overlap = GroupMember.objects.filter(
                group_id=group_id,
                user=user,
            ).exclude(pk=getattr(self.instance, 'pk', None)).filter(
                join_date__lte=leave_date or join_date,
                leave_date__gte=join_date,
            )
            if overlap.exists():
                raise serializers.ValidationError('The member has overlapping membership periods within the group.')

        return attrs


class ExpenseParticipantSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(source='user', queryset=User.objects.all())
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ExpenseParticipant
        fields = ['id', 'expense', 'user_id', 'username', 'amount', 'percentage', 'created_at']
        read_only_fields = ['id', 'expense', 'username', 'created_at']

    def validate_amount(self, value: Decimal) -> Decimal:
        if value < 0:
            raise serializers.ValidationError('Participant amount must be non-negative.')
        return value

    def validate_percentage(self, value: Decimal | None) -> Decimal | None:
        if value is not None and not (Decimal('0') <= value <= Decimal('100')):
            raise serializers.ValidationError('Percentage must be between 0 and 100.')
        return value


class ExpenseSerializer(serializers.ModelSerializer):
    payer_id = serializers.PrimaryKeyRelatedField(source='payer', queryset=User.objects.all())
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    participants = ExpenseParticipantSerializer(many=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'group',
            'payer_id',
            'description',
            'category',
            'total_amount',
            'currency',
            'date',
            'split_type',
            'source_reference',
            'created_by',
            'created_at',
            'updated_at',
            'participants',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def validate_date(self, value: date) -> date:
        if value > date.today():
            raise serializers.ValidationError('Expense date cannot be in the future.')
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        split_type = attrs.get('split_type', getattr(self.instance, 'split_type', None))
        participants = attrs.get('participants')
        total_amount = attrs.get('total_amount', getattr(self.instance, 'total_amount', None))
        group = attrs.get('group', getattr(self.instance, 'group', None))
        currency = attrs.get('currency', getattr(self.instance, 'currency', None))

        if participants is None or len(participants) == 0:
            raise serializers.ValidationError('At least one participant must be provided.')

        if group is not None and currency is not None and currency != group.currency:
            raise serializers.ValidationError('Currency must match the group currency.')

        if split_type == 'exact':
            total = sum(item['amount'] for item in participants)
            if total != total_amount:
                raise serializers.ValidationError('Exact split amounts must sum to the total amount.')
        elif split_type == 'percentage':
            total_percent = sum(item['percentage'] for item in participants if item.get('percentage') is not None)
            if total_percent != Decimal('100'):
                raise serializers.ValidationError('Percentage split values must sum to 100.')

        group_id = self.context.get('view').kwargs.get('group_pk') if self.context.get('view') else None
        if group_id and participants and attrs.get('date'):
            user_ids = [participant['user'].id for participant in participants]
            active_members = GroupMember.objects.filter(
                group_id=group_id,
                user_id__in=user_ids,
                join_date__lte=attrs['date'],
            ).filter(Q(leave_date__gte=attrs['date']) | Q(leave_date__isnull=True))
            if active_members.count() != len(user_ids):
                raise serializers.ValidationError('All participants must be active members on the expense date.')
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Expense:
        participants_data = validated_data.pop('participants')
        expense = Expense.objects.create(**validated_data)
        for participant_data in participants_data:
            ExpenseParticipant.objects.create(expense=expense, **participant_data)
        return expense

    def update(self, instance: Expense, validated_data: dict[str, Any]) -> Expense:
        participants_data = validated_data.pop('participants', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if participants_data is not None:
            instance.participants.all().delete()
            for participant_data in participants_data:
                ExpenseParticipant.objects.create(expense=instance, **participant_data)
        return instance


class SettlementSerializer(serializers.ModelSerializer):
    payer_id = serializers.PrimaryKeyRelatedField(source='payer', queryset=User.objects.all())
    payee_id = serializers.PrimaryKeyRelatedField(source='payee', queryset=User.objects.all())
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Settlement
        fields = [
            'id',
            'group',
            'payer_id',
            'payee_id',
            'amount',
            'currency',
            'date',
            'note',
            'created_by',
            'created_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        payer = attrs.get('payer')
        payee = attrs.get('payee')
        if payer and payee and payer == payee:
            raise serializers.ValidationError('payer_id and payee_id must be different.')
        return attrs


class ImportRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRow
        fields = ['id', 'import_batch', 'row_number', 'raw_data', 'parsed_data', 'status', 'created_at']
        read_only_fields = ['id', 'parsed_data', 'status', 'created_at']


class ImportIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportIssue
        fields = [
            'id',
            'import_batch',
            'import_row',
            'rule_code',
            'severity',
            'description',
            'recommendation',
            'requires_approval',
            'resolved',
            'created_at',
            'resolved_at',
        ]
        read_only_fields = ['id', 'created_at', 'resolved_at']


class ImportBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportBatch
        fields = [
            'id',
            'group',
            'imported_by',
            'source_file_name',
            'status',
            'total_rows',
            'valid_rows',
            'issue_count',
            'raw_csv_sha256',
            'created_at',
            'completed_at',
        ]
        read_only_fields = ['id', 'imported_by', 'status', 'valid_rows', 'issue_count', 'created_at', 'completed_at']
