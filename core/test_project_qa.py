"""Additional financial, validation, API and concurrent-operation audit scenarios."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from decimal import Decimal
from threading import Barrier, BrokenBarrierError, Event, local
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .models import (
    Attendance, Course, Expense, FinancialAudit, Group, Payment, Receptionist,
    ReceptionistCommission, ReceptionistSalary, Refund, Salary, Student, Teacher,
)
from .payroll import percentage_share


def fixtures():
    owner = get_user_model().objects.create_superuser('qa-owner', password='qa-test-password')
    teacher = Teacher.objects.create(name='QA Teacher', percent=40)
    receptionist = Receptionist.objects.create(name='QA Reception', commission_percent=10)
    course = Course.objects.create(name='QA course')
    group = Group.objects.create(name='QA group', teacher=teacher, course=course, monthly_fee=500000,
                                 start_time=time(9), end_time=time(10))
    student = Student.objects.create(name='QA Student', teacher=teacher, group=group,
                                     receptionist=receptionist, registration_date=date(2026, 11, 1))
    return owner, teacher, receptionist, group, student


@override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_STAFF_CHAT_ID='', CRM_API_KEY='qa-test-api-key',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProjectQATests(TestCase):
    def setUp(self):
        self.owner, self.teacher, self.receptionist, self.group, self.student = fixtures()
        self.client.force_login(self.owner)

    def payload(self, **kwargs):
        data = {'student': self.student.pk, 'amount': '150000', 'month': '2026-11',
                'paid_date': '2026-11-20T10:00', 'payment_type': 'cash'}
        data.update(kwargs)
        return data

    def test_replayed_payment_submission_creates_one_payment(self):
        data = self.payload(submission_key=str(uuid4()))
        first = self.client.post(reverse('payment_create'), data)
        second = self.client.post(reverse('payment_create'), data)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first.url, second.url)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(FinancialAudit.objects.filter(entity='payment', action='create').count(), 1)

    def test_payment_submission_key_cannot_be_reused_for_different_amount(self):
        data = self.payload(submission_key=str(uuid4()))
        self.client.post(reverse('payment_create'), data)
        response = self.client.post(reverse('payment_create'), {**data, 'amount': '250000'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)

    def test_attendance_overlong_note_is_rejected_without_partial_save(self):
        response = self.client.post(reverse('take_attendance', args=[self.group.pk]), {
            f'attendance_{self.student.pk}': 'present', f'note_{self.student.pk}': 'x' * 201,
            f'score_{self.student.pk}': '90',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Attendance.objects.exists())
        self.assertTrue(response.context['form_errors'])

    def test_receptionist_salary_out_of_range_is_rejected(self):
        for amount in ('10000000000', '1e1000', '0.001', '-1', 'NaN', 'Infinity'):
            with self.subTest(amount=amount), transaction.atomic():
                response = self.client.post(reverse('calculate_receptionist_salaries'), {
                    'month': '2026-11', 'base_salary': amount,
                })
                self.assertEqual(response.status_code, 302)
                self.assertFalse(ReceptionistSalary.objects.exists())

    def test_protected_course_delete_returns_message_instead_of_500(self):
        response = self.client.post(reverse('course_delete', args=[self.group.course_id]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Course.objects.filter(pk=self.group.course_id).exists())

    def test_model_payment_amount_rejects_nonfinite_and_precision_overflow(self):
        for amount in ('NaN', 'Infinity', '-Infinity', '10000000000', '0.001', '0', '-1'):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    Payment.objects.create(student=self.student, amount=Decimal(amount), month=date(2026, 11, 1))
        self.assertFalse(Payment.objects.exists())

    def test_percentage_rounding_matches_independent_controls(self):
        for amount, rate, expected in (('0.03', '50', '0.02'), ('123.45', '12.5', '15.43'),
                                       ('9999999.99', '40', '4000000.00'), ('100', '0', '0.00')):
            with self.subTest(amount=amount, rate=rate):
                self.assertEqual(percentage_share(Decimal(amount), Decimal(rate)), Decimal(expected))

    def test_payment_form_supplies_a_unique_submission_key(self):
        first = self.client.get(reverse('payment_create'))
        second = self.client.get(reverse('payment_create'))
        self.assertContains(first, 'name="submission_key"')
        self.assertNotEqual(str(first.context['form']['submission_key'].value()),
                            str(second.context['form']['submission_key'].value()))

    def test_distinct_payment_submissions_allow_legitimate_same_amount(self):
        for _ in range(2):
            self.assertEqual(self.client.post(reverse('payment_create'),
                self.payload(submission_key=str(uuid4()))).status_code, 302)
        self.assertEqual(Payment.objects.count(), 2)

    def test_admin_cannot_create_negative_expense(self):
        response = self.client.post(reverse('admin:core_expense_add'), {
            'title': 'Invalid expense', 'category': 'other', 'amount': '-1', 'date': '2026-11-20',
            'added_by': self.owner.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Expense.objects.exists())

    def test_month_end_leap_day_and_year_change_use_one_charge_per_month(self):
        student = Student.objects.create(name='Calendar QA', group=self.group, registration_date=date(2023, 12, 31))
        controls = ((date(2023, 12, 31), 1), (date(2024, 1, 30), 1), (date(2024, 1, 31), 2),
                    (date(2024, 2, 28), 2), (date(2024, 2, 29), 3), (date(2024, 3, 30), 3),
                    (date(2024, 3, 31), 4), (date(2024, 4, 29), 4), (date(2024, 4, 30), 5))
        for day, months in controls:
            with self.subTest(day=day):
                rows = student.get_debt_breakdown(today=day)
                self.assertEqual(sum(row['amount'] for row in rows), Decimal(500000) * months)
                self.assertEqual(len(rows), months)
                self.assertEqual(len({row['month'] for row in rows}), months)

    def test_api_methods_authentication_and_invalid_json_matrix(self):
        self.client.logout()
        write_routes = ['api_bot_create_lead', 'api_bot_auth_user', 'api_bot_lead_message']
        read_routes = ['api_bot_courses_list', 'api_bot_student_info', 'api_bot_staff_summary', 'api_bot_account']
        for name in write_routes + read_routes:
            url = reverse(name)
            expected_method = 'post' if name in write_routes else 'get'
            for method in ('get', 'post', 'put', 'patch', 'delete'):
                with self.subTest(route=name, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 401 if method == expected_method else 405)
            if name in write_routes:
                for body in ('{', '[]', 'null', '42', '"text"'):
                    with self.subTest(route=name, body=body):
                        response = self.client.post(url, body, content_type='application/json',
                                                    HTTP_X_CRM_API_KEY='qa-test-api-key')
                        self.assertEqual(response.status_code, 400)

    def test_all_named_routes_reject_anonymous_mutations_and_avoid_500(self):
        from .urls import urlpatterns
        self.client.logout()
        public = {'login', 'api_health_check', 'payment_verify', 'payment_qr',
                  'certificate_verify', 'certificate_verify_short'}
        for pattern in urlpatterns:
            kwargs = {}
            for name, converter in pattern.pattern.converters.items():
                kind = converter.__class__.__name__
                kwargs[name] = uuid4() if kind == 'UUIDConverter' else 999999 if kind == 'IntConverter' else 'qa-invalid'
            url = reverse(pattern.name, kwargs=kwargs)
            for method in ('get', 'post'):
                with self.subTest(route=pattern.name, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertIn(response.status_code, (200, 302, 400, 401, 403, 404, 405))
                    if pattern.name not in public:
                        self.assertNotEqual(response.status_code, 200)

    def test_admin_payment_validation_rejects_negative_amount(self):
        response = self.client.post(reverse('admin:core_payment_add'), {
            'student': self.student.pk, 'amount': '-1', 'month': '2026-11-01',
            'paid_date_0': '2026-11-20', 'paid_date_1': '10:00',
            'payment_type': 'cash', 'received_by': self.owner.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.exists())

    def test_full_financial_user_journey_preserves_data_after_relogin(self):
        self.client.logout()
        self.assertTrue(self.client.login(username='qa-owner', password='qa-test-password'))
        with patch('core.views.timezone.localdate', return_value=date(2026, 11, 20)), \
                patch('core.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 11, 20, 12))), \
                patch.object(Refund._meta.get_field('paid_at'), '_get_default',
                             return_value=timezone.make_aware(datetime(2026, 11, 20, 12))):
            for amount in ('150000', '350000'):
                response = self.client.post(reverse('payment_create'), self.payload(amount=amount))
                self.assertEqual(response.status_code, 302)
            self.assertEqual(self.student.get_debt_amount(), 0)
            response = self.client.post(reverse('expense_create'), {
                'title': 'QA rent', 'amount': '50000', 'date': '2026-11-20', 'category': 'rent',
            })
            self.assertEqual(response.status_code, 302)
            self.client.post(reverse('calculate_receptionist_salaries'), {'month': '2026-11', 'base_salary': '50000'})
            payment = Payment.objects.order_by('-pk').first()
            self.assertEqual(self.client.post(reverse('refund_create', args=[payment.pk]), {
                'amount': '100000', 'reason': 'QA partial return',
            }).status_code, 302)
            dashboard = self.client.get(reverse('dashboard'))
            self.assertEqual(dashboard.context['monthly_income'], 400000)
            self.assertEqual(dashboard.context['monthly_expenses'], 300000)  # 160k teacher + 90k reception + 50k rent
            self.assertEqual(dashboard.context['net_income'], 100000)
            self.assertEqual(self.student.get_debt_amount(), 100000)
            self.client.logout()
            self.assertTrue(self.client.login(username='qa-owner', password='qa-test-password'))
            self.assertEqual(self.client.get(reverse('dashboard')).context['monthly_income'], 400000)
            self.assertEqual(self.client.post(reverse('payment_delete', args=[payment.pk]), {'reason': 'QA correction'}).status_code, 302)
            dashboard = self.client.get(reverse('dashboard'))
            self.assertEqual(dashboard.context['monthly_income'], 150000)
            self.assertEqual(dashboard.context['monthly_expenses'], 175000)  # 60k + 65k + 50k
            self.assertEqual(dashboard.context['net_income'], -25000)
            self.assertEqual(Payment.objects.count(), 1)
            self.assertEqual(Payment.all_objects.count(), 2)
            self.assertEqual(Refund.objects.count(), 1)
            self.assertEqual(self.student.get_debt_amount(), 350000)


@override_settings(TELEGRAM_BOT_TOKEN='', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ConcurrentFinancialQATests(TransactionTestCase):
    def setUp(self):
        self.owner, self.teacher, self.receptionist, self.group, self.student = fixtures()
        self.payment = Payment.objects.create(student=self.student, amount=100000, month=date(2026, 11, 1))

    def worker(self, operation):
        close_old_connections()
        try:
            operation()
            return 'saved'
        except ValidationError:
            return 'rejected'
        finally:
            close_old_connections()

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_cancellations_create_only_one_void_event(self):
        barrier, state = Barrier(2), local()
        ensure_open = Payment.ensure_open_period

        def pause_after_old_read(payment):
            if not getattr(state, 'waited', False):
                state.waited = True
                try:
                    barrier.wait(timeout=1)
                except BrokenBarrierError:
                    pass
            return ensure_open(payment)

        def cancel():
            Payment.objects.get(pk=self.payment.pk).void('QA parallel cancel')

        with patch.object(Payment, 'ensure_open_period', pause_after_old_read):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(self.worker, [cancel, cancel]))
        self.assertCountEqual(results, ['saved', 'rejected'])
        self.assertEqual(FinancialAudit.objects.filter(entity='payment', action='void').count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_refunds_cannot_exceed_payment(self):
        barrier = Barrier(2)

        def refund():
            barrier.wait(timeout=5)
            Refund.objects.create(payment_id=self.payment.pk, amount=70000,
                                   reason='QA parallel refund', created_by_id=self.owner.pk)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.worker, [refund, refund]))
        self.assertCountEqual(results, ['saved', 'rejected'])
        self.assertEqual(Refund.objects.get().amount, 70000)
        self.assertEqual(Salary.objects.get(teacher=self.teacher).total_income, 30000)

    @skipUnlessDBFeature('has_select_for_update')
    def test_payment_and_salary_paid_status_keep_the_same_total(self):
        checked, marked = Event(), Event()
        ensure_open = Payment.ensure_open_period
        self.client.force_login(self.owner)
        salary = Salary.objects.get(teacher=self.teacher)

        def pause_after_check(payment):
            ensure_open(payment)
            if payment._state.adding:
                checked.set()
                marked.wait(timeout=1)

        def create():
            Payment.objects.create(student_id=self.student.pk, amount=100000, month=date(2026, 11, 1))

        def mark_paid():
            self.assertTrue(checked.wait(timeout=5))
            self.assertEqual(self.client.post(reverse('update_salary_status', args=[salary.pk])).status_code, 302)
            marked.set()

        with patch.object(Payment, 'ensure_open_period', pause_after_check):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(self.worker, [create, mark_paid]))
        self.assertEqual(results, ['saved', 'saved'])
        salary.refresh_from_db()
        self.assertTrue(salary.is_paid)
        self.assertEqual(salary.total_income, 200000)
        self.assertEqual(salary.salary_amount, 80000)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_retry_of_same_submission_is_saved_once(self):
        from .payments import accept_payment
        barrier, key = Barrier(2), uuid4()

        def submit():
            payment = Payment(student_id=self.student.pk, amount=150000, month=date(2026, 11, 1),
                              paid_date=timezone.make_aware(datetime(2026, 11, 20, 10)),
                              received_by_id=self.owner.pk)
            barrier.wait(timeout=5)
            accept_payment(payment, key)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.worker, [submit, submit]))
        self.assertEqual(results, ['saved', 'saved'])
        self.assertEqual(Payment.objects.filter(submission_key=key).count(), 1)
        self.assertEqual(Salary.objects.get(teacher=self.teacher).total_income, 250000)
