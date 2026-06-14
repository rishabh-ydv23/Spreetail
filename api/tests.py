from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Expense, ExpenseParticipant, Group, GroupMember, Settlement
from .services import BalanceService, CSVImportService

User = get_user_model()


class ExpenseModelTest(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(email='aisha@example.com', username='aisha', password='testpass')
        self.user_b = User.objects.create_user(email='rohan@example.com', username='rohan', password='testpass')
        self.group = Group.objects.create(name='Friends', currency='INR', created_by=self.user_a)
        GroupMember.objects.create(group=self.group, user=self.user_a, join_date='2026-01-01')
        GroupMember.objects.create(group=self.group, user=self.user_b, join_date='2026-01-01')

    def test_equal_expense_participants_balance(self):
        expense = Expense.objects.create(
            group=self.group,
            payer=self.user_a,
            description='Dinner',
            total_amount=Decimal('1000.00'),
            currency='INR',
            date='2026-06-14',
            split_type='equal',
            created_by=self.user_a,
        )
        ExpenseParticipant.objects.create(expense=expense, user=self.user_a, amount=Decimal('500.00'))
        ExpenseParticipant.objects.create(expense=expense, user=self.user_b, amount=Decimal('500.00'))

        balances = BalanceService.compute_member_balances(self.group.id)
        self.assertEqual(balances[self.user_a.id], Decimal('500.00'))
        self.assertEqual(balances[self.user_b.id], Decimal('-500.00'))

    def test_settlement_adjusts_balances(self):
        expense = Expense.objects.create(
            group=self.group,
            payer=self.user_a,
            description='Taxi',
            total_amount=Decimal('600.00'),
            currency='INR',
            date='2026-06-14',
            split_type='equal',
            created_by=self.user_a,
        )
        ExpenseParticipant.objects.create(expense=expense, user=self.user_a, amount=Decimal('300.00'))
        ExpenseParticipant.objects.create(expense=expense, user=self.user_b, amount=Decimal('300.00'))
        Settlement.objects.create(
            group=self.group,
            payer=self.user_b,
            payee=self.user_a,
            amount=Decimal('300.00'),
            currency='INR',
            date='2026-06-15',
            created_by=self.user_b,
        )

        balances = BalanceService.compute_member_balances(self.group.id)
        self.assertEqual(balances[self.user_a.id], Decimal('600.00'))
        self.assertEqual(balances[self.user_b.id], Decimal('-600.00'))


class BalanceServiceTest(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(email='aisha@example.com', username='aisha', password='testpass')
        self.user_b = User.objects.create_user(email='rohan@example.com', username='rohan', password='testpass')
        self.user_c = User.objects.create_user(email='priya@example.com', username='priya', password='testpass')
        self.group = Group.objects.create(name='Trip', currency='INR', created_by=self.user_a)
        GroupMember.objects.create(group=self.group, user=self.user_a, join_date='2026-01-01')
        GroupMember.objects.create(group=self.group, user=self.user_b, join_date='2026-01-01')
        GroupMember.objects.create(group=self.group, user=self.user_c, join_date='2026-01-01')

    def test_simplified_settlements_generates_minimal_transactions(self):
        balances = {
            self.user_a.id: Decimal('300.00'),
            self.user_b.id: Decimal('-100.00'),
            self.user_c.id: Decimal('-200.00'),
        }
        settlements = BalanceService.simplified_settlements(balances)
        self.assertEqual(len(settlements), 2)
        self.assertEqual(settlements[0]['amount'], Decimal('100.00'))
        self.assertEqual(settlements[1]['amount'], Decimal('200.00'))


class CSVImportServiceTest(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(email='aisha@example.com', username='aisha', password='testpass')
        self.user_b = User.objects.create_user(email='rohan@example.com', username='rohan', password='testpass')
        self.group = Group.objects.create(name='Trip', currency='INR', created_by=self.user_a)
        GroupMember.objects.create(group=self.group, user=self.user_a, join_date='2026-01-01')
        GroupMember.objects.create(group=self.group, user=self.user_b, join_date='2026-01-01')

    def test_create_import_batch_with_valid_csv(self):
        csv_content = (
            'payer,date,total_amount,currency,split_type,participants,description,category,source_reference\n'
            'aisha,2026-06-14,1000.00,INR,equal,aisha:500;rohan:500,Dinner,Food,import-1\n'
        ).encode('utf-8')
        batch = CSVImportService.create_import_batch(
            group=self.group,
            imported_by=self.user_a,
            source_file_name='expenses.csv',
            raw_content=csv_content,
        )

        self.assertEqual(batch.total_rows, 1)
        self.assertEqual(batch.valid_rows, 1)
        self.assertEqual(batch.issue_count, 0)
        self.assertEqual(batch.status, 'completed')

    def test_create_import_batch_with_invalid_member(self):
        csv_content = (
            'payer,date,total_amount,currency,split_type,participants,description,category,source_reference\n'
            'aisha,2026-06-14,1000.00,INR,equal,unknown:500;rohan:500,Dinner,Food,import-2\n'
        ).encode('utf-8')
        batch = CSVImportService.create_import_batch(
            group=self.group,
            imported_by=self.user_a,
            source_file_name='errors.csv',
            raw_content=csv_content,
        )

        self.assertEqual(batch.total_rows, 1)
        self.assertEqual(batch.valid_rows, 0)
        self.assertGreater(batch.issue_count, 0)
        self.assertEqual(batch.status, 'needs_review')
