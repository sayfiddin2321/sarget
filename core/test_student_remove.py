from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Payment, Student, Teacher


@override_settings(TELEGRAM_BOT_TOKEN='', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StudentRemovalTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('remove-admin', password='test')
        self.teacher_user = get_user_model().objects.create_user('remove-teacher')
        self.teacher = Teacher.objects.create(name='Teacher', user=self.teacher_user)
        self.student = Student.objects.create(name='Remove student', teacher=self.teacher)
        self.url = reverse('student_remove', args=[self.student.pk])

    def test_only_superadmin_can_remove_and_get_does_not_change_data(self):
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_remove_hides_student_but_keeps_payment_and_receipt(self):
        payment = Payment.objects.create(student=self.student, amount=500000,
                                         month=timezone.localdate().replace(day=1))
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('student_list')), self.url)
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        removed = Student.all_objects.get(pk=self.student.pk)
        self.assertEqual(removed.status, 'inactive')
        self.assertIsNotNone(removed.deleted_at)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        self.assertEqual(self.client.get(reverse('student_detail', args=[removed.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('payment_receipt', args=[payment.pk])).status_code, 200)
        self.assertEqual(self.client.post(self.url).status_code, 404)
