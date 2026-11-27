from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Student, TelegramBinding, TelegramLinkToken
from .telegram_linking import issue_link_code, redeem_link_code


@override_settings(TELEGRAM_BOT_TOKEN='', CRM_API_KEY='retry-test-key')
class LinkRetryTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(name='Retry student')

    def test_same_chat_retry_succeeds_other_chat_cannot_reuse_code(self):
        code = issue_link_code('student', self.student.pk, None)
        first = redeem_link_code(code, 123)
        self.assertEqual(redeem_link_code(code, 123), first)
        self.assertEqual(TelegramBinding.objects.count(), 1)
        with self.assertRaises(ValidationError):
            redeem_link_code(code, 456)

    def test_guardian_retry_is_bound_to_original_chat(self):
        code = issue_link_code('guardian', self.student.pk, None)
        first = redeem_link_code(code, 123)
        self.assertEqual(redeem_link_code(code, 123), first)
        with self.assertRaises(ValidationError):
            redeem_link_code(code, 456)

    def test_revoked_or_expired_binding_cannot_be_replayed(self):
        code = issue_link_code('student', self.student.pk, None)
        redeem_link_code(code, 123)
        TelegramLinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            redeem_link_code(code, 123)
        code = issue_link_code('student', self.student.pk, None)
        redeem_link_code(code, 123)
        TelegramBinding.objects.all().delete()
        with self.assertRaises(ValidationError):
            redeem_link_code(code, 123)

    def test_duplicate_http_auth_returns_success_twice(self):
        code = issue_link_code('student', self.student.pk, None)
        for _ in range(2):
            response = self.client.post(reverse('api_bot_auth_user'),
                {'code': code, 'chat_id': 123}, content_type='application/json',
                HTTP_X_CRM_API_KEY='retry-test-key')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['ok'])
