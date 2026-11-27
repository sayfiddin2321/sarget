from datetime import date, time
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Group, Receptionist, ReceptionistSalary, Salary, StaffCapability, Student, Teacher


class SidebarLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.in_sidebar = False
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'nav':
            self.in_sidebar = attrs.get('class') == 'sidebar-nav'
        elif tag == 'a' and self.in_sidebar:
            self.links.append(attrs.get('href'))

    def handle_endtag(self, tag):
        if tag == 'nav':
            self.in_sidebar = False


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class UnifiedCentersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser('center-admin', 'admin@example.test', 'secret')
        cls.teacher_user = users.objects.create_user('center-teacher')
        cls.rec_user = users.objects.create_user('center-reception')
        cls.teacher = Teacher.objects.create(user=cls.teacher_user, name='Teacher for center')
        cls.other_teacher = Teacher.objects.create(name='Other teacher for center')
        cls.rec = Receptionist.objects.create(user=cls.rec_user, name='Reception for center')
        cls.group = Group.objects.create(name='Center group', teacher=cls.teacher, monthly_fee=500000,
                                         start_time=time(9), end_time=time(10))
        cls.student = Student.objects.create(name='Center student', phone='+998901234567', teacher=cls.teacher, group=cls.group)

    def test_navigation_uses_one_entry_for_each_combined_section(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'))
        links = SidebarLinks(response.content.decode()).links
        for name in ('staff_center', 'learning_center', 'salary_center', 'academic_center'):
            self.assertEqual(links.count(reverse(name)), 1)
        for name in ('teacher_list', 'receptionist_list', 'group_list', 'course_list', 'salary_list', 'receptionist_salary_list', 'attendance_list', 'grade_list'):
            self.assertNotIn(reverse(name), links)

    def test_all_combined_tabs_and_legacy_pages_share_navigation(self):
        self.client.force_login(self.admin)
        for center, tabs in (('staff_center', ('teachers', 'receptionists')),
                             ('learning_center', ('groups', 'courses')),
                             ('salary_center', ('teachers', 'receptionists')),
                             ('academic_center', ('attendance', 'grades'))):
            for tab in tabs:
                response = self.client.get(reverse(center), {'tab': tab})
                self.assertEqual(response.status_code, 200, (center, tab))
                self.assertEqual(response.context['navigation_section'], center)
                active = [item for item in response.context['center_tabs'] if item['active']]
                self.assertEqual(len(active), 1)
                self.assertEqual(parse_qs(urlsplit(active[0]['url']).query)['tab'], [tab])
        for legacy, center in (('teacher_list', 'staff_center'), ('receptionist_list', 'staff_center'),
                               ('group_list', 'learning_center'), ('course_list', 'learning_center'),
                               ('salary_list', 'salary_center'), ('receptionist_salary_list', 'salary_center'),
                               ('attendance_list', 'academic_center'), ('grade_list', 'academic_center')):
            response = self.client.get(reverse(legacy))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['navigation_section'], center)

    def test_academic_tabs_preserve_permissions_and_shared_filters(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('academic_center'), {'tab': 'grades', 'group': self.group.pk, 'date': '2026-10-31'})
        self.assertEqual(response.status_code, 200)
        for tab in response.context['center_tabs']:
            query = parse_qs(urlsplit(tab['url']).query)
            self.assertEqual(query['group'], [str(self.group.pk)])
            self.assertEqual(query['date'], ['2026-10-31'])
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('academic_center'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([tab['label'] for tab in response.context['center_tabs']], ['Davomat'])
        self.assertEqual(self.client.get(reverse('academic_center'), {'tab': 'grades'}).status_code, 403)
        StaffCapability.objects.create(user=self.rec_user, code='attendance.view', allowed=False)
        self.assertEqual(self.client.get(reverse('academic_center')).status_code, 403)

    def test_only_permitted_tabs_are_visible_and_direct_access_is_blocked(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('learning_center'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([tab['label'] for tab in response.context['center_tabs']], ['Guruhlar'])
        self.assertEqual(self.client.get(reverse('learning_center'), {'tab': 'courses'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('staff_center')).status_code, 403)
        self.assertEqual(self.client.get(reverse('learning_center'), {'tab': 'unknown'}).status_code, 400)
        StaffCapability.objects.create(user=self.rec_user, code='receptionists.view', allowed=True)
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('staff_center'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([tab['label'] for tab in response.context['center_tabs']], ['Retsepshen'])
        self.assertEqual(self.client.get(reverse('staff_center'), {'tab': 'teachers'}).status_code, 403)

    def test_payroll_center_preserves_private_salary_scope_and_month(self):
        own = Salary.objects.create(teacher=self.teacher, month=date(2026, 10, 1), total_income=25000, percent=40, salary_amount=10000)
        Salary.objects.create(teacher=self.other_teacher, month=date(2026, 10, 1), total_income=50000, percent=40, salary_amount=20000)
        StaffCapability.objects.create(user=self.teacher_user, code='salary.teacher_self.view', allowed=True)
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('salary_center'), {'month': '2026-10'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['salaries']), [own])
        self.assertEqual(len(response.context['center_tabs']), 1)
        self.assertIn('month=2026-10', response.context['center_tabs'][0]['url'])
        self.assertEqual(self.client.get(reverse('salary_center'), {'tab': 'receptionists'}).status_code, 403)
        StaffCapability.objects.create(user=self.rec_user, code='salary.receptionist_self.view', allowed=True)
        rec_salary = ReceptionistSalary.objects.create(receptionist=self.rec, month=date(2026, 10, 1), total_salary=50000)
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('salary_center'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['salaries']), [rec_salary])

    def test_report_builder_preserves_filters_and_hides_internal_preview_ids(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('report_center'), {'kind': 'students', 'group': self.group.pk, 'month': '2026-10'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Center student')
        self.assertNotIn('UUID', response.context['headers'])
        self.assertIn('UUID', response.context['report'].sheets()[0].headers)
        self.assertEqual(len(response.context['headers']), len(response.context['preview_rows'][0]))
        self.assertContains(response, 'name="kind" value="students"')
        preset = parse_qs(urlsplit(response.context['period_presets'][0]['url']).query)
        self.assertEqual(preset['group'], [str(self.group.pk)])
        self.assertEqual(preset['kind'], ['students'])
        self.assertNotIn('month', preset)
        response = self.client.get(reverse('report_center'), {'date_from': '2026-10-31', 'date_to': '2026-10-01'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'role="alert"', status_code=400)

    def test_report_controls_follow_export_and_finance_permissions(self):
        StaffCapability.objects.create(user=self.teacher_user, code='reports.export', allowed=False)
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('report_center'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('report_jobs'))
        self.assertNotContains(response, 'id="reportFormat"')
        options = {item['key'] for group in response.context['report_options'] for item in group['items']}
        self.assertNotIn('payments', options)
        self.assertNotIn('leads', options)
        self.assertEqual(self.client.get(reverse('report_center'), {'kind': 'payments'}).status_code, 403)
