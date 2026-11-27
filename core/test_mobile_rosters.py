"""Optional browser layout checks for long admission and student names."""
import os
from datetime import time
from pathlib import Path
from unittest import skipUnless
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Group, Lead, Receptionist, Student, Teacher

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@skipUnless(sync_playwright and os.environ.get('ROSTER_TEST_CHROMIUM'),
            'Roster browser checks require playwright and ROSTER_TEST_CHROMIUM')
@override_settings(TELEGRAM_BOT_TOKEN='', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MobileRosterLayoutTests(TestCase):
    def test_long_names_remain_readable_and_boards_scroll_instead_of_shrinking(self):
        admin = get_user_model().objects.create_superuser('roster-browser', password='test')
        teacher = Teacher.objects.create(name='Abdurahmonov Muhammadali Abdurahmonovich', percent=40)
        receptionist = Receptionist.objects.create(name='Muhammadjonova Shahrizoda Abdurahmonovna')
        group = Group.objects.create(name='Python backend dasturlash boshlangich guruh', teacher=teacher,
                                     monthly_fee=490000, start_time=time(9), end_time=time(10))
        long_name = 'Abdurahmonov Muhammadali Abdurahmonovich Sayfiddinov'
        Student.objects.create(name=long_name, teacher=teacher, receptionist=receptionist, group=group,
                               phone='+998901234567', parent_phone='+998909876543')
        for index in range(5):
            Lead.objects.create(name=long_name, course='Python backend dasturlash va suniy intellekt asoslari',
                                phone='+998901234567', status='new', assigned_to=admin)
        Lead.objects.create(name='JudaUzunIsmFamiliya' * 6, course='DasturlashKursiningUzunNomi' * 4,
                            status='callback', phone='+998909876543')
        self.client.force_login(admin)
        documents = {}
        for route_name in ('lead_list', 'student_list'):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200)
            documents[reverse(route_name)] = response.content.decode()
        artifacts = Path(settings.BASE_DIR) / 'artifacts' / 'mobile-rosters'
        artifacts.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright, playwright.chromium.launch(
            headless=True, executable_path=os.environ['ROSTER_TEST_CHROMIUM'],
        ) as browser:
            for width in (320, 390, 768, 1360):
                for theme in ('light', 'dark'):
                    with self.subTest(width=width, theme=theme):
                        page = browser.new_page(viewport={'width': width, 'height': 900})
                        page.add_init_script(f"localStorage.setItem('sargetcrm_theme', '{theme}')")
                        page.set_default_timeout(5000)
                        script_errors = []
                        page.on('pageerror', lambda error: script_errors.append(str(error)))

                        def route_request(route):
                            parsed = urlsplit(route.request.url)
                            if parsed.path in documents and parsed.netloc == 'roster.test':
                                route.fulfill(body=documents[parsed.path], content_type='text/html')
                            elif parsed.path.startswith('/static/') and parsed.netloc == 'roster.test':
                                asset = Path(settings.BASE_DIR) / 'core' / 'static' / parsed.path.removeprefix('/static/')
                                if asset.is_file():
                                    route.fulfill(path=str(asset))
                                else:
                                    route.abort()
                            elif parsed.path == reverse('notification_poll'):
                                route.fulfill(json={'notifications': [], 'unread_count': 0, 'cursor': 0})
                            else:
                                route.abort()

                        page.route('**/*', route_request)
                        page.goto('http://roster.test' + reverse('lead_list'))
                        board = page.locator('.lead-board').evaluate("""el => ({
                            width:el.clientWidth, scroll:el.scrollWidth,
                            columns:[...el.querySelectorAll('.lead-column')].map(c => c.getBoundingClientRect().width),
                            nameWidth:el.querySelector('.lead-name').getBoundingClientRect().width
                        })""")
                        self.assertGreaterEqual(min(board['columns']), 200, board)
                        self.assertGreater(board['scroll'], board['width'])
                        self.assertGreaterEqual(board['nameWidth'], 150, board)
                        page.locator('.lead-board').evaluate('el => { el.scrollLeft=260; }')
                        self.assertGreater(page.locator('.lead-board').evaluate('el => el.scrollLeft'), 0)
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                        page.locator('.lead-board').evaluate('el => { el.scrollLeft=0; }')
                        if width in (320, 390, 1360) and theme == 'light':
                            page.screenshot(path=str(artifacts / f'admissions-{width}.png'), full_page=True, animations='disabled')

                        page.goto('http://roster.test' + reverse('student_list'))
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                        name = page.locator('.student-table .entity-name').first
                        self.assertGreaterEqual(name.bounding_box()['width'], 150)
                        if width <= 1100:
                            metrics = page.locator('.student-table').evaluate('el => ({width:el.clientWidth,scroll:el.scrollWidth})')
                            self.assertLessEqual(metrics['scroll'], metrics['width'] + 1, metrics)
                        if width in (320, 390, 1360) and theme == 'light':
                            page.screenshot(path=str(artifacts / f'students-{width}.png'), full_page=True, animations='disabled')
                        self.assertEqual(script_errors, [])
                        page.close()
