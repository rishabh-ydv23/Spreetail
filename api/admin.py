from django.contrib import admin

from .models import (
    Expense,
    ExpenseParticipant,
    Group,
    GroupMember,
    ImportBatch,
    ImportIssue,
    ImportRow,
    Settlement,
    User,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'full_name', 'is_active', 'is_staff')
    search_fields = ('email', 'username', 'full_name')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'currency', 'created_by', 'created_at')
    search_fields = ('name',)


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ('group', 'user', 'join_date', 'leave_date', 'role')
    list_filter = ('group', 'role')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('description', 'group', 'payer', 'total_amount', 'date', 'split_type')
    list_filter = ('group', 'date', 'split_type')


@admin.register(ExpenseParticipant)
class ExpenseParticipantAdmin(admin.ModelAdmin):
    list_display = ('expense', 'user', 'amount', 'percentage')
    list_filter = ('expense__group',)


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ('group', 'payer', 'payee', 'amount', 'date')
    list_filter = ('group', 'date')


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ('source_file_name', 'group', 'status', 'total_rows', 'valid_rows', 'issue_count')
    list_filter = ('status',)


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = ('import_batch', 'row_number', 'status')
    list_filter = ('status',)


@admin.register(ImportIssue)
class ImportIssueAdmin(admin.ModelAdmin):
    list_display = ('import_batch', 'rule_code', 'severity', 'requires_approval', 'resolved')
    list_filter = ('severity', 'requires_approval', 'resolved')
