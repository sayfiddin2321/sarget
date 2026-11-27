from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(TELEGRAM_BOT_TOKEN='', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AdminPageSmokeTests(TestCase):
    def test_main_pages_render_for_superadmin(self):
        admin = get_user_model().objects.create_superuser('page-admin', password='test')
        self.client.force_login(admin)
        names = (
            'dashboard', 'student_list', 'student_create', 'teacher_list', 'teacher_create',
            'receptionist_list', 'receptionist_create', 'course_list', 'course_create',
            'group_list', 'group_create', 'schedule', 'payment_list', 'payment_create',
            'salary_list', 'calculate_salaries', 'receptionist_salary_list',
            'calculate_receptionist_salaries', 'attendance_list', 'take_attendance_select',
            'grade_list', 'take_grades_select', 'assignment_history', 'expense_list',
            'expense_create', 'reports', 'report_center', 'report_jobs', 'notification_list',
            'global_search', 'academic_center', 'staff_center', 'learning_center', 'salary_center',
            'period_payroll', 'financial_migration', 'certificate_list',
        )
        for name in names:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertIn(response.status_code, (200, 302))
