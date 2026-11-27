"""Optional browser regression: clearing the bell must keep the full history."""
import os
from datetime import datetime
from pathlib import Path
from unittest import skipUnless
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Notification

try:
    from playwright.sync_api import sync_playwright, expect
except ImportError:
    sync_playwright = None


@skipUnless(sync_playwright and os.environ.get('NOTIFICATION_TEST_CHROMIUM'),
            'Browser history check requires playwright and NOTIFICATION_TEST_CHROMIUM')
@override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_BOT_MODE='disabled',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NotificationHistoryBrowserTests(LiveServerTestCase):
    def test_filter_read_and_clear_bell_keep_history_on_desktop_and_mobile(self):
        admin = get_user_model().objects.create_superuser('history-browser', password='test')
        for title, date_string, read in (
            ('Old message kept in history', '2026-11-10T12:00:00', True),
            ('Payment reminder to read', '2026-11-20T12:00:00', False),
            ('Another day reminder', '2026-11-21T12:00:00', False),
        ):
            item = Notification.objects.create(recipient=admin, title=title, message='Daily notification text', is_read=read)
            Notification.objects.filter(pk=item.pk).update(created_at=timezone.make_aware(datetime.fromisoformat(date_string)))
        self.client.force_login(admin)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        artifacts = Path(settings.BASE_DIR) / 'artifacts' / 'notification-history'
        artifacts.mkdir(parents=True, exist_ok=True)
        origin = urlsplit(self.live_server_url).netloc

        with sync_playwright() as playwright, playwright.chromium.launch(
            headless=True, executable_path=os.environ['NOTIFICATION_TEST_CHROMIUM'],
        ) as browser:
            page = browser.new_page(viewport={'width': 1360, 'height': 900})
            page.set_default_timeout(6000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))

            def serve_assets(route):
                parsed = urlsplit(route.request.url)
                if parsed.netloc != origin:
                    route.abort()
                elif parsed.path.startswith('/static/'):
                    asset = Path(settings.BASE_DIR) / 'core' / 'static' / parsed.path.removeprefix('/static/')
                    if asset.is_file():
                        route.fulfill(path=str(asset))
                    else:
                        route.abort()
                else:
                    route.continue_()

            page.route('**/*', serve_assets)
            page.context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': self.live_server_url}])
            page.goto(self.live_server_url + reverse('notification_list'))
            expect(page.locator('.notification-history-item')).to_have_count(3)
            page.fill('#id_date_from', '2026-11-10')
            page.fill('#id_date_to', '2026-11-20')
            page.get_by_role('button', name="Ko'rsatish", exact=True).click()
            expect(page.locator('.notification-history-item')).to_have_count(2)
            reminder = page.locator('.notification-history-item').filter(has_text='Payment reminder to read')
            reminder.get_by_role('button', name="O'qildi deb belgilash").click()
            expect(reminder.locator('.notification-history-meta')).to_contain_text("O'qilgan")
            page.locator('#notificationBell').click()
            page.locator('#notificationClearAll').click()
            expect(page.locator('#notificationStatus')).to_contain_text('tarixda saqlandi')
            page.get_by_role('link', name='Barcha tarix', exact=True).click()
            expect(page.locator('.notification-history-item')).to_have_count(3)
            expect(page.locator('.notification-history-item.is-unread')).to_have_count(0)
            page.reload()
            expect(page.locator('.notification-history-item')).to_have_count(3)
            page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.wait_for_function("getComputedStyle(document.querySelector('.main-content')).marginLeft === '0px' && document.querySelector('.sidebar').getBoundingClientRect().right <= 1")
            page.screenshot(path=str(artifacts / 'mobile.png'), full_page=True)
            overflow = page.evaluate("""() => [...document.querySelectorAll('body *')].filter(el => {
                const r=el.getBoundingClientRect(); return r.width && r.right > innerWidth+1;
            }).map(el => ({tag:el.tagName, cls:el.className, right:el.getBoundingClientRect().right})).slice(0,20)""")
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390, overflow)
            self.assertEqual(errors, [])

        self.assertEqual(Notification.objects.filter(recipient=admin).count(), 3)
        self.assertFalse(Notification.objects.filter(recipient=admin, is_read=False).exists())
