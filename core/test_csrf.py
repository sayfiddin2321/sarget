import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Student, TelegramLinkToken


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TelegramLinkCsrfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('csrf-admin', 'admin@example.test', 'test-pass')
        cls.student = Student.objects.create(name='CSRF test student')

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.url = reverse('telegram_link')

    def form_data(self, secure=False):
        response = self.client.get(self.url, secure=secure)
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        self.assertEqual(response['Cache-Control'], 'no-store')
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.content.decode()).group(1)
        return {'target': f'student:{self.student.pk}', 'csrfmiddlewaretoken': token}

    def test_same_origin_form_post_creates_link_code(self):
        response = self.client.post(self.url, self.form_data(), HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TelegramLinkToken.objects.count(), 1)

    def test_https_form_with_same_origin_referer_creates_link_code(self):
        response = self.client.post(self.url, self.form_data(secure=True), secure=True,
                                    HTTP_REFERER='https://testserver/telegram/link/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TelegramLinkToken.objects.count(), 1)

    def test_null_or_foreign_origin_remains_rejected_even_with_valid_token(self):
        data = self.form_data()
        for origin in ('null', 'https://untrusted.example'):
            response = self.client.post(self.url, data, HTTP_ORIGIN=origin)
            self.assertEqual(response.status_code, 403)
        self.assertFalse(TelegramLinkToken.objects.exists())

    def test_same_origin_without_csrf_token_remains_rejected(self):
        self.form_data()
        response = self.client.post(self.url, {'target': f'student:{self.student.pk}'}, HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TelegramLinkToken.objects.exists())
