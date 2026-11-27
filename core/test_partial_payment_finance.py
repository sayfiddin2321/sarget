from datetime import date, datetime, time
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Expense, Group, Payment, Receptionist, ReceptionistSalary, Salary, Student, Teacher
from .accounts import student_accounts


@override_settings(TELEGRAM_BOT_TOKEN='', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PartialPaymentFinanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('partial-admin', password='test')
        cls.teacher = Teacher.objects.create(name='Teacher', percent=40)
        cls.group = Group.objects.create(name='Course', teacher=cls.teacher, monthly_fee=490000,
                                        start_time=time(9), end_time=time(10))
        cls.student = Student.objects.create(name='Student', teacher=cls.teacher, group=cls.group,
                                            registration_date=date(2026, 11, 1))

    def setUp(self):
        self.client.force_login(self.admin)

    def payment(self, amount=480000, **kwargs):
        return Payment.objects.create(
            student=self.student, amount=amount, month=date(2026, 11, 1),
            paid_date=timezone.make_aware(datetime(2026, 11, 20, 10)), **kwargs,
        )

    def reports(self):
        with patch('core.views.timezone.localdate', return_value=date(2026, 11, 20)):
            return self.client.get(reverse('dashboard')), self.client.get(reverse('reports'))

    def test_480000_of_490000_immediately_earns_salary_and_leaves_debt(self):
        self.payment(is_partial=True)
        salary = Salary.objects.get(teacher=self.teacher, month=date(2026, 11, 1))
        self.assertEqual(salary.total_income, Decimal('480000'))
        self.assertEqual(salary.salary_amount, Decimal('192000'))
        self.assertEqual(sum(row['balance'] for row in student_accounts(self.student, date(2026, 11, 20))), Decimal('10000'))
        response = self.client.get(reverse('salary_list'))
        self.assertEqual(response.context['total_unpaid'], Decimal('192000'))
        dashboard, report = self.reports()
        self.assertEqual(dashboard.context['monthly_income'], Decimal('480000'))
        self.assertEqual(dashboard.context['monthly_expenses'], Decimal('192000'))
        self.assertEqual(dashboard.context['net_income'], Decimal('288000'))
        november = next(row for row in report.context['monthly_income'] if row['month'] == '2026-11')
        self.assertEqual(november['net'], 288000)
        self.assertEqual(report.context['total_expense_year'], Decimal('192000'))
        self.payment(amount=10000)
        salary.refresh_from_db()
        self.assertEqual(salary.total_income, Decimal('490000'))
        self.assertEqual(salary.salary_amount, Decimal('196000'))
        self.assertEqual(sum(row['balance'] for row in student_accounts(self.student, date(2026, 11, 20))), 0)
        self.assertEqual(Salary.objects.count(), 1)

    def assert_partial_form_updates_student_card(self, enrollment=''):
        with patch('core.views.timezone.localdate', return_value=date(2026, 11, 20)):
            response = self.client.post(reverse('payment_create'), {
                'student': self.student.pk, 'enrollment': enrollment,
                'amount': '480000', 'month': '2026-11',
                'paid_date': '2026-11-20T10:00', 'payment_type': 'cash',
            })
            self.assertEqual(response.status_code, 302)
            detail = self.client.get(reverse('student_detail', args=[self.student.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context['total_paid'], Decimal('480000'))
        self.assertEqual(detail.context['debt_amount'], Decimal('10000'))
        self.assertEqual(detail.context['debt_months'], 1)
        self.assertEqual(detail.context['debt_breakdown'][0]['paid'], Decimal('480000'))
        self.assertEqual(detail.context['debt_breakdown'][0]['amount'], Decimal('10000'))

    def test_partial_payment_form_reduces_student_card_debt(self):
        self.assert_partial_form_updates_student_card()

    def test_partial_payment_for_primary_enrollment_reduces_same_card_debt(self):
        enrollment = self.student.enrollments.get(is_primary=True)
        self.assert_partial_form_updates_student_card(enrollment.pk)

    def test_calculation_and_paid_toggle_do_not_duplicate_expenses(self):
        self.payment()
        Expense.objects.create(title='Rent', amount=10000, date=date(2026, 11, 5))
        receptionist = Receptionist.objects.create(name='Reception')
        ReceptionistSalary.objects.create(receptionist=receptionist, month=date(2026, 11, 1), total_salary=20000)
        Expense.objects.create(title='Past year', amount=999999, date=date(2025, 11, 5))
        Expense.objects.create(title='January rent', amount=5000, date=date(2026, 1, 5))
        for _ in range(2):
            self.client.post(reverse('calculate_salaries'), {'month': '2026-11'})
        for paid in (False, True, False):
            salary = Salary.objects.get(teacher=self.teacher)
            if salary.is_paid != paid:
                self.client.post(reverse('update_salary_status', args=[salary.pk]))
            dashboard, report = self.reports()
            self.assertEqual(dashboard.context['monthly_expenses'], 222000)
            self.assertEqual(dashboard.context['net_income'], 258000)
            self.assertEqual(dashboard.context['chart_data'][-1]['expense'], 222000)
            self.assertEqual(report.context['total_expense_year'], 227000)

    def test_edit_and_void_update_profit_and_keep_other_collections(self):
        payment = self.payment(is_partial=True)
        self.payment(amount=5000)
        payment.amount = 470000
        payment.save()
        self.assertEqual(self.reports()[0].context['net_income'], 285000)
        payment.void('Duplicate')
        salary = Salary.objects.get(teacher=self.teacher)
        self.assertEqual(salary.total_income, 5000)
        self.assertEqual(salary.salary_amount, 2000)
        self.assertEqual(self.reports()[0].context['net_income'], 3000)

    def test_backfill_repairs_missing_and_stale_rows_but_preserves_paid_rows(self):
        self.payment()
        Salary.objects.all().delete()
        state = MigrationExecutor(connection).loader.project_state([('core', '0021_student_deleted_at')])
        migration = import_module('core.migrations.0022_backfill_teacher_payroll')
        editor = SimpleNamespace(connection=connection)
        migration.backfill_teacher_payroll(state.apps, editor)
        salary = Salary.objects.get(teacher=self.teacher)
        self.assertEqual(salary.salary_amount, 192000)
        Salary.objects.filter(pk=salary.pk).update(salary_amount=0)
        migration.backfill_teacher_payroll(state.apps, editor)
        salary.refresh_from_db()
        self.assertEqual(salary.salary_amount, 192000)
        Salary.objects.filter(pk=salary.pk).update(is_paid=True, salary_amount=123)
        migration.backfill_teacher_payroll(state.apps, editor)
        salary.refresh_from_db()
        self.assertTrue(salary.is_paid)
        self.assertEqual(salary.salary_amount, 123)
        self.assertEqual(Salary.objects.count(), 1)

    def test_historical_import_and_unassigned_payment_do_not_create_teacher_payroll(self):
        self.payment(is_historical_migration=True)
        self.student.teacher = None
        self.student.group = None
        self.student.save()
        self.payment()
        self.assertFalse(Salary.objects.exists())
