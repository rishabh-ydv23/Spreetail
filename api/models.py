import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


def currency_code_validator():
    return RegexValidator(
        regex=r'^[A-Z]{3}$',
        message='Currency must be a 3-letter ISO code.',
    )


class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        if not username:
            raise ValueError('Username is required')
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(email, username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self) -> str:
        return self.username


class Group(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    currency = models.CharField(max_length=3, validators=[currency_code_validator()])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='created_groups')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['created_by']),
        ]

    def __str__(self) -> str:
        return self.name


class GroupMember(models.Model):
    MEMBER_ROLE_CHOICES = [
        ('member', 'Member'),
        ('admin', 'Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='group_memberships')
    join_date = models.DateField()
    leave_date = models.DateField(blank=True, null=True)
    role = models.CharField(max_length=16, choices=MEMBER_ROLE_CHOICES, default='member')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['group', 'user']),
            models.Index(fields=['group']),
        ]
        constraints = [
            models.CheckConstraint(check=Q(leave_date__gte=models.F('join_date')) | Q(leave_date__isnull=True), name='groupmember_leave_after_join'),
            models.UniqueConstraint(fields=['group', 'user', 'join_date'], name='unique_group_user_join_date'),
        ]

    def __str__(self) -> str:
        return f'{self.user} @ {self.group} from {self.join_date}'


class Expense(models.Model):
    SPLIT_TYPE_CHOICES = [
        ('equal', 'Equal'),
        ('exact', 'Exact'),
        ('percentage', 'Percentage'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='expenses')
    payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='paid_expenses')
    description = models.TextField()
    category = models.CharField(max_length=120, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(max_length=3, validators=[currency_code_validator()])
    date = models.DateField()
    split_type = models.CharField(max_length=16, choices=SPLIT_TYPE_CHOICES)
    source_reference = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='created_expenses')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['group', 'date']),
            models.Index(fields=['payer']),
            models.Index(fields=['source_reference']),
        ]

    def __str__(self) -> str:
        return f'{self.description} ({self.total_amount} {self.currency})'


class ExpenseParticipant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='expense_participations')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['expense']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['expense', 'user'], name='unique_participant_per_expense'),
            models.CheckConstraint(check=Q(amount__gte=0), name='participant_non_negative_amount'),
            models.CheckConstraint(check=Q(percentage__gte=0) & Q(percentage__lte=100) | Q(percentage__isnull=True), name='participant_percentage_range'),
        ]

    def __str__(self) -> str:
        return f'{self.user} share for {self.expense}'


class Settlement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='settlements')
    payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='settlement_payments')
    payee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='settlement_receipts')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(max_length=3, validators=[currency_code_validator()])
    date = models.DateField()
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='created_settlements')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['group', 'date']),
            models.Index(fields=['payer', 'payee']),
        ]
        constraints = [
            models.CheckConstraint(check=~Q(payer=models.F('payee')), name='settlement_payer_not_payee'),
        ]

    def __str__(self) -> str:
        return f'{self.payer} -> {self.payee} {self.amount} {self.currency}'


class ImportBatch(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('needs_review', 'Needs Review'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='import_batches')
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='import_batches')
    source_file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending')
    total_rows = models.IntegerField(default=0)
    valid_rows = models.IntegerField(default=0)
    issue_count = models.IntegerField(default=0)
    raw_csv_sha256 = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['imported_by']),
        ]

    def __str__(self) -> str:
        return f'Import {self.source_file_name} ({self.status})'


class ImportRow(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('valid', 'Valid'),
        ('anomaly', 'Anomaly'),
        ('skipped', 'Skipped'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='rows')
    row_number = models.IntegerField()
    raw_data = models.JSONField()
    parsed_data = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [('import_batch', 'row_number')]
        indexes = [
            models.Index(fields=['import_batch', 'status']),
        ]

    def __str__(self) -> str:
        return f'Row {self.row_number} in {self.import_batch}'


class ImportIssue(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    RULE_CHOICES = [
        ('duplicate_expense', 'Duplicate expense'),
        ('negative_amount', 'Negative amount'),
        ('missing_payer', 'Missing payer'),
        ('invalid_date', 'Invalid date'),
        ('settlement_logged_as_expense', 'Settlement logged as expense'),
        ('currency_mismatch', 'Currency mismatch'),
        ('unknown_member', 'Unknown member'),
        ('inactive_member', 'Inactive member'),
        ('amount_mismatch', 'Amount mismatch'),
        ('invalid_split', 'Invalid split'),
        ('duplicate_transaction', 'Duplicate transaction'),
        ('missing_category', 'Missing category'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='issues')
    import_row = models.ForeignKey(ImportRow, on_delete=models.SET_NULL, related_name='issues', blank=True, null=True)
    rule_code = models.CharField(max_length=64, choices=RULE_CHOICES)
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES)
    description = models.TextField()
    recommendation = models.TextField()
    requires_approval = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['import_batch', 'rule_code']),
            models.Index(fields=['import_batch', 'severity']),
        ]

    def __str__(self) -> str:
        return f'{self.rule_code} in {self.import_batch}'
