from datetime import date, datetime, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Group, Payment, Student, Teacher


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StudentListActionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user('admin', password='test-pass', is_superuser=True, is_staff=True)
        teacher_user = User.objects.create_user('teach', password='test-pass')
        cls.teacher = Teacher.objects.create(user=teacher_user, name='Teacher', subject='Python')
        cls.group = Group.objects.create(name='Python-1', teacher=cls.teacher,
                                         start_time=time(10), end_time=time(11))
        cls.student = Student.objects.create(name='Ali', teacher=cls.teacher, group=cls.group)
        cls.lonely = Student.objects.create(name='Anor', teacher=cls.teacher)

    def test_grade_link_points_to_students_group(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('student_list'))
        self.assertContains(response, reverse('take_grades', args=[self.group.pk]))
        # Guruhsiz o'quvchi uchun havola berilmaydi (pk=None URL xatosi bo'lmaydi).
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="Baholash"', count=1)

    def test_mobile_card_markup_is_rendered(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('student_list'))
        self.assertContains(response, 'class="student-table"')
        for label in ("O'qituvchi", 'Telefon', 'Guruh', 'Qarz', 'Amallar'):
            self.assertIn(f'data-label="{label}"', response.content.decode())

    def test_teacher_sees_only_own_students_with_grade_link(self):
        self.client.force_login(self.teacher.user)
        response = self.client.get(reverse('student_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ali')
        self.assertContains(response, 'Anor')
        self.assertContains(response, reverse('take_grades', args=[self.group.pk]))

    def test_students_without_tuition_are_not_shown_as_paid(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('student_list'))
        self.assertNotContains(response, "> To'langan</span>")
        self.assertContains(response, "To'lanmagan")
        self.assertNotContains(response, 'Hisoblanmagan')
        self.assertEqual(self.lonely.payment_status, 'unpaid')

    def test_actual_payment_without_group_is_recognized(self):
        from .models import Refund
        today = timezone.localdate()
        payment = Payment.objects.create(student=self.lonely, month=today.replace(day=1), amount=500000)
        self.assertEqual(self.lonely.payment_status, 'paid')
        Refund.objects.create(payment=payment, amount=500000, reason='Refund', created_by=self.admin)
        self.assertEqual(self.lonely.payment_status, 'unpaid')

    @patch('django.utils.timezone.localdate', return_value=date(2026, 11, 11))
    def test_payment_status_distinguishes_unpaid_partial_and_paid(self, localdate):
        self.group.monthly_fee = 300000
        self.group.save()
        student = Student.objects.create(
            name='Payment status', group=self.group, teacher=self.teacher,
            registration_date=date(2026, 11, 10), payment_due_day=20,
        )
        # No overdue debt does not mean that tuition has been paid.
        self.assertEqual(student.get_debt_amount(), 0)
        self.assertEqual(student.payment_status, 'unpaid')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('student_list'))
        self.assertContains(response, "To'lanmagan")
        paid_at = timezone.make_aware(datetime(2026, 11, 11, 10))
        payment = Payment.objects.create(student=student, month=date(2026, 11, 1), amount=100000,
                                         paid_date=paid_at)
        self.assertEqual(student.payment_status, 'unpaid')
        payment.amount = 300000
        payment.save()
        self.assertEqual(student.payment_status, 'paid')
        response = self.client.get(reverse('student_list'))
        self.assertContains(response, "> To'langan</span>", count=1)
        payment.voided_at = paid_at
        payment.save()
        self.assertEqual(student.payment_status, 'unpaid')
