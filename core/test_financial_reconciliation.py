from datetime import date, datetime, time
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .finance import monthly_cash_totals, monthly_income_totals
from .models import Enrollment, Group, Payment, Receptionist, ReceptionistCommission, ReceptionistSalary, Refund, Salary, Student, Teacher
from .period_payroll import period_calculation
from .reporting import Report
from .telegram_linking import issue_link_code, redeem_link_code


@override_settings(TELEGRAM_BOT_TOKEN='', CRM_API_KEY='audit-test-key',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FinancialReconciliationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('audit-admin', password='test')
        cls.teacher = Teacher.objects.create(name='Teacher', percent=40)
        cls.rec = Receptionist.objects.create(name='Reception', commission_percent=10)
        cls.group = Group.objects.create(name='Main', teacher=cls.teacher, monthly_fee=490000,
                                        start_time=time(9), end_time=time(10))
        cls.student = Student.objects.create(name='Student', teacher=cls.teacher, group=cls.group,
                                            receptionist=cls.rec, registration_date=date(2026, 11, 1))

    def setUp(self):
        self.client.force_login(self.admin)

    def payment(self, amount=480000, month=date(2026, 11, 1), **kwargs):
        return Payment.objects.create(student=self.student, amount=amount, month=month,
                                      paid_date=timezone.make_aware(datetime(2026, 11, 20, 10)), **kwargs)

    def test_refund_reconciles_debt_payroll_commission_reports_and_bot_api(self):
        payment = self.payment()
        rec_salary = ReceptionistSalary.objects.create(
            receptionist=self.rec, month=date(2026, 11, 1), base_salary=10000,
            total_commission=48000, total_salary=58000,
        )
        Refund.objects.create(payment=payment, amount=Decimal(100000), reason='Returned', created_by=self.admin,
                              paid_at=timezone.make_aware(datetime(2026, 11, 20, 11)))
        teacher_salary = Salary.objects.get(teacher=self.teacher)
        self.assertEqual(teacher_salary.total_income, 380000)
        self.assertEqual(teacher_salary.salary_amount, 152000)
        self.assertEqual(ReceptionistCommission.objects.get(payment=payment).commission_amount, 38000)
        rec_salary.refresh_from_db()
        self.assertEqual(rec_salary.total_salary, 48000)
        with patch('core.views.timezone.localdate', return_value=date(2026, 11, 20)):
            detail = self.client.get(reverse('student_detail', args=[self.student.pk]))
            dashboard = self.client.get(reverse('dashboard'))
            report = self.client.get(reverse('reports'))
            redeem_link_code(issue_link_code('student', self.student.pk, self.admin), 555111)
            bot = self.client.get('/api/bot/student-info/', {'chat_id': 555111}, HTTP_X_CRM_API_KEY='audit-test-key')
        self.assertEqual(detail.context['debt_amount'], 110000)
        self.assertEqual(bot.status_code, 200)
        self.assertEqual(bot.json()['student']['finance']['debt_amount'], 110000)
        self.assertEqual(dashboard.context['monthly_income'], 380000)
        self.assertEqual(dashboard.context['monthly_expenses'], 200000)
        self.assertEqual(dashboard.context['net_income'], 180000)
        self.assertEqual(report.context['total_income_year'], 380000)
        self.assertEqual(report.context['total_expense_year'], 200000)

    def test_secondary_course_payment_belongs_to_its_teacher(self):
        other_teacher = Teacher.objects.create(name='Second teacher', percent=50)
        other_group = Group.objects.create(name='Second course', teacher=other_teacher, monthly_fee=490000,
                                          start_time=time(11), end_time=time(12))
        enrollment = Enrollment.objects.create(student=self.student, group=other_group,
                                               starts_on=date(2026, 11, 1), monthly_fee=490000)
        payment = self.payment(enrollment=enrollment)
        self.assertEqual(payment.teacher_at_payment, other_teacher)
        self.assertEqual(payment.teacher_percent_at_payment, 50)
        self.assertEqual(Salary.objects.get(teacher=other_teacher).salary_amount, 240000)
        self.assertFalse(Salary.objects.filter(teacher=self.teacher).exists())

    def test_changing_course_moves_the_unpaid_teacher_share(self):
        payment = self.payment()
        other_teacher = Teacher.objects.create(name='Second teacher', percent=50)
        other_group = Group.objects.create(name='Second course', teacher=other_teacher, monthly_fee=490000,
                                          start_time=time(11), end_time=time(12))
        payment.enrollment = Enrollment.objects.create(student=self.student, group=other_group,
                                                       starts_on=date(2026, 11, 1), monthly_fee=490000)
        payment.save(update_fields=['enrollment'])
        payment.refresh_from_db()
        self.assertEqual(payment.teacher_at_payment, other_teacher)
        self.assertEqual(payment.group_at_payment, other_group)
        self.assertEqual(Salary.objects.get(teacher=other_teacher).salary_amount, 240000)
        self.assertEqual(Salary.objects.get(teacher=self.teacher).salary_amount, 0)

    def test_each_payment_rounds_the_same_way_in_monthly_and_period_payroll(self):
        self.teacher.percent = 50
        self.teacher.save()
        for _ in range(2):
            self.payment(amount=Decimal('.03'))
        salary = Salary.objects.get(teacher=self.teacher)
        period = period_calculation({'date_from': date(2026, 11, 1), 'date_to': date(2026, 11, 30)})
        self.assertEqual(salary.total_income, Decimal('.06'))
        self.assertEqual(salary.salary_amount, Decimal('.04'))
        self.assertEqual(period['salary_total'], salary.salary_amount)
        self.assertEqual(period['center_total'], Decimal('.02'))

    def test_refund_cannot_change_already_paid_payroll(self):
        payment = self.payment()
        salary = Salary.objects.get(teacher=self.teacher)
        salary.is_paid = True
        salary.save()
        with self.assertRaises(ValidationError):
            Refund.objects.create(payment=payment, amount=Decimal(100000), reason='Returned', created_by=self.admin)
        salary.refresh_from_db()
        self.assertEqual(salary.salary_amount, 192000)
        self.assertFalse(payment.refunds.exists())

    def test_migration_repairs_old_refund_totals_and_preserves_paid_rows(self):
        payment = self.payment()
        Refund.objects.create(payment=payment, amount=Decimal(100000), reason='Returned', created_by=self.admin)
        salary = Salary.objects.get(teacher=self.teacher)
        Salary.objects.filter(pk=salary.pk).update(total_income=480000, salary_amount=192000)
        ReceptionistCommission.objects.filter(payment=payment).update(payment_amount=480000, commission_amount=48000)
        rec_salary = ReceptionistSalary.objects.create(
            receptionist=self.rec, month=payment.receptionist_salary_month,
            base_salary=10000, total_commission=48000, total_salary=58000,
        )
        state = MigrationExecutor(connection).loader.project_state([('core', '0022_backfill_teacher_payroll')])
        migration = import_module('core.migrations.0023_reconcile_refunded_payroll')
        migration.reconcile_refunded_payroll(state.apps, SimpleNamespace(connection=connection))
        salary.refresh_from_db()
        rec_salary.refresh_from_db()
        self.assertEqual(salary.total_income, 380000)
        self.assertEqual(salary.salary_amount, 152000)
        self.assertEqual(rec_salary.total_salary, 48000)
        self.assertEqual(ReceptionistCommission.objects.get(payment=payment).commission_amount, 38000)
        Salary.objects.filter(pk=salary.pk).update(is_paid=True, salary_amount=123)
        ReceptionistSalary.objects.filter(pk=rec_salary.pk).update(is_paid=True, total_salary=456)
        migration.reconcile_refunded_payroll(state.apps, SimpleNamespace(connection=connection))
        salary.refresh_from_db()
        rec_salary.refresh_from_db()
        self.assertEqual(salary.salary_amount, 123)
        self.assertEqual(rec_salary.total_salary, 456)

    def test_later_cancellation_does_not_erase_original_month_cash_event(self):
        payment = Payment.objects.create(student=self.student, amount=100000, month=date(2026, 10, 1),
                                         paid_date=timezone.make_aware(datetime(2026, 10, 15, 10)))
        with patch('core.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 11, 20, 10))):
            payment.void('Wrong entry')
        cash = monthly_cash_totals(date(2026, 10, 1), date(2026, 11, 30))
        self.assertEqual(cash[date(2026, 10, 1)], 100000)
        self.assertEqual(cash[date(2026, 11, 1)], -100000)
        self.assertEqual(sum(cash.values()), 0)

    def test_refunds_and_later_cancellation_deduct_cash_only_once(self):
        payment = Payment.objects.create(
            student=self.student, amount=480000, month=date(2026, 10, 1),
            paid_date=timezone.make_aware(datetime(2026, 10, 15, 10)),
        )
        for amount in (100000, 50000):
            Refund.objects.create(
                payment=payment, amount=amount, reason='Returned', created_by=self.admin,
                paid_at=timezone.make_aware(datetime(2026, 11, 15, 10)),
            )
        with patch('core.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 12, 20, 10))):
            payment.void('Wrong entry after refund')
        cash = monthly_cash_totals(date(2026, 10, 1), date(2026, 12, 31))
        self.assertEqual(cash[date(2026, 10, 1)], 480000)
        self.assertEqual(cash[date(2026, 11, 1)], -150000)
        self.assertEqual(cash[date(2026, 12, 1)], -330000)
        self.assertEqual(sum(cash.values()), 0)
        summary = Report(self.admin, 'payments', {
            'date_from': '2026-10-01', 'date_to': '2026-12-31',
        }).summary()
        self.assertEqual(summary['gross'], 480000)
        self.assertEqual(summary['refunds'], 150000)
        self.assertEqual(summary['cancellations'], 330000)
        self.assertEqual(summary['net_cash'], 0)
        refund_month = Report(self.admin, 'payments', {
            'date_from': '2026-11-01', 'date_to': '2026-11-30',
        }).summary()
        self.assertEqual(refund_month['net_cash'], -150000)
        cancel_month = Report(self.admin, 'payments', {
            'date_from': '2026-12-01', 'date_to': '2026-12-31',
        }).summary()
        self.assertEqual(cancel_month['net_cash'], -330000)

    def test_full_refund_then_cancellation_has_no_further_cash_deduction(self):
        payment = self.payment()
        Refund.objects.create(payment=payment, amount=payment.amount, reason='Full return', created_by=self.admin)
        payment.void('Wrong entry')
        today = timezone.localdate()
        summary = Report(self.admin, 'payments', {'month': today.strftime('%Y-%m')}).summary()
        self.assertEqual(summary['refunds'], payment.amount)
        self.assertEqual(summary['cancellations'], 0)
        self.assertEqual(summary['net_cash'], 0)
        cash = monthly_cash_totals(today.replace(day=1), today)
        self.assertEqual(sum(cash.values()), 0)
        with self.assertRaises(ValidationError):
            Refund.objects.create(payment=payment, amount=1, reason='After void', created_by=self.admin)

    def test_deleted_old_payment_does_not_leave_negative_overview_income(self):
        payment = Payment.objects.create(
            student=self.student, amount=4720000, month=date(2026, 9, 1),
            paid_date=timezone.make_aware(datetime(2026, 9, 17, 10)),
        )
        with patch('core.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 11, 21, 10))):
            payment.void('Wrong entry')
        self.assertFalse(Payment.objects.exists())
        with patch('core.views.timezone.localdate', return_value=date(2026, 11, 21)):
            dashboard = self.client.get(reverse('dashboard'))
            report = self.client.get(reverse('reports'))
        self.assertEqual(dashboard.context['monthly_income'], 0)
        self.assertFalse(dashboard.context['recent_payments'])
        self.assertTrue(all(row['income'] == 0 for row in dashboard.context['chart_data']))
        self.assertEqual(report.context['total_income_year'], 0)
        self.assertTrue(all(row['income'] == 0 for row in report.context['monthly_income']))
        self.assertTrue(Payment.all_objects.filter(pk=payment.pk, voided_at__isnull=False).exists())

    def test_cancelled_payment_and_its_refunds_do_not_reduce_active_income(self):
        old = Payment.objects.create(
            student=self.student, amount=4720000, month=date(2026, 9, 1),
            paid_date=timezone.make_aware(datetime(2026, 9, 17, 10)),
        )
        Refund.objects.create(
            payment=old, amount=100000, reason='Return', created_by=self.admin,
            paid_at=timezone.make_aware(datetime(2026, 11, 20, 10)),
        )
        with patch('core.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 11, 21, 10))):
            old.void('Wrong entry')
        active = self.payment()
        Refund.objects.create(
            payment=active, amount=20000, reason='Partial return', created_by=self.admin,
            paid_at=timezone.make_aware(datetime(2026, 11, 20, 11)),
        )
        with patch('core.views.timezone.localdate', return_value=date(2026, 11, 21)):
            dashboard = self.client.get(reverse('dashboard'))
            report = self.client.get(reverse('reports'))
        self.assertEqual(dashboard.context['monthly_income'], 460000)
        self.assertEqual(report.context['total_income_year'], 460000)
        active.void('Remove last payment')
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(monthly_income_totals(date(2026, 1, 1), date(2026, 12, 31)), {})
        self.assertEqual(Refund.objects.count(), 2)

    def test_refund_of_active_old_payment_remains_in_refund_month(self):
        payment = Payment.objects.create(
            student=self.student, amount=480000, month=date(2026, 9, 1),
            paid_date=timezone.make_aware(datetime(2026, 9, 17, 10)),
        )
        Refund.objects.create(
            payment=payment, amount=100000, reason='Return', created_by=self.admin,
            paid_at=timezone.make_aware(datetime(2026, 11, 20, 10)),
        )
        income = monthly_income_totals(date(2026, 9, 1), date(2026, 11, 30))
        self.assertEqual(income[date(2026, 9, 1)], 480000)
        self.assertEqual(income[date(2026, 11, 1)], -100000)
