from datetime import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Attendance, Grade, Group, Receptionist, StaffCapability, Student, Teacher


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AttendanceGradingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.teacher_user = users.objects.create_user('joint-teacher')
        cls.rec_user = users.objects.create_user('joint-reception')
        cls.teacher = Teacher.objects.create(user=cls.teacher_user, name='Teacher')
        cls.other_teacher = Teacher.objects.create(name='Other teacher')
        Receptionist.objects.create(user=cls.rec_user, name='Reception')
        cls.group = Group.objects.create(name='Joint class', teacher=cls.teacher, monthly_fee=500000,
                                         start_time=time(9), end_time=time(10))
        other_group = Group.objects.create(name='Other class', teacher=cls.other_teacher, monthly_fee=500000,
                                           start_time=time(11), end_time=time(12))
        cls.first = Student.objects.create(name='First student', phone='+998901234567', group=cls.group, teacher=cls.teacher)
        cls.second = Student.objects.create(name='Second student', phone='+998901234568', group=cls.group, teacher=cls.teacher)
        cls.foreign = Student.objects.create(name='Foreign student', phone='+998901234569', group=other_group, teacher=cls.other_teacher)

    def setUp(self):
        self.client.force_login(self.teacher_user)
        self.url = reverse('take_attendance', args=[self.group.pk])
        self.today = timezone.localdate()

    def test_attendance_and_optional_grade_save_together(self):
        response = self.client.post(self.url, {f'attendance_{self.first.pk}': 'present', f'score_{self.first.pk}': '92',
                                               f'attendance_{self.second.pk}': 'absent', f'score_{self.second.pk}': ''})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Attendance.objects.count(), 2)
        grade = Grade.objects.get(student=self.first)
        self.assertEqual((grade.score, grade.date, grade.grade_type, grade.graded_by), (92, self.today, 'classwork', self.teacher_user))
        self.assertFalse(Grade.objects.filter(student=self.second).exists())

    def test_existing_grade_is_prefilled_updated_without_duplicates_and_blank_preserves_it(self):
        grade = Grade.objects.create(student=self.first, group=self.group, date=self.today, score=70, note='Keep grade note')
        homework = Grade.objects.create(student=self.first, group=self.group, date=self.today, grade_type='homework', score=65)
        Attendance.objects.create(student=self.first, group=self.group, date=self.today, status='late', note='Keep attendance note')
        response = self.client.get(self.url)
        self.assertEqual(response.context['scores'][self.first.pk], 70)
        self.assertContains(response, f'name="score_{self.first.pk}"')
        self.client.post(self.url, {f'attendance_{self.first.pk}': 'present', f'score_{self.first.pk}': '85'})
        grade.refresh_from_db()
        homework.refresh_from_db()
        self.assertEqual(grade.score, 85)
        self.assertEqual(grade.note, 'Keep grade note')
        self.assertEqual(homework.score, 65)
        self.assertEqual(Grade.objects.count(), 2)
        self.assertEqual(Attendance.objects.get(student=self.first).note, 'Keep attendance note')
        self.client.post(self.url, {f'attendance_{self.first.pk}': 'late', f'score_{self.first.pk}': ''})
        grade.refresh_from_db()
        self.assertEqual(grade.score, 85)

    def test_invalid_score_preserves_inputs_and_blocks_all_writes(self):
        for invalid in ('0', '101', '-1', '2.5', 'abc', '999999999999999999999'):
            with self.subTest(score=invalid):
                response = self.client.post(self.url, {f'attendance_{self.first.pk}': 'late', f'score_{self.first.pk}': invalid,
                                                       f'attendance_{self.second.pk}': 'present', f'score_{self.second.pk}': '90'})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'role="alert"')
                self.assertEqual(response.context['scores'][self.first.pk], invalid)
                self.assertEqual(response.context['scores'][self.second.pk], '90')
                self.assertEqual(response.context['existing'][self.first.pk], 'late')
                self.assertFalse(Attendance.objects.exists())
                self.assertFalse(Grade.objects.exists())

    def test_invalid_attendance_or_missing_status_blocks_grade(self):
        for status in ('invalid', ''):
            response = self.client.post(self.url, {f'attendance_{self.first.pk}': status, f'score_{self.first.pk}': '90'})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Attendance.objects.exists())
            self.assertFalse(Grade.objects.exists())

    def test_attendance_only_role_cannot_write_grades(self):
        StaffCapability.objects.create(user=self.rec_user, code='attendance.write', allowed=True)
        self.client.force_login(self.rec_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'name="score_{self.first.pk}"')
        response = self.client.post(self.url, {f'attendance_{self.first.pk}': 'present', f'score_{self.first.pk}': '90'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Attendance.objects.exists())
        self.assertFalse(Grade.objects.exists())
        response = self.client.post(self.url, {f'attendance_{self.first.pk}': 'present'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Attendance.objects.filter(student=self.first).exists())

    def test_foreign_student_fields_are_ignored(self):
        response = self.client.post(self.url, {f'attendance_{self.first.pk}': 'present', f'score_{self.first.pk}': '90',
                                               f'attendance_{self.foreign.pk}': 'present', f'score_{self.foreign.pk}': '100'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Attendance.objects.filter(student=self.foreign).exists())
        self.assertFalse(Grade.objects.filter(student=self.foreign).exists())

    def test_failure_saving_grade_rolls_back_attendance(self):
        with patch('core.views.Grade.objects.update_or_create', side_effect=IntegrityError('Simulated failure')):
            with self.assertRaises(IntegrityError):
                self.client.post(self.url, {f'attendance_{self.first.pk}': 'present', f'score_{self.first.pk}': '90'})
        self.assertFalse(Attendance.objects.exists())
        self.assertFalse(Grade.objects.exists())
