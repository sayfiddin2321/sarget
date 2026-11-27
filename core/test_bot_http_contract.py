"""Run the standalone bot's actual HTTP client against a live Django test server.

The bot folder is optional on CRM-only deployments. No Telegram requests are sent.
"""
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import patch

from django.test import LiveServerTestCase, override_settings

from .models import Course, Group, Lead, Payment, Refund, Student, Teacher
from .telegram_linking import issue_link_code
from django.utils import timezone
from datetime import time
from decimal import Decimal

BOT_FILE = Path(__file__).resolve().parents[2] / 'sarget_BOT' / 'bot.py'


@skipUnless(BOT_FILE.exists() and importlib.util.find_spec('requests'),
            'HTTP contract test requires the bot folder and requirements-dev.txt')
@override_settings(CRM_API_KEY='contract-test-key', TELEGRAM_BOT_TOKEN='', TELEGRAM_BOT_MODE='disabled')
class BotHttpContractTests(LiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp = TemporaryDirectory()
        with patch.dict(os.environ, {
            'TELEGRAM_BOT_TOKEN': 'contract-test-token', 'CRM_API_URL': cls.live_server_url,
            'CRM_API_KEY': 'contract-test-key', 'BOT_STATE_DB': str(Path(cls.temp.name) / 'state.sqlite3'),
            'BOT_ENV': 'development',
        }):
            spec = importlib.util.spec_from_file_location('standalone_bot_contract', BOT_FILE)
            cls.bot = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.bot)
        cls.bot.http.trust_env = False

    @classmethod
    def tearDownClass(cls):
        cls.bot.http.close()
        cls.bot.db.close()
        cls.temp.cleanup()
        super().tearDownClass()

    def test_http_health_courses_registration_and_duplicate(self):
        Course.objects.create(name='Python')
        self.assertTrue(self.bot.check_connection())
        status, data = self.bot.crm('GET', '/api/bot/courses/')
        self.assertEqual(status, 200)
        self.assertIn('Python', data['courses'])
        payload = {'name': 'HTTP Student', 'phone': '+998901234567', 'course': 'Python',
                   'chat_id': 1234567, 'user_id': 1234567}
        status, data = self.bot.crm('POST', '/api/bot/leads/', json=payload)
        self.assertEqual(status, 201)
        status, duplicate = self.bot.crm('POST', '/api/bot/leads/', json=payload)
        self.assertEqual(status, 200)
        self.assertEqual(data['lead_id'], duplicate['lead_id'])
        self.assertEqual(Lead.objects.count(), 1)
        status, account = self.bot.crm('GET', '/api/bot/account/', params={'chat_id': 1234567})
        self.assertEqual(status, 200)
        self.assertFalse(account['linked'])

    def test_http_invalid_key_is_rejected(self):
        with patch.object(self.bot, 'CRM_KEY', 'wrong-key'):
            status, data = self.bot.crm('GET', '/api/bot/courses/')
        self.assertEqual(status, 401)
        self.assertFalse(data['ok'])

    def test_http_link_partial_payment_and_refund_show_the_same_debt(self):
        teacher = Teacher.objects.create(name='Teacher', percent=40)
        group = Group.objects.create(name='Math', teacher=teacher, monthly_fee=490000,
                                     start_time=time(9), end_time=time(10))
        student = Student.objects.create(name='Student', teacher=teacher, group=group)
        code = issue_link_code('student', student.pk, None)
        payload = {'code': code, 'chat_id': 1234567}
        self.assertEqual(self.bot.crm('POST', '/api/bot/auth/', json=payload)[0], 200)
        self.assertEqual(self.bot.crm('POST', '/api/bot/auth/', json=payload)[0], 200)
        payment = Payment.objects.create(student=student, amount=480000, month=timezone.localdate().replace(day=1))
        status, data = self.bot.crm('GET', '/api/bot/student-info/', params={'chat_id': 1234567})
        self.assertEqual(status, 200)
        self.assertEqual(data['student']['finance']['debt_amount'], 10000)
        self.assertIn('10 000', self.bot.format_student_info(data['student']))
        from django.contrib.auth import get_user_model
        admin = get_user_model().objects.create_superuser('contract-admin', password='test')
        Refund.objects.create(payment=payment, amount=Decimal(100000), reason='Returned', created_by=admin)
        status, data = self.bot.crm('GET', '/api/bot/student-info/', params={'chat_id': 1234567})
        self.assertEqual(status, 200)
        self.assertEqual(data['student']['finance']['debt_amount'], 110000)
        self.assertIn('110 000', self.bot.format_student_info(data['student']))
