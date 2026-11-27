"""Real Chromium -> HTTP -> PostgreSQL payment workflow on an isolated live server."""
import os
from pathlib import Path
import re
from unittest import skipUnless
from urllib.parse import urlsplit

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from .models import FinancialAudit, Payment, Salary
from .test_project_qa import fixtures

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@skipUnless(sync_playwright and os.environ.get('RECEIPT_PRINT_CHROMIUM'), 'Live browser QA requires Chromium and Playwright')
@override_settings(TELEGRAM_BOT_TOKEN='', CRM_BACKGROUND_JOBS=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FinancialBrowserQATests(StaticLiveServerTestCase):
    def test_login_select_student_pay_receipt_dashboard_refresh_and_relogin(self):
        owner, teacher, _, _, _ = fixtures()
        errors, failed_local_responses = [], []
        host = urlsplit(self.live_server_url).netloc
        with sync_playwright() as playwright, playwright.chromium.launch(
            headless=True, executable_path=os.environ['RECEIPT_PRINT_CHROMIUM'],
        ) as browser:
            page = browser.new_page(viewport={'width': 1360, 'height': 900})
            page.set_default_timeout(10000)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('response', lambda response: failed_local_responses.append((response.status, response.url))
                    if urlsplit(response.url).netloc == host and response.status >= 400 else None)

            def route_asset(route):
                url = route.request.url
                if urlsplit(url).netloc == host:
                    route.continue_()
                elif 'jquery.min.js' in url:
                    route.fulfill(path=finders.find('admin/js/vendor/jquery/jquery.min.js'), content_type='application/javascript')
                elif 'select2.min.js' in url:
                    route.fulfill(path=finders.find('admin/js/vendor/select2/select2.full.min.js'), content_type='application/javascript')
                elif 'select2.min.css' in url:
                    route.fulfill(path=finders.find('admin/css/vendor/select2/select2.min.css'), content_type='text/css')
                else:
                    # Fonts, icons and Chart.js are outside this form/HTTP workflow.
                    route.fulfill(body='', content_type='text/css' if '.css' in url else 'application/javascript')

            page.route('**/*', route_asset)

            def login():
                page.goto(self.live_server_url + reverse('login'))
                page.fill('#id_username', 'qa-owner')
                page.fill('#id_password', 'qa-test-password')
                page.click('#loginBtn')
                page.wait_for_url(self.live_server_url + '/')

            login()
            page.goto(self.live_server_url + reverse('payment_create'))
            page.click('#select2-id_student-container')
            page.fill('.select2-search__field', 'QA Student')
            page.locator('.select2-results__option').filter(has_text='QA Student').last.click()
            page.fill('#id_amount', '150000')
            page.fill('#id_month', '2026-11')
            page.fill('#id_paid_date', '2026-11-20T10:00')
            page.get_by_role('button', name='Saqlash').click()
            page.wait_for_url(re.compile(r'/payments/\d+/receipt/\?created=1$'))
            self.assertIn('150000', page.locator('.total-amount').inner_text().replace(' ', ''))
            page.goto(self.live_server_url + '/')
            income = lambda: page.locator('.stat-info').filter(
                has=page.get_by_text('Bu oylik tushum', exact=True),
            ).locator('.stat-value').inner_text()
            self.assertEqual(income(), '150000')
            page.reload()
            self.assertEqual(income(), '150000')
            page.goto(self.live_server_url + reverse('logout'))
            login()
            self.assertEqual(income(), '150000')
            artifact = os.environ.get('RECEIPT_PRINT_ARTIFACTS')
            if artifact:
                path = Path(artifact)
                path.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(path / 'financial-live-dashboard.png'), full_page=True)
        self.assertEqual(errors, [])
        self.assertEqual(failed_local_responses, [])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.get().amount, 150000)
        self.assertEqual(Salary.objects.get(teacher=teacher).salary_amount, 60000)
        self.assertEqual(FinancialAudit.objects.get(entity='payment', action='create').actor, owner)
