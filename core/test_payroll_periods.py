from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Payment, Receptionist, ReceptionistCommission, ReceptionistSalary, Salary, Student, Teacher


@override_settings(TELEGRAM_BOT_TOKEN='', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], TIME_ZONE='Asia/Tashkent')
class PayrollPeriodTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('payroll-admin', password='test-pass')
        cls.teacher = Teacher.objects.create(name='Teacher', percent=40)
        cls.rec = Receptionist.objects.create(name='Reception', commission_percent=10)
        cls.student = Student.objects.create(name='Student', teacher=cls.teacher, receptionist=cls.rec)

    def setUp(self):
        self.client.force_login(self.admin)

    def payment(self, service, paid, amount=600000):
        return Payment.objects.create(
            student=self.student, month=date.fromisoformat(service + '-01'), amount=amount,
            paid_date=timezone.make_aware(datetime.fromisoformat(paid)),
        )

    def calculate(self, month):
        self.assertEqual(self.client.post(reverse('calculate_salaries'), {'month': month}).status_code, 302)
        self.assertEqual(self.client.post(reverse('calculate_receptionist_salaries'), {'month': month, 'base_salary': '100000'}).status_code, 302)
        return (Salary.objects.get(teacher=self.teacher, month=month + '-01'),
                ReceptionistSalary.objects.get(receptionist=self.rec, month=month + '-01'))

    def test_advance_and_late_payments_are_each_counted_once(self):
        advance = self.payment('2026-11', '2026-10-25T10:00')
        late = self.payment('2026-09', '2026-10-26T10:00')
        self.assertEqual(advance.teacher_salary_month, date(2026, 11, 1))
        self.assertEqual(late.teacher_salary_month, date(2026, 10, 1))
        self.assertEqual(ReceptionistCommission.objects.get(payment=late).month, date(2026, 10, 1))
        for month, expected in [('2026-09', 0), ('2026-10', 600000), ('2026-11', 600000), ('2026-12', 0)]:
            teacher, rec = self.calculate(month)
            self.assertEqual(teacher.total_income, expected)
            self.assertEqual(teacher.salary_amount, Decimal(expected) * Decimal('.4'))
            self.assertEqual(rec.total_commission, Decimal(expected) * Decimal('.1'))
            self.assertEqual(rec.total_salary, 100000 + rec.total_commission)
        self.calculate('2026-10')
        self.assertEqual(Salary.objects.filter(teacher=self.teacher, month='2026-10-01').count(), 1)
        self.assertEqual(ReceptionistCommission.objects.count(), 2)

    def test_partial_payments_keep_their_actual_collection_month(self):
        self.payment('2026-09', '2026-09-10T10:00', 200000)
        self.payment('2026-09', '2026-10-10T10:00', 400000)
        self.assertEqual(self.calculate('2026-09')[0].salary_amount, 80000)
        self.assertEqual(self.calculate('2026-10')[0].salary_amount, 160000)

    def test_date_edit_moves_both_open_payroll_periods_and_void_excludes_it(self):
        payment = self.payment('2026-09', '2026-09-10T10:00')
        payment.paid_date = timezone.make_aware(datetime(2026, 10, 10, 10))
        payment.save(update_fields=['paid_date'])
        payment.refresh_from_db()
        self.assertEqual(payment.teacher_salary_month, date(2026, 10, 1))
        self.assertEqual(self.calculate('2026-09')[0].salary_amount, 0)
        self.assertEqual(self.calculate('2026-10')[0].salary_amount, 240000)
        payment.void('Duplicate')
        teacher, rec = self.calculate('2026-10')
        self.assertEqual(teacher.salary_amount, 0)
        self.assertEqual(rec.total_commission, 0)

    def test_closed_actual_payroll_month_blocks_financial_edits_and_new_entries(self):
        payment = self.payment('2026-09', '2026-10-10T10:00')
        salary, _ = self.calculate('2026-10')
        salary.is_paid = True
        salary.save()
        payment.paid_date = timezone.make_aware(datetime(2026, 11, 1, 10))
        with self.assertRaises(ValidationError):
            payment.save()
        with self.assertRaises(ValidationError):
            self.payment('2026-08', '2026-10-12T10:00')
        payment.refresh_from_db()
        payment.comment = 'Comment is allowed'
        payment.save(update_fields=['comment'])
        self.assertEqual(payment.teacher_salary_month, date(2026, 10, 1))

    def test_closed_receptionist_payroll_month_is_protected(self):
        payment = self.payment('2026-09', '2026-10-10T10:00')
        _, salary = self.calculate('2026-10')
        salary.is_paid = True
        salary.save()
        with self.assertRaises(ValidationError):
            payment.void('Attempt')

    def test_local_month_boundary_and_year_rollover(self):
        payment = self.payment('2026-12', '2026-12-31T23:30')
        # 20:30 UTC is already January 1 in Tashkent.
        from datetime import timezone as dt_timezone
        payment.paid_date = datetime(2026, 12, 31, 20, 30, tzinfo=dt_timezone.utc)
        payment.save()
        self.assertEqual(payment.teacher_salary_month, date(2027, 1, 1))
        self.assertEqual(self.calculate('2026-12')[0].salary_amount, 0)
        self.assertEqual(self.calculate('2027-01')[0].salary_amount, 240000)

    def test_payment_form_separates_lesson_month_from_received_date(self):
        response = self.client.post(reverse('payment_create'), {
            'student': self.student.pk, 'month': '2026-09', 'amount': '600000',
            'paid_date': '2026-10-25T10:30', 'payment_type': 'cash',
        })
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get()
        self.assertEqual(payment.month, date(2026, 9, 1))
        self.assertEqual(payment.teacher_salary_month, date(2026, 10, 1))
        self.assertContains(self.client.get(reverse('payment_list')), 'Oylikka kiradigan oy')
        self.assertContains(self.client.get(reverse('payment_receipt', args=[payment.pk])), '30.09.2026')

    def test_payment_changes_refresh_existing_unpaid_salaries_automatically(self):
        self.calculate('2026-09')
        self.calculate('2026-10')
        payment = self.payment('2026-09', '2026-09-10T10:00')
        self.assertEqual(Salary.objects.get(teacher=self.teacher, month='2026-09-01').salary_amount, 240000)
        payment.paid_date = timezone.make_aware(datetime(2026, 10, 10, 10))
        payment.save()
        self.assertEqual(Salary.objects.get(teacher=self.teacher, month='2026-09-01').salary_amount, 0)
        self.assertEqual(Salary.objects.get(teacher=self.teacher, month='2026-10-01').salary_amount, 240000)
        self.assertEqual(ReceptionistSalary.objects.get(receptionist=self.rec, month='2026-09-01').total_commission, 0)
        self.assertEqual(ReceptionistSalary.objects.get(receptionist=self.rec, month='2026-10-01').total_commission, 60000)
        payment.void('Duplicate')
        self.assertEqual(Salary.objects.get(teacher=self.teacher, month='2026-10-01').salary_amount, 0)
        self.assertEqual(ReceptionistSalary.objects.get(receptionist=self.rec, month='2026-10-01').total_commission, 0)

    def test_cash_reports_use_collection_month_even_for_advance_and_late_payment(self):
        self.payment('2026-11', '2026-10-25T10:00')
        self.payment('2026-09', '2026-10-26T10:00')
        from unittest.mock import patch
        with patch('core.views.timezone.localdate', return_value=date(2026, 10, 31)):
            dashboard = self.client.get(reverse('dashboard'))
            report = self.client.get(reverse('reports'))
        self.assertEqual(dashboard.context['monthly_income'], 1200000)
        rows = {row['month']: row['income'] for row in report.context['monthly_income']}
        self.assertEqual(rows['2026-09'], 0)
        self.assertEqual(rows['2026-10'], 1200000)

    def test_comment_edit_on_paid_payment_preserves_original_seconds(self):
        payment = self.payment('2026-09', '2026-10-10T10:00:45')
        salary, _ = self.calculate('2026-10')
        salary.is_paid = True
        salary.save()
        response = self.client.post(reverse('payment_edit', args=[payment.pk]), {
            'student': self.student.pk, 'month': '2026-09', 'amount': '600000',
            'paid_date': '2026-10-10T10:00', 'payment_type': 'cash', 'comment': 'Updated note',
        })
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.paid_date.second, 45)
        self.assertEqual(payment.comment, 'Updated note')

    def test_migration_preserves_paid_legacy_months_and_refreshes_unpaid(self):
        payment = self.payment('2026-09', '2026-10-10T10:00')
        teacher = Salary.objects.create(teacher=self.teacher, month='2026-09-01', percent=40, total_income=600000, salary_amount=240000, is_paid=True)
        rec = ReceptionistSalary.objects.create(receptionist=self.rec, month='2026-09-01', base_salary=100000, total_commission=60000, total_salary=160000)
        ReceptionistCommission.objects.filter(payment=payment).update(month='2026-09-01')
        # Historical models intentionally use an unrestricted manager during backfill.
        from django.db.migrations.executor import MigrationExecutor
        # Include the added fields in the historical state, as RunPython sees them.
        migration = import_module('core.migrations.0020_payment_salary_months')
        state = MigrationExecutor(connection).loader.project_state([('core', '0019_notification_student_link')])
        for operation in migration.Migration.operations[:2]:
            operation.state_forwards('core', state)
        migration.backfill_salary_months(state.apps, SimpleNamespace(connection=connection))
        payment.refresh_from_db()
        teacher.refresh_from_db()
        rec.refresh_from_db()
        self.assertEqual(payment.teacher_salary_month, date(2026, 9, 1))
        self.assertEqual(payment.receptionist_salary_month, date(2026, 10, 1))
        self.assertEqual(teacher.salary_amount, 240000)
        self.assertTrue(teacher.is_paid)
        self.assertEqual(rec.total_commission, 0)
        self.assertEqual(rec.total_salary, 100000)
        self.assertEqual(self.calculate('2026-10')[0].salary_amount, 0)
        payment.comment = 'Keep paid history'
        payment.save(update_fields=['comment'])
        self.assertEqual(payment.teacher_salary_month, date(2026, 9, 1))
