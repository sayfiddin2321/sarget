from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLConnection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    FinancialAudit, Group, Payment, PaymentQuerySet, Receptionist, ReceptionistCommission,
    Refund, Salary, Student, Teacher,
)


@override_settings(
    TELEGRAM_BOT_TOKEN='', TELEGRAM_STAFF_CHAT_ID='',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class AdminPaymentDeleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('payment-admin', password='test')
        cls.staff = get_user_model().objects.create_user('payment-viewer', is_staff=True)
        cls.teacher = Teacher.objects.create(name='Teacher', percent=40)
        cls.receptionist = Receptionist.objects.create(name='Reception', commission_percent=10)
        cls.group = Group.objects.create(
            name='Course', teacher=cls.teacher, monthly_fee=500000,
            start_time=time(9), end_time=time(10),
        )
        cls.student = Student.objects.create(
            name='Ali', group=cls.group, teacher=cls.teacher, receptionist=cls.receptionist,
            registration_date=timezone.localdate().replace(day=1),
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.changelist = reverse('admin:core_payment_changelist')

    def payment(self, **kwargs):
        values = {
            'student': self.student, 'amount': Decimal(100000),
            'month': timezone.localdate().replace(day=1),
        }
        values.update(kwargs)
        return Payment.objects.create(**values)

    def delete_url(self, payment):
        return reverse('admin:core_payment_delete', args=[payment.pk])

    def test_list_and_detail_expose_delete_and_get_only_confirms(self):
        payment = self.payment()
        response = self.client.get(self.changelist)
        self.assertContains(response, 'value="delete_selected"')
        response = self.client.get(reverse('admin:core_payment_change', args=[payment.pk]))
        self.assertContains(response, self.delete_url(payment))
        response = self.client.get(self.delete_url(payment))
        self.assertContains(response, 'name="reason"')
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        response = self.client.post(self.changelist, {
            'action': 'delete_selected', '_selected_action': [payment.pk], 'index': 0,
        })
        self.assertContains(response, 'name="reason"')
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_single_delete_preserves_history_and_recalculates_finances(self):
        payment = self.payment()
        debt_before = self.student.get_debt_amount()
        response = self.client.post(self.delete_url(payment), {
            'post': 'yes', 'reason': 'Duplicate entry',
        })
        self.assertRedirects(response, self.changelist)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())
        saved = Payment.all_objects.get(pk=payment.pk)
        self.assertEqual(saved.void_reason, 'Duplicate entry')
        self.assertIsNotNone(saved.voided_at)
        self.assertEqual(self.student.get_debt_amount(), debt_before + payment.amount)
        self.assertFalse(ReceptionistCommission.objects.filter(payment=payment).exists())
        self.assertTrue(ReceptionistCommission.all_objects.filter(payment=payment).exists())
        salary = Salary.objects.get(teacher=self.teacher, month=payment.teacher_salary_month)
        self.assertEqual(salary.total_income, 0)
        self.assertEqual(salary.salary_amount, 0)
        event = FinancialAudit.objects.get(entity='payment', object_id=payment.pk, action='void')
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.after['void_reason'], 'Duplicate entry')
        self.assertTrue(LogEntry.objects.filter(
            user=self.admin, object_id=str(payment.pk), action_flag=CHANGE,
        ).exists())

    def test_bulk_delete_only_cancels_selected_payments(self):
        first, second, untouched = self.payment(), self.payment(), self.payment()
        response = self.client.post(self.changelist, {
            'action': 'delete_selected', '_selected_action': [first.pk, second.pk],
            'post': 'yes', 'reason': 'Wrong import',
        })
        self.assertRedirects(response, self.changelist)
        self.assertQuerySetEqual(Payment.objects.all(), [untouched], ordered=False)
        self.assertEqual(FinancialAudit.objects.filter(entity='payment', action='void').count(), 2)
        self.assertEqual(Payment.all_objects.filter(void_reason='Wrong import').count(), 2)

    def test_bulk_delete_search_locks_only_payment_table_on_postgresql(self):
        payment = self.payment(received_by=None)
        locked_queries = []
        select_for_update = PaymentQuerySet.select_for_update

        def capture_lock(queryset, *args, **kwargs):
            locked = select_for_update(queryset, *args, **kwargs)
            locked_queries.append(locked)
            return locked

        with patch.object(PaymentQuerySet, 'select_for_update', autospec=True, side_effect=capture_lock):
            response = self.client.post(self.changelist + '?q=Ali', {
                'action': 'delete_selected', '_selected_action': [payment.pk],
                'post': 'yes', 'reason': 'Wrong entry',
            })
        self.assertRedirects(response, self.changelist)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())
        self.assertTrue(locked_queries)

        # Compile the actual action query with PostgreSQL even on SQLite test runs.
        postgres = PostgreSQLConnection({'NAME': 'sql-check', 'OPTIONS': {}}, alias='sql-check')
        with patch.object(postgres, 'get_autocommit', return_value=False):
            sql, _ = locked_queries[0].query.get_compiler(connection=postgres).as_sql()
        self.assertIn('LEFT OUTER JOIN', sql)
        self.assertTrue(sql.endswith('FOR UPDATE OF "core_payment"'), sql)

    def test_empty_reason_does_not_cancel_payment(self):
        payment = self.payment()
        response = self.client.post(self.delete_url(payment), {'post': 'yes', 'reason': '  '})
        self.assertEqual(response.status_code, 200)
        self.assertIn('reason', response.context['form'].errors)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_bulk_delete_rolls_back_every_payment_when_one_period_is_paid(self):
        locked = self.payment(
            month=date(2026, 1, 1),
            paid_date=timezone.make_aware(timezone.datetime(2026, 1, 5, 10)),
        )
        salary = Salary.objects.get(teacher=self.teacher, month=locked.teacher_salary_month)
        salary.is_paid = True
        salary.save(update_fields=['is_paid'])
        unlocked = self.payment()
        response = self.client.post(self.changelist, {
            'action': 'delete_selected', '_selected_action': [locked.pk, unlocked.pk],
            'post': 'yes', 'reason': 'Wrong entries',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertEqual(Payment.objects.count(), 2)
        self.assertFalse(FinancialAudit.objects.filter(entity='payment', action='void').exists())
        self.assertFalse(LogEntry.objects.filter(action_flag=CHANGE).exists())
        salary = Salary.objects.get(teacher=self.teacher, month=unlocked.teacher_salary_month)
        self.assertEqual(salary.total_income, unlocked.amount)

    def test_payment_with_refund_is_cancelled_and_refund_history_is_preserved(self):
        payment = self.payment()
        refund = Refund.objects.create(payment=payment, amount=10000, reason='Refund', created_by=self.admin)
        debt_before = self.student.get_debt_amount()
        response = self.client.post(self.delete_url(payment), {'post': 'yes', 'reason': 'Wrong entry'})
        self.assertRedirects(response, self.changelist)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())
        self.assertEqual(Payment.all_objects.get(pk=payment.pk).void_reason, 'Wrong entry')
        self.assertTrue(Refund.objects.filter(pk=refund.pk, amount=10000).exists())
        self.assertEqual(self.student.get_debt_amount(), debt_before + 90000)
        salary = Salary.objects.get(teacher=self.teacher, month=payment.teacher_salary_month)
        self.assertEqual(salary.total_income, 0)
        self.assertEqual(salary.salary_amount, 0)
        self.assertFalse(ReceptionistCommission.objects.filter(payment=payment).exists())
        self.assertEqual(FinancialAudit.objects.get(
            entity='payment', object_id=payment.pk, action='void',
        ).actor, self.admin)

    def test_bulk_delete_handles_partial_full_and_unrefunded_payments_together(self):
        partial, full, normal = self.payment(), self.payment(), self.payment()
        Refund.objects.create(payment=partial, amount=20000, reason='Partial', created_by=self.admin)
        Refund.objects.create(payment=full, amount=full.amount, reason='Full', created_by=self.admin)
        response = self.client.post(self.changelist, {
            'action': 'delete_selected', '_selected_action': [partial.pk, full.pk, normal.pk],
            'post': 'yes', 'reason': 'Wrong import',
        })
        self.assertRedirects(response, self.changelist)
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(Payment.all_objects.filter(void_reason='Wrong import').count(), 3)
        self.assertEqual(Refund.objects.count(), 2)
        self.assertEqual(FinancialAudit.objects.filter(entity='payment', action='void').count(), 3)

    def test_staff_requires_delete_permission_for_single_and_bulk(self):
        payment = self.payment()
        self.client.force_login(self.staff)
        response = self.client.get(self.changelist)
        self.assertNotContains(response, 'value="delete_selected"')
        self.assertEqual(self.client.get(self.delete_url(payment)).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url(payment), {
            'post': 'yes', 'reason': 'Unauthorized',
        }).status_code, 403)
        self.client.post(self.changelist, {
            'action': 'delete_selected', '_selected_action': [payment.pk],
            'post': 'yes', 'reason': 'Unauthorized',
        })
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        self.staff.user_permissions.add(Permission.objects.get(codename='delete_payment'))
        response = self.client.post(self.delete_url(payment), {'post': 'yes', 'reason': 'Authorized'})
        self.assertRedirects(response, self.changelist)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())

    def test_delete_requires_csrf_token(self):
        payment = self.payment()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(self.delete_url(payment), {'post': 'yes', 'reason': 'No CSRF token'})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
