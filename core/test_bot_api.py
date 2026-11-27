import json
from decimal import Decimal
from datetime import date, time
from django.test import TestCase, Client, override_settings
from django.conf import settings
from core.models import Student, Teacher, Receptionist, Group, Lead, Grade, Attendance, Course
from core.telegram_linking import issue_link_code, redeem_link_code


@override_settings(CRM_API_KEY='test-api-key')
class BotApiTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.api_key = getattr(settings, 'CRM_API_KEY', 'sarget-crm-api-secret-key-2026')
        self.headers = {'HTTP_X_CRM_API_KEY': self.api_key}

        self.teacher = Teacher.objects.create(
            name='Alisher Ustoz',
            phone='+998901112233',
            subject='Matematika',
            percent=50,
            is_active=True
        )

        self.group = Group.objects.create(
            name='Mat-101',
            teacher=self.teacher,
            monthly_fee=Decimal('500000.00'),
            days='1-3-5',
            start_time=time(9),
            end_time=time(10),
            room='Xona 3',
            is_active=True
        )

        self.student = Student.objects.create(
            name='Azizbek Vohidov',
            phone='+998909876543',
            parent_phone='+998901234567',
            group=self.group,
            teacher=self.teacher,
            status='active'
        )

    def test_missing_api_key_returns_401(self):
        res = self.client.get('/api/bot/courses/')
        self.assertEqual(res.status_code, 401)
        data = res.json()
        self.assertFalse(data['ok'])

    def test_invalid_api_key_returns_401(self):
        res = self.client.get('/api/bot/courses/', HTTP_X_CRM_API_KEY='wrong-secret-key')
        self.assertEqual(res.status_code, 401)

    def test_courses_list(self):
        Course.objects.create(name='Matematika')
        res = self.client.get('/api/bot/courses/', **self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertIn('Matematika', data['courses'])
        self.assertNotIn('Mat-101', data['courses'])

    def test_create_lead_success(self):
        payload = {
            'name': 'Bekzod Rahimov',
            'phone': '+998935557788',
            'course': 'Ingliz tili',
            'chat_id': 123456789,
            'campaign': 'telegram_welcome'
        }
        res = self.client.post(
            '/api/bot/leads/',
            data=json.dumps(payload),
            content_type='application/json',
            **self.headers
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data['ok'])
        lead = Lead.objects.get(pk=data['lead_id'])
        self.assertEqual(lead.name, 'Bekzod Rahimov')
        self.assertEqual(lead.phone, '+998935557788')
        self.assertEqual(lead.telegram_chat_id, 123456789)

    def test_auth_student_and_bind_chat_id(self):
        payload = {
            'code': issue_link_code('student', self.student.pk, None),
            'chat_id': 999888777
        }
        res = self.client.post(
            '/api/bot/auth/',
            data=json.dumps(payload),
            content_type='application/json',
            **self.headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['role'], 'student')
        self.assertEqual(data['user']['name'], 'Azizbek Vohidov')

        # Check in DB
        self.student.refresh_from_db()
        self.assertEqual(self.student.telegram_chat_id, 999888777)

    def test_auth_teacher(self):
        payload = {
            'code': issue_link_code('teacher', self.teacher.pk, None),
            'chat_id': 777666555
        }
        res = self.client.post(
            '/api/bot/auth/',
            data=json.dumps(payload),
            content_type='application/json',
            **self.headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['role'], 'teacher')
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.telegram_chat_id, 777666555)

    def test_student_info(self):
        redeem_link_code(issue_link_code('student', self.student.pk, None), 999888777)

        Grade.objects.create(
            student=self.student,
            group=self.group,
            date=date.today(),
            grade_type='homework',
            score=95,
            note='Ajoyib uy vazifasi'
        )

        Attendance.objects.create(
            student=self.student,
            group=self.group,
            date=date.today(),
            status='present'
        )

        res = self.client.get('/api/bot/student-info/?chat_id=999888777', **self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        std = data['student']
        self.assertEqual(std['name'], 'Azizbek Vohidov')
        self.assertEqual(len(std['grades']), 1)
        self.assertEqual(std['grades'][0]['score'], 95)
        self.assertEqual(std['attendance']['total'], 1)
        self.assertEqual(std['attendance']['present'], 1)

    def test_staff_summary(self):
        redeem_link_code(issue_link_code('teacher', self.teacher.pk, None), 123456)
        res = self.client.get('/api/bot/staff-summary/?chat_id=123456', **self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        summary = data['summary']
        self.assertGreaterEqual(summary['total_active_students'], 1)

    def test_health_check_public(self):
        # Health check does not require API key
        res = self.client.get('/api/bot/health/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['service'], 'sarget-crm')
        self.assertEqual(data['db'], 'ok')

    def test_create_lead_idempotency_prevents_duplicates(self):
        payload = {
            'name': 'Dilshod Karimov',
            'phone': '+998901234500',
            'course': 'Python Backend',
            'chat_id': 555444333,
            'campaign': 'tg_promo'
        }
        # 1-marta yuborilganda: yangi lead yaratiladi (201)
        res1 = self.client.post(
            '/api/bot/leads/',
            data=json.dumps(payload),
            content_type='application/json',
            **self.headers
        )
        self.assertEqual(res1.status_code, 201)
        lead_id_1 = res1.json()['lead_id']
        self.assertEqual(Lead.objects.filter(telegram_chat_id=555444333).count(), 1)

        # 2-marta aynan bir xil so'rov: takroriy lead yaratilmaydi (200, duplicate=True)
        res2 = self.client.post(
            '/api/bot/leads/',
            data=json.dumps(payload),
            content_type='application/json',
            **self.headers
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2['ok'])
        self.assertTrue(data2.get('duplicate'))
        self.assertEqual(data2['lead_id'], lead_id_1)
        # Bazada hali ham faqat 1 ta lead bo'lishi kerak!
        self.assertEqual(Lead.objects.filter(telegram_chat_id=555444333).count(), 1)

    def test_unlinked_student_info_returns_403(self):
        res = self.client.get('/api/bot/student-info/?chat_id=999999999', **self.headers)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.json()['ok'])

    def test_unlinked_staff_summary_returns_403(self):
        res = self.client.get('/api/bot/staff-summary/?chat_id=999999999', **self.headers)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.json()['ok'])

    def test_create_lead_invalid_json_returns_400(self):
        res = self.client.post(
            '/api/bot/leads/',
            data='not valid json',
            content_type='application/json',
            **self.headers
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json()['ok'])

