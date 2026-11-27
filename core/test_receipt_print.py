"""Optional Chromium print checks: see docs/RECEIPT_PRINTING.md."""
import os
from datetime import date, time
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest import skipUnless
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Course, Group, Payment, Student, Teacher

try:
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader
except ImportError:
    sync_playwright = None


@skipUnless(sync_playwright, 'Optional print checks require playwright and pypdf')
@override_settings(TELEGRAM_BOT_TOKEN='', QR_VERIFY_BASE_URL='https://crm.example.test',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReceiptPrintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('print-admin', password='test')
        teacher = Teacher.objects.create(name='Test Teacher', percent=40)
        course = Course.objects.create(name='Python dasturlash')
        group = Group.objects.create(name='Python-01', course=course, teacher=teacher,
                                     start_time=time(9), end_time=time(11))
        cls.student = Student.objects.create(name='Test Student', teacher=teacher, group=group,
                                             phone='+998901234567')
        cls.payment = Payment.objects.create(student=cls.student, amount=Decimal('600000'),
                                             month=date(2026, 11, 1), received_by=cls.admin)

    def test_thermal_print_geometry_and_browser_controls(self):
        self.client.force_login(self.admin)
        artifacts = os.environ.get('RECEIPT_PRINT_ARTIFACTS')
        # Render before Playwright starts its event loop: Django ORM is synchronous.
        receipts = []
        for scenario in ('normal', 'long', 'void'):
            if scenario == 'long':
                self.student.name = 'Abdurahmonov Muhammadali Abdurahmonovich ' * 3
                self.student.save()
                self.payment.amount = Decimal('9999999999.99')
                self.payment.comment = 'Uzun izoh ' * 50 + ' https://example.test/' + 'a' * 180
                self.payment.save()
            elif scenario == 'void':
                self.payment.void('Sinov uchun bekor qilindi ' * 6)
            response = self.client.get(reverse('payment_receipt', args=[self.payment.pk]) + '?created=1')
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            self.assertIn('Python dasturlash', html)
            receipts.append((scenario, html))
        options = {'headless': True}
        if os.environ.get('RECEIPT_PRINT_CHROMIUM'):
            options['executable_path'] = os.environ['RECEIPT_PRINT_CHROMIUM']
        with sync_playwright() as playwright, playwright.chromium.launch(**options) as browser:
            for scenario, html in receipts:
                for width in (80, 58):
                    with self.subTest(scenario=scenario, width=width):
                        page = browser.new_page(viewport={'width': 240, 'height': 720})
                        page.set_default_timeout(5000)
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' and 'Receipt' in message.text else None)

                        def route_request(route):
                            path = urlsplit(route.request.url).path
                            if path.startswith('/static/'):
                                relative = path.removeprefix('/static/')
                                asset = Path(settings.BASE_DIR) / 'core' / 'static' / relative
                                route.fulfill(path=str(asset))
                            elif path.startswith('/payments/'):
                                route.fulfill(body=html, content_type='text/html')
                            else:
                                route.abort()

                        page.route('**/*', route_request)
                        page.goto('http://receipt.test' + reverse('payment_receipt', args=[self.payment.pk]))
                        page.select_option('#receiptPaperWidth', str(width))
                        page.evaluate('waitForReceiptImages()')
                        page.evaluate('() => { window.print = () => { window.printCalls = (window.printCalls || 0) + 1; }; }')
                        page.click('#btnPrintReceipt')
                        try:
                            page.wait_for_function("window.printCalls === 1 && !document.getElementById('btnPrintReceipt').disabled")
                        except Exception:
                            self.fail(f'Print did not start: {errors}; ' + str(page.evaluate("({calls: window.printCalls, disabled: document.getElementById('btnPrintReceipt').disabled})")))
                        self.assertFalse(page.is_disabled('#btnPrintReceipt'))
                        self.assertFalse(page.is_disabled('#receiptPaperWidth'))
                        if scenario == 'normal' and width == 80:
                            # A slow logo must hold printing until its image is decoded.
                            pending = []
                            page.route('**/pending-logo.png', lambda route: pending.append(route))
                            page.evaluate("document.querySelector('.receipt-logo-img').src = '/pending-logo.png'")
                            page.click('#btnPrintReceipt')
                            self.assertTrue(page.is_disabled('#btnPrintReceipt'))
                            self.assertEqual(page.evaluate('window.printCalls'), 1)
                            self.assertEqual(len(pending), 1)
                            pending[0].fulfill(path=str(Path(settings.BASE_DIR) / 'core/static/img/logo_icon_tight.png'))
                            page.wait_for_function("window.printCalls === 2 && !document.getElementById('btnPrintReceipt').disabled")
                            page.evaluate('window.printCalls = 1')
                        page.keyboard.press('Control+p')
                        page.wait_for_function('window.printCalls === 2')
                        self.assertEqual(page.evaluate('localStorage.getItem(receiptPaperStorageKey)'), str(width))
                        # Include native beforeprint; measurement must work in print media too.
                        page.emulate_media(media='print')
                        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
                        layout = page.evaluate("""() => {
                            const card = document.getElementById('receiptCard');
                            const rect = card.getBoundingClientRect();
                            return {
                                top: rect.top, width: rect.width, height: rect.height,
                                overflow: [...card.querySelectorAll('*')].filter(el => {
                                    const r = el.getBoundingClientRect();
                                    return r.left < rect.left - 1 || r.right > rect.right + 1;
                                }).map(el => el.className),
                                controls: getComputedStyle(document.querySelector('.receipt-print-settings')).display,
                                sidebar: getComputedStyle(document.querySelector('.sidebar')).display,
                                qr: document.getElementById('receiptQrImage').getBoundingClientRect().width
                            };
                        }""")
                        self.assertAlmostEqual(layout['top'], 0, delta=0.1)
                        self.assertAlmostEqual(layout['width'] * 25.4 / 96, 48 if width == 58 else 72, delta=0.1)
                        self.assertAlmostEqual(layout['qr'] * 25.4 / 96, 30, delta=0.1)
                        self.assertEqual(layout['overflow'], [])
                        self.assertEqual(layout['controls'], 'none')
                        self.assertEqual(layout['sidebar'], 'none')
                        # Keep browser headers enabled here to verify zero page margins suppress them.
                        pdf = page.pdf(prefer_css_page_size=True, display_header_footer=True)
                        document = PdfReader(BytesIO(pdf))
                        self.assertEqual(len(document.pages), 1)
                        paper = document.pages[0]
                        self.assertAlmostEqual(float(paper.mediabox.width) * 25.4 / 72, width, delta=0.4)
                        self.assertAlmostEqual(float(paper.mediabox.height) * 25.4 / 72,
                                               layout['height'] * 25.4 / 96 + 0.5, delta=0.4)
                        text = paper.extract_text()
                        self.assertIn(self.payment.receipt_number, text)
                        self.assertIn('Python dasturlash', text)
                        self.assertIn('tashakkur', text)
                        self.assertNotIn('receipt.test', text)
                        self.assertNotIn('1/1', text)
                        self.assertNotIn('More settings', text)
                        self.assertIn('BEKOR QILINGAN' if scenario == 'void' else "TO'LANDI", text)
                        self.assertEqual(errors, [])
                        if artifacts:
                            directory = Path(artifacts)
                            directory.mkdir(parents=True, exist_ok=True)
                            name = f'receipt-{scenario}-{width}mm'
                            (directory / f'{name}.pdf').write_bytes(pdf)
                            page.locator('#receiptCard').screenshot(path=str(directory / f'{name}.png'))
                        page.close()
