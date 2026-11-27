import base64
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlsplit

from PIL import Image

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Payment, Refund, Student, Teacher
from .payment_verification import SALT, qr_image_data_uri
from django.core import signing


@override_settings(TELEGRAM_BOT_TOKEN='', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], TIME_ZONE='Asia/Tashkent')
class PeriodPayrollTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('period-admin', password='test')
        cls.teacher = Teacher.objects.create(name='Teacher', percent=40)
        cls.student = Student.objects.create(name='Private Student', teacher=cls.teacher, phone='+998901234567')

    def payment(self, month, paid, amount=300000):
        return Payment.objects.create(student=self.student, month=date.fromisoformat(month + '-01'),
                                      amount=amount, paid_date=timezone.make_aware(datetime.fromisoformat(paid)))

    def report(self, **kwargs):
        self.client.force_login(self.admin)
        return self.client.get(reverse('period_payroll'), {
            'date_from': '2026-05-10', 'date_to': '2026-06-10', **kwargs,
        })

    def test_date_range_includes_both_days_and_separates_service_month(self):
        april = self.payment('2026-04', '2026-05-10T00:00:00')
        july = self.payment('2026-07', '2026-06-10T23:59:59')
        self.payment('2026-04', '2026-05-09T23:59:59')
        self.payment('2026-07', '2026-06-11T00:00:00')
        response = self.report()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['payment_count'], 2)
        self.assertEqual(response.context['student_count'], 1)
        self.assertEqual(response.context['net_total'], 600000)
        self.assertEqual(response.context['salary_total'], 240000)
        self.assertEqual(response.context['center_total'], 360000)
        self.assertEqual({row['payment'].pk for row in response.context['rows']}, {april.pk, july.pk})
        response = self.report(service_month='2026-07')
        self.assertEqual(response.context['payment_count'], 1)
        self.assertEqual(response.context['rows'][0]['payment'], july)

    def test_saved_percent_void_refund_and_teacher_filter(self):
        payment = self.payment('2026-04', '2026-05-15T10:00:00')
        Refund.objects.create(payment=payment, amount=100000, reason='Partial refund', created_by=self.admin)
        cancelled = self.payment('2026-04', '2026-05-16T10:00:00')
        cancelled.void('Duplicate')
        self.teacher.percent = 90
        self.teacher.save()
        response = self.report(teacher=self.teacher.pk)
        self.assertEqual(response.context['payment_count'], 1)
        self.assertEqual(response.context['net_total'], 200000)
        self.assertEqual(response.context['salary_total'], 80000)
        self.assertEqual(response.context['refund_total'], 100000)
        self.assertEqual(response.context['center_total'], 120000)
        other = Teacher.objects.create(name='Other', percent=50)
        self.assertEqual(self.report(teacher=other.pk).context['payment_count'], 0)

    def test_center_share_and_all_time_payments_have_distinct_totals(self):
        self.payment('2026-11', '2026-11-10T10:00:00', amount=600000)
        self.payment('2026-11', '2026-11-11T10:00:00', amount=600000)
        for name, amount, paid in (
            ('Second', 480000, '2026-11-12T10:00:00'),
            ('Third', 380000, '2026-11-13T10:00:00'),
            ('Fourth', 4720000, '2026-09-10T10:00:00'),
        ):
            student = Student.objects.create(name=name)
            Payment.objects.create(student=student, amount=amount, month=date(2026, 11, 1),
                                   paid_date=timezone.make_aware(datetime.fromisoformat(paid)))
        response = self.report(date_from='2026-11-01', date_to='2026-11-20')
        self.assertEqual(response.context['gross_total'], 2060000)
        self.assertEqual(response.context['net_total'], 2060000)
        self.assertEqual(response.context['salary_total'], 480000)
        self.assertEqual(response.context['center_total'], 1580000)
        self.assertContains(response, '1580000')
        self.assertContains(response, '01.11.2026')
        self.assertContains(response, '20.11.2026')
        all_payments = self.client.get(reverse('payment_list'))
        self.assertEqual(all_payments.context['total'], 6780000)
        self.assertEqual(all_payments.context['student_count'], 4)
        self.assertEqual(all_payments.context['payment_count'], 5)
        filtered_payments = self.client.get(reverse('payment_list'), {
            'paid_from': '2026-11-01', 'paid_to': '2026-11-20',
        })
        self.assertEqual(filtered_payments.context['total'], response.context['gross_total'])

    def test_bad_dates_show_errors_and_report_requires_permission(self):
        response = self.report(date_from='2026-07-01')
        self.assertTrue(response.context['form'].errors)
        self.assertNotIn('rows', response.context)
        response = self.report(service_month='wrong')
        self.assertTrue(response.context['form'].errors)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('period_payroll')).status_code, 302)
        user = get_user_model().objects.create_user('no-role')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('period_payroll')).status_code, 403)

    def test_payment_list_filters_count_unique_students_and_keep_service_month(self):
        self.payment('2026-04', '2026-05-15T10:00:00')
        self.payment('2026-07', '2026-05-16T10:00:00')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('payment_list'), {
            'paid_from': '2026-05-10', 'paid_to': '2026-06-10', 'month': '2026-07',
        })
        self.assertEqual(response.context['student_count'], 1)
        self.assertEqual(response.context['payment_count'], 1)
        self.assertContains(response, 'name="paid_from"')
        response = self.client.get(reverse('payment_list'), {
            'paid_from': '2026-05-10', 'paid_to': '2026-06-10',
        })
        self.assertEqual(response.context['student_count'], 1)
        self.assertEqual(response.context['payment_count'], 2)

    def test_qr_links_to_public_verification_and_rechecks_void(self):
        payment = self.payment('2026-04', '2026-05-15T10:00:00')
        self.client.force_login(self.admin)
        receipt = self.client.get(reverse('payment_receipt', args=[payment.pk]))
        url = receipt.context['verification_url']
        self.assertContains(receipt, url)
        qr_url = receipt.context['receipt_qr_url']
        # The printable QR is embedded, so no image request can race window.print().
        qr_data_uri = receipt.context['receipt_qr_data_uri']
        self.assertContains(receipt, 'src="' + qr_data_uri + '"')
        self.assertNotContains(receipt, 'src="' + qr_url + '"')
        self.assertNotContains(receipt, 'js/qrcode.min.js')
        self.client.logout()
        qr_response = self.client.get(qr_url)
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response['Content-Type'], 'image/png')
        self.assertEqual(base64.b64decode(qr_data_uri.split(',', 1)[1]), qr_response.content)
        source = Image.open(BytesIO(qr_response.content))
        self.assertEqual(source.format, 'PNG')
        png = source.convert('RGB')
        self.assertGreaterEqual(png.width, 192)
        self.assertEqual(png.getpixel((0, 0)), (255, 255, 255))
        # The finder pattern must contain black modules, not an empty white image.
        self.assertEqual(png.getpixel((32, 32)), (0, 0, 0))
        self.assertEqual(png.getpixel((40, 40)), (255, 255, 255))
        self.assertEqual(self.client.get(qr_url.replace('/qr.png', 'broken/qr.png')).status_code, 404)
        self.assertNotContains(receipt, 'CHEK: ')
        self.client.logout()
        response = self.client.get(url)
        self.assertContains(response, "To'lov tasdiqlandi")
        self.assertContains(response, 'CHEK HAQIQIY')
        self.assertContains(response, 'Chek haqiqiyligi Sarget CRM bazasida tasdiqlandi')
        self.assertContains(response, payment.receipt_number)
        self.assertContains(response, "300 000 SO'M")
        self.assertNotContains(response, self.student.phone)
        self.assertNotContains(response, self.student.name)
        self.assertIn('no-store', response['Cache-Control'])
        payment.void('Duplicate')
        void_response = self.client.get(url)
        self.assertContains(void_response, "To'lov bekor qilingan")
        self.assertNotContains(void_response, 'CHEK HAQIQIY')
        self.assertNotContains(void_response, 'class="verified-mark"')
        self.client.force_login(self.admin)
        receipt = self.client.get(reverse('payment_receipt', args=[payment.pk]))
        self.assertContains(receipt, 'BEKOR QILINGAN')
        self.assertNotContains(receipt, '<span>TO\'LANDI</span>')
        self.client.logout()
        self.assertEqual(self.client.get(url + 'broken').status_code, 404)
        missing = signing.dumps(99999999, salt=SALT)
        self.assertEqual(self.client.get(reverse('payment_verify', args=[missing])).status_code, 404)

    def test_receipt_groups_amount_with_spaces(self):
        self.client.force_login(self.admin)
        for amount, expected in (
            (600000, '600 000'), (1250000, '1 250 000'),
            (Decimal('600000.49'), '600 000'), (Decimal('600000.50'), '600 001'),
        ):
            with self.subTest(amount=amount):
                payment = self.payment('2026-11', '2026-11-14T13:26:00', amount=amount)
                receipt = self.client.get(reverse('payment_receipt', args=[payment.pk]))
                self.assertContains(receipt, f'<span class="total-amount">{expected} SO\'M</span>', html=True)

    def test_public_verification_reports_partial_and_full_refunds(self):
        payment = self.payment('2026-04', '2026-05-15T10:00:00')
        url = reverse('payment_verify', args=[signing.dumps(payment.pk, salt=SALT)])
        Refund.objects.create(payment=payment, amount=100000, reason='Part', created_by=self.admin)
        response = self.client.get(url)
        self.assertContains(response, "To'lov qisman qaytarilgan")
        self.assertContains(response, "-100 000 so'm")
        self.assertContains(response, "200 000 so'm")
        self.assertNotContains(response, 'class="verified-mark"')
        Refund.objects.create(payment=payment, amount=200000, reason='Rest', created_by=self.admin)
        response = self.client.get(url)
        self.assertContains(response, "To'lov qaytarilgan")
        self.assertNotContains(response, 'class="verified-mark"')

    def test_invalid_verification_never_shows_success(self):
        payment = self.payment('2026-11', '2026-11-14T13:26:00')
        token = signing.dumps(payment.pk, salt=SALT)
        for invalid in (token + 'broken', signing.dumps(99999999, salt=SALT)):
            with self.subTest(token=invalid):
                response = self.client.get(reverse('payment_verify', args=[invalid]))
                self.assertContains(response, 'Chek tasdiqlanmadi', status_code=404)
                self.assertContains(response, 'Chek haqiqiyligi tasdiqlanmadi', status_code=404)
                self.assertNotContains(response, 'class="verified-mark"', status_code=404)
                self.assertNotContains(response, 'CHEK HAQIQIY', status_code=404)

    @override_settings(QR_VERIFY_BASE_URL='https://crm.example.test/', TELEGRAM_PUBLIC_URL='https://bot.example.test')
    def test_qr_opens_public_crm_verification_without_login(self):
        payment = self.payment('2026-11', '2026-11-14T13:26:00', amount=600000)
        self.client.force_login(self.admin)
        receipt = self.client.get(reverse('payment_receipt', args=[payment.pk]))
        url = receipt.context['verification_url']
        self.assertEqual(urlsplit(url).netloc, 'crm.example.test')
        self.assertEqual(receipt.context['receipt_qr_data_uri'], qr_image_data_uri(url))
        self.client.logout()
        response = self.client.get(urlsplit(url).path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CHEK HAQIQIY')
        self.assertContains(response, payment.receipt_number)
        self.assertContains(response, "600 000 SO'M")
