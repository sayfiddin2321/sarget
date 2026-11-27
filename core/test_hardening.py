import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import ExpenseForm, StudentForm, TeacherForm
from .models import Attendance, Grade, Group, Lead, Notification, Payment, Receptionist, ReceptionistCommission, Salary, Student, Teacher
from .reminders import dispatch_due_callback_reminders
from .utils import calendar_months


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CrmHardeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user('admin', password='test-pass', is_superuser=True, is_staff=True)
        cls.unknown = User.objects.create_user('unknown', password='test-pass')
        cls.teacher_user = User.objects.create_user('teacher', password='test-pass')
        cls.rec_user = User.objects.create_user('reception', password='test-pass')
        cls.teacher = Teacher.objects.create(user=cls.teacher_user, name='Teacher', subject='Python', percent=40)
        cls.other_teacher = Teacher.objects.create(name='Other', subject='English', percent=50)
        cls.rec = Receptionist.objects.create(user=cls.rec_user, name='Reception', commission_percent=10)
        cls.other_rec = Receptionist.objects.create(name='Other Reception', commission_percent=20)
        cls.group = Group.objects.create(name='Python', teacher=cls.teacher, monthly_fee=500000, start_time=time(10), end_time=time(11))
        cls.student = Student.objects.create(name='Ali', phone='+998901234567', teacher=cls.teacher, group=cls.group, receptionist=cls.rec)

    def test_unknown_cannot_read_or_create_business_records(self):
        self.client.force_login(self.unknown)
        for name in ('dashboard', 'student_list', 'payment_list', 'api_students_search'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertEqual(self.client.post(reverse('payment_create'), {'student': self.student.pk, 'amount': '1000', 'month': '2026-10', 'payment_type': 'cash'}).status_code, 403)
        self.assertFalse(Payment.objects.exists())

    def test_inactive_profile_cannot_access_crm(self):
        Teacher.objects.filter(pk=self.teacher.pk).update(is_active=False)
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 403)

    def test_teacher_api_and_reception_card_share_object_scope(self):
        foreign = Student.objects.create(name='Other student', teacher=self.other_teacher, group=self.group)
        self.client.force_login(self.teacher_user)
        ids = {row['id'] for row in self.client.get(reverse('api_group_students', args=[self.group.pk])).json()['students']}
        self.assertIn(self.student.pk, ids)
        self.assertNotIn(foreign.pk, ids)
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(reverse('student_card_print', args=[foreign.pk])).status_code, 200)

    def test_login_next_rejects_external_but_accepts_local(self):
        credentials = {'username': 'admin', 'password': 'test-pass'}
        response = self.client.post(reverse('login') + '?next=https://example.invalid', credentials)
        self.assertEqual(response['Location'], reverse('dashboard'))
        self.client.logout()
        response = self.client.post(reverse('login') + '?next=/students/', credentials)
        self.assertEqual(response['Location'], '/students/')

    def test_grade_delete_requires_post_and_permission(self):
        grade = Grade.objects.create(student=self.student, group=self.group, score=80)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('grade_delete', args=[grade.pk])).status_code, 405)
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.post(reverse('grade_delete', args=[grade.pk])).status_code, 403)
        self.assertTrue(Grade.objects.filter(pk=grade.pk).exists())

    def test_archive_and_database_protection_preserve_payment(self):
        payment = Payment.objects.create(student=self.student, amount=1000, month=date(2026, 10, 1))
        self.client.force_login(self.admin)
        self.client.post(reverse('student_delete', args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, 'inactive')
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        with self.assertRaises(ProtectedError):
            self.student.delete()

    def test_partial_and_future_payments_do_not_hide_earlier_months(self):
        self.student = Student.objects.create(name='Historical student', group=self.group, registration_date=date(2026, 8, 1))
        paid_at = timezone.make_aware(datetime(2026, 10, 29, 10))
        Payment.objects.create(student=self.student, amount=1, month=date(2026, 10, 1), paid_date=paid_at)
        Payment.objects.create(student=self.student, amount=500000, month=date(2026, 11, 1), paid_date=paid_at)
        debts = self.student.get_debt_breakdown(today=date(2026, 10, 29))
        self.assertEqual(len(debts), 3)
        self.assertEqual(sum(item['amount'] for item in debts), Decimal('1499999'))

    def test_month_end_due_date_and_no_fee(self):
        self.student = Student.objects.create(name='Month end', group=self.group, registration_date=date(2026, 1, 31))
        self.assertEqual(len(self.student.get_debt_breakdown(today=date(2026, 2, 27))), 1)
        self.assertEqual(len(self.student.get_debt_breakdown(today=date(2026, 2, 28))), 2)
        self.group.monthly_fee = 0
        self.group.save()
        self.student.refresh_from_db()
        # A new free tariff must not erase already incurred historical debt.
        self.assertEqual(len(self.student.get_debt_breakdown(today=date(2026, 2, 28))), 2)

    def test_commission_keeps_original_receptionist_and_rate(self):
        payment = Payment.objects.create(student=self.student, amount=1000, month=date(2026, 10, 1))
        self.student.receptionist = self.other_rec
        self.student.save()
        payment.amount = 2000
        payment.save()
        commission = ReceptionistCommission.objects.get(payment=payment)
        self.assertEqual(commission.receptionist, self.rec)
        self.assertEqual(commission.commission_amount, Decimal('200'))

    def test_new_payment_snapshot_survives_teacher_transfer_and_archive(self):
        payment = Payment.objects.create(student=self.student, amount=1000, month=date(2026, 10, 1), paid_date=timezone.make_aware(datetime(2026, 10, 15, 10)))
        self.student.teacher = self.other_teacher
        self.student.status = 'inactive'
        self.student.save()
        self.teacher.percent = 80
        self.teacher.save()
        self.client.force_login(self.admin)
        self.client.post(reverse('calculate_salaries'), {'month': '2026-10'})
        self.assertEqual(Salary.objects.get(teacher=self.teacher, month=payment.month).salary_amount, Decimal('400'))

    def test_paid_salary_is_not_overwritten(self):
        salary = Salary.objects.create(teacher=self.teacher, month=date(2026, 10, 1), total_income=1000, percent=40, salary_amount=400, is_paid=True)
        with self.assertRaises(ValidationError):
            Payment.objects.create(student=self.student, amount=5000, month=salary.month, paid_date=timezone.make_aware(datetime(2026, 10, 15, 10)))
        self.client.force_login(self.admin)
        self.client.post(reverse('calculate_salaries'), {'month': '2026-10'})
        salary.refresh_from_db()
        self.assertEqual(salary.salary_amount, Decimal('400'))

    def test_enroll_is_visible_to_receptionist(self):
        lead = Lead.objects.create(name='Vali', phone='+998909876543', course='Python')
        self.client.force_login(self.rec_user)
        response = self.client.post(reverse('lead_enroll', args=[lead.pk]))
        lead.refresh_from_db()
        self.assertEqual(lead.student.receptionist, self.rec)
        self.assertRedirects(response, reverse('student_detail', args=[lead.student.pk]))

    def test_attendance_roundtrip_and_invalid_status_rejected(self):
        self.client.force_login(self.teacher_user)
        url = reverse('take_attendance', args=[self.group.pk])
        self.client.post(url, {f'attendance_{self.student.pk}': 'absent'})
        response = self.client.get(url)
        self.assertEqual(response.context['existing'][self.student.pk], 'absent')
        self.assertRegex(response.content.decode(), r'value="absent"\s+checked')
        self.client.post(url, {f'attendance_{self.student.pk}': 'invalid'})
        self.assertEqual(Attendance.objects.get(student=self.student).status, 'absent')

    def test_grade_unique_constraint(self):
        Grade.objects.create(student=self.student, group=self.group, score=80)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Grade.objects.create(student=self.student, group=self.group, score=90)

    def test_callback_rescheduled_same_day_gets_new_reminder(self):
        now = timezone.make_aware(datetime(2026, 10, 29, 9))
        lead = Lead.objects.create(name='Callback', course='Python', status='callback', follow_up_at=now)
        dispatch_due_callback_reminders(now)
        before = Notification.objects.count()
        lead.follow_up_at = now + timedelta(hours=1)
        lead.save()
        dispatch_due_callback_reminders(now + timedelta(hours=1))
        self.assertEqual(Notification.objects.count(), before * 2)
        dispatch_due_callback_reminders(now + timedelta(hours=1))
        self.assertEqual(Notification.objects.count(), before * 2)

    def test_negative_expense_and_blank_new_account_password_rejected(self):
        self.assertFalse(ExpenseForm({'title': 'Test', 'amount': '-1', 'category': 'other', 'date': '2026-10-29'}).is_valid())
        form = TeacherForm({'name': 'New', 'phone': '123456789', 'subject': 'Test', 'percent': '40', 'username': 'newteacher', 'password': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)

    def test_invalid_filters_and_salary_month_are_not_500(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('student_list'), {'teacher': 'invalid'}).status_code, 400)
        self.assertEqual(self.client.get(reverse('payment_list'), {'month': '2026-13'}).status_code, 400)
        self.assertEqual(self.client.post(reverse('calculate_salaries'), {'month': '2026-13'}).status_code, 302)

    def test_charts_use_valid_json_and_continuous_calendar_months(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'))
        raw = re.search(r'<script id="income-chart-data" type="application/json">(.*?)</script>', response.content.decode(), re.S).group(1)
        self.assertEqual(len(json.loads(raw)), 6)
        self.assertEqual(calendar_months(date(2026, 3, 1), 3), [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)])

    def test_export_respects_filter_and_escapes_formulas(self):
        Lead.objects.create(name='=SUM(1)', course='Python', status='new')
        Lead.objects.create(name='Hidden', course='English', status='contacted')
        self.client.force_login(self.admin)
        text = self.client.get(reverse('lead_export'), {'status': 'new'}).content.decode()
        self.assertIn("'=SUM(1)", text)
        self.assertNotIn('Hidden', text)
