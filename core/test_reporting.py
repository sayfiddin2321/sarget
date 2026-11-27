import json
import zipfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from docx import Document

from .accounts import student_accounts
from .models import (Attendance, Branch, Campaign, Course, Enrollment, Grade, Group, GuardianBinding,
                     ImportBatch, Lead, Notification, Payment, ReceptionistSalary, Refund, ReportJob, ReportSubscription,
                     Salary, TelegramLinkToken,
                     StaffCapability, Student, Teacher, Receptionist, TelegramBinding, TelegramDelivery)
from .permissions import (RECEPTIONIST_OWN_SALARY, TEACHER_OWN_SALARY, get_role, has_capability)
from .reporting import Report
from .report_files import build_file, create_job, generate_job, private_path, validate_job_access
from .report_imports import HEADERS, confirm_batch, digest, validate_rows
from .messaging import queue_student_report, queue_subscriptions, process_deliveries
from .reminders import dispatch_student_payment_reminders
from .telegram_linking import issue_link_code, redeem_link_code
from .telegram_bot import process_update, registration_reply


@override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_STAFF_CHAT_ID='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReportingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser('admin-reports', 'admin@example.test', 'secret')
        cls.teacher_user = User.objects.create_user('teacher-reports')
        cls.rec_user = User.objects.create_user('rec-reports')
        cls.staff = User.objects.create_user('staff-only', is_staff=True)
        cls.teacher = Teacher.objects.create(user=cls.teacher_user, name='Teacher one')
        cls.other_teacher = Teacher.objects.create(name='Teacher two')
        cls.rec = Receptionist.objects.create(user=cls.rec_user, name='Reception')
        cls.branch = Branch.objects.create(name='Branch one')
        cls.other_branch = Branch.objects.create(name='Branch two')
        cls.course = Course.objects.create(name='Python')
        cls.other_course = Course.objects.create(name='English')
        cls.group = Group.objects.create(name='Python A', teacher=cls.teacher, branch=cls.branch, course=cls.course,
                                        monthly_fee=500000, start_time=time(9), end_time=time(10))
        cls.other_group = Group.objects.create(name='English B', teacher=cls.other_teacher, branch=cls.other_branch,
                                              course=cls.other_course, monthly_fee=300000, start_time=time(11), end_time=time(12))
        cls.today = timezone.localdate()
        cls.start = cls.today.replace(day=1)
        cls.student = Student.objects.create(name='Ali Report', phone='+998901234567', parent_phone='+998909999999',
                                             group=cls.group, teacher=cls.teacher, receptionist=cls.rec,
                                             branch=cls.branch, registration_date=cls.start)
        cls.foreign = Student.objects.create(name='Foreign Report', phone='+998901112233',
                                             group=cls.other_group, teacher=cls.other_teacher, branch=cls.other_branch)
        cls.attendance = Attendance.objects.create(student=cls.student, group=cls.group, date=cls.today, status='late', note='Valid attendance')
        cls.grade = Grade.objects.create(student=cls.student, group=cls.group, date=cls.today, score=90, grade_type='classwork', note='Valid grade')

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings_override = override_settings(BASE_DIR=Path(directory.name))
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def params(self, **extra):
        return dict({'date_from': self.start.isoformat(), 'date_to': self.today.isoformat()}, **extra)

    def upload(self, kind, rows):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = kind
        worksheet.append(HEADERS[kind])
        for row in rows:
            worksheet.append(row)
        stream = BytesIO()
        workbook.save(stream)
        return SimpleUploadedFile('import.xlsx', stream.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_new_pages_render_for_each_role(self):
        for user in (self.admin, self.rec_user, self.teacher_user):
            self.client.force_login(user)
            for name in ('report_center', 'report_jobs', 'group_list', 'student_list'):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200, (user.username, name))
            self.assertEqual(self.client.get(reverse('student_report', args=[self.student.pk])).status_code, 200)
        self.client.force_login(self.admin)
        for name in ('staff_permissions', 'report_settings', 'system_status'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_strict_superadmin_and_capability_revocation(self):
        self.assertEqual(get_role(self.staff), 'unknown')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('staff_permissions')).status_code, 403)
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(reverse('payment_list')).status_code, 200)
        StaffCapability.objects.create(user=self.rec_user, code='payments.view', allowed=False)
        self.assertEqual(self.client.get(reverse('payment_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('report_center'), {'kind': 'payments'}).status_code, 403)

    def test_student_report_page_shows_simplified_telegram_flow(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('student_report', args=[self.student.pk]), self.params())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hisobotni ko'rsatish")
        self.assertContains(response, 'Telegramni ulash yoki qayta ulash')
        self.assertContains(response, 'Yuborish holati')
        self.assertNotContains(response, 'Telegram chat ID')

    def test_staff_can_send_a_message_to_a_chosen_linked_student_recipient(self):
        binding = TelegramBinding.objects.create(role='student', target_id=self.student.pk, chat_id=612345)
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('student_detail', args=[self.student.pk]))
        self.assertContains(response, reverse('student_telegram_message', args=[self.student.pk]))
        self.assertContains(response, 'Davomat va baho hisobotini yuborish')

        response = self.client.post(reverse('student_telegram_message', args=[self.student.pk]), {
            'recipient': f'student:{binding.pk}',
            'text': 'Assalomu alaykum, to‘lovni eslatamiz.',
        })

        self.assertRedirects(response, reverse('student_detail', args=[self.student.pk]))
        delivery = TelegramDelivery.objects.get(student=self.student, report_job__isnull=True)
        self.assertEqual(delivery.chat_id, binding.chat_id)
        self.assertEqual(delivery.owner, self.rec_user)
        self.assertEqual(delivery.text, 'Assalomu alaykum, to‘lovni eslatamiz.')

        binding.reports_enabled = False
        binding.save(update_fields=['reports_enabled'])
        self.client.post(reverse('student_telegram_message', args=[self.student.pk]), {
            'recipient': f'student:{binding.pk}',
            'text': 'This should not be sent.',
        })
        self.assertEqual(TelegramDelivery.objects.filter(student=self.student, report_job__isnull=True).count(), 1)

    def test_payment_reminders_cover_three_days_before_due_day_and_daily_overdue(self):
        today = self.today.replace(day=1)
        due_date = today.replace(day=4)
        student = Student.objects.create(
            name='Due soon student', group=self.group, teacher=self.teacher, receptionist=self.rec,
            registration_date=today, payment_due_day=due_date.day,
        )
        self.assertEqual(student.tariffs.get().due_day, due_date.day)

        def run_reminders(on_date):
            now = timezone.make_aware(datetime.combine(on_date, time(10)))
            dispatch_student_payment_reminders(now)

        self.client.force_login(self.rec_user)
        run_reminders(due_date - timedelta(days=4))
        self.assertFalse(Notification.objects.filter(student=student).exists())
        run_reminders(due_date - timedelta(days=3))
        run_reminders(due_date - timedelta(days=3))
        early = Notification.objects.filter(student=student, recipient=self.rec_user)
        self.assertEqual(early.count(), 1)
        self.assertEqual(early.first().title, "To'lov muddati yaqinlashmoqda")
        self.assertEqual(early.first().target_url, reverse('student_detail', args=[student.pk]))

        run_reminders(due_date)
        self.assertEqual(Notification.objects.filter(student=student, recipient=self.rec_user).count(), 2)
        run_reminders(due_date + timedelta(days=1))
        run_reminders(due_date + timedelta(days=1))
        overdue = Notification.objects.filter(student=student, recipient=self.rec_user)
        self.assertEqual(overdue.count(), 3)
        self.assertEqual(overdue.order_by('-created_at').first().title, "To'lov muddati o'tgan")

    def test_payment_reminder_finds_a_due_date_in_the_next_month(self):
        this_month = self.today.replace(day=1)
        next_month = date(
            this_month.year + (this_month.month == 12),
            this_month.month % 12 + 1,
            1,
        )
        due_date = next_month.replace(day=2)
        notify_date = due_date - timedelta(days=3)
        student = Student.objects.create(
            name='Next month student', group=self.group, teacher=self.teacher, receptionist=self.rec,
            registration_date=this_month, payment_due_day=due_date.day,
        )

        now = timezone.make_aware(datetime.combine(notify_date, time(10)))
        dispatch_student_payment_reminders(now)

        notification = Notification.objects.get(
            student=student, recipient=self.rec_user,
            title="To'lov muddati yaqinlashmoqda",
        )
        self.assertIn(f'Muddat: {due_date:%d.%m.%Y}', notification.message)

    def test_admin_can_grant_and_revoke_private_salary_visibility(self):
        teacher_salary = Salary.objects.create(
            teacher=self.teacher, month=self.start, total_income=100000,
            percent=40, salary_amount=40000,
        )
        Salary.objects.create(
            teacher=self.other_teacher, month=self.start, total_income=200000,
            percent=50, salary_amount=100000,
        )
        other_receptionist = Receptionist.objects.create(name='Other reception')
        own_reception_salary = ReceptionistSalary.objects.create(
            receptionist=self.rec, month=self.start, base_salary=100000,
            total_commission=20000, total_salary=120000,
        )
        ReceptionistSalary.objects.create(
            receptionist=other_receptionist, month=self.start, total_salary=300000,
        )

        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.get(reverse('salary_list')).status_code, 403)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Bu oylik maoshim')
        self.assertIsNone(response.context['month_salary'])
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(reverse('receptionist_salary_list')).status_code, 403)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Mening oyligim')

        self.client.force_login(self.admin)
        response = self.client.get(reverse('staff_permissions'), {'user': self.teacher_user.pk})
        teacher_codes = {row['code'] for row in response.context['permission_rows']}
        self.assertIn(TEACHER_OWN_SALARY, teacher_codes)
        self.assertNotIn(RECEPTIONIST_OWN_SALARY, teacher_codes)
        self.client.post(reverse('staff_permissions'), {
            'user': self.teacher_user.pk, 'capabilities': [TEACHER_OWN_SALARY],
        })
        response = self.client.get(reverse('staff_permissions'), {'user': self.rec_user.pk})
        receptionist_codes = {row['code'] for row in response.context['permission_rows']}
        self.assertIn(RECEPTIONIST_OWN_SALARY, receptionist_codes)
        self.assertNotIn(TEACHER_OWN_SALARY, receptionist_codes)
        self.client.post(reverse('staff_permissions'), {
            'user': self.rec_user.pk, 'capabilities': [RECEPTIONIST_OWN_SALARY],
        })

        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('salary_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['salaries']), [teacher_salary])
        self.assertContains(response, 'Mening oyligim')
        self.assertNotContains(response, 'Teacher two')
        self.assertNotContains(response, 'Oylik hisoblash')
        self.assertContains(self.client.get(reverse('dashboard')), 'Bu oylik maoshim')
        self.client.post(reverse('update_salary_status', args=[teacher_salary.pk]))
        teacher_salary.refresh_from_db()
        self.assertFalse(teacher_salary.is_paid)

        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('receptionist_salary_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['salaries']), [own_reception_salary])
        self.assertContains(response, 'Mening oyligim')
        self.assertNotContains(response, 'Other reception')
        self.assertNotContains(response, 'Hisoblash')
        self.assertContains(self.client.get(reverse('dashboard')), 'Mening oyligim')

        self.client.force_login(self.admin)
        self.client.post(reverse('staff_permissions'), {'user': self.teacher_user.pk})
        self.client.post(reverse('staff_permissions'), {'user': self.rec_user.pk})
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.get(reverse('salary_list')).status_code, 403)
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(reverse('receptionist_salary_list')).status_code, 403)

    def test_reception_can_edit_assign_and_see_all_but_cannot_grade(self):
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('student_list'))
        self.assertEqual(response.context['students'].paginator.count, 2)
        self.assertEqual(self.client.get(reverse('student_edit', args=[self.foreign.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('take_grades', args=[self.group.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('take_attendance', args=[self.group.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('enrollment_create', args=[self.student.pk])).status_code, 200)

    def test_teacher_scope_and_profile_fields_are_restricted(self):
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.get(reverse('student_report', args=[self.foreign.pk])).status_code, 404)
        response = self.client.get(reverse('report_center'), {'group': self.other_group.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(reverse('profile_edit')).status_code, 200)
        self.client.post(reverse('profile_edit'), {'name': 'Updated Teacher', 'phone': '+998907777777', 'notes': 'Profile', 'percent': 99, 'is_active': False})
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.name, 'Updated Teacher')
        self.assertEqual(self.teacher.percent, 40)
        self.assertTrue(self.teacher.is_active)
        self.teacher_user.refresh_from_db()
        self.assertEqual(self.teacher_user.get_full_name(), 'Updated Teacher')
        self.assertContains(self.client.get(reverse('dashboard')), 'Updated Teacher')

    def test_admin_can_edit_profile_name_and_sidebar_role_remains_visible(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('profile_edit'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('profile_edit'), {
            'first_name': 'Sardor',
            'last_name': 'Rahimov',
        })
        self.assertRedirects(response, reverse('profile_edit'))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.get_full_name(), 'Sardor Rahimov')

        dashboard = self.client.get(reverse('dashboard'))
        self.assertContains(dashboard, 'Sardor Rahimov')
        self.assertContains(dashboard, 'Boshliq')

    def test_staff_admin_can_view_all_crm_models_and_export_selected_records(self):
        student_changelist = reverse('admin:core_student_changelist')
        payment_changelist = reverse('admin:core_payment_changelist')
        self.client.force_login(self.staff)

        student_response = self.client.get(student_changelist)
        self.assertEqual(student_response.status_code, 200, student_response.content[:1000])
        payment_response = self.client.get(payment_changelist)
        self.assertEqual(payment_response.status_code, 200, payment_response.content[:1000])

        response = self.client.post(student_changelist, {
            'action': 'export_selected_xlsx',
            '_selected_action': [self.student.pk],
            'index': 0,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        self.assertIn('Ali Report', [cell for row in workbook.active.iter_rows(values_only=True) for cell in row])

        response = self.client.post(student_changelist, {
            'action': 'export_selected_docx',
            '_selected_action': [self.student.pk],
            'index': 0,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
        document = Document(BytesIO(response.content))
        document_text = [
            cell.text for row in document.tables[0].rows for cell in row.cells
        ]
        self.assertIn('Ali Report', document_text)

    def test_receptionist_profile_name_updates_header_without_changing_role(self):
        self.client.force_login(self.rec_user)
        response = self.client.post(reverse('profile_edit'), {
            'name': 'Dilnoza Karimova',
            'phone': '+998907777777',
            'notes': 'Updated profile',
        })
        self.assertRedirects(response, reverse('profile_edit'))

        self.rec_user.refresh_from_db()
        self.assertEqual(self.rec_user.get_full_name(), 'Dilnoza Karimova')
        dashboard = self.client.get(reverse('dashboard'))
        self.assertContains(dashboard, 'Dilnoza Karimova')
        self.assertContains(dashboard, 'Retsepshen')

    def test_revoked_academic_capability_is_hidden_on_student_card_and_dashboard(self):
        StaffCapability.objects.create(user=self.teacher_user, code='grades.view', allowed=False)
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('student_detail', args=[self.student.pk]))
        self.assertEqual(response.context['grades_count'], 0)
        self.assertNotContains(response, 'Valid grade')
        self.assertEqual(self.client.get(reverse('take_grades', args=[self.group.pk])).status_code, 403)
        StaffCapability.objects.create(user=self.teacher_user, code='students.view', allowed=False)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['my_students_count'], 0)
        self.assertEqual(self.client.get(reverse('global_search'), {'q': 'Ali'}).status_code, 403)

    def test_teacher_can_archive_only_own_students(self):
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.post(reverse('student_delete', args=[self.foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('student_delete', args=[self.student.pk])).status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, 'inactive')
        self.assertTrue(Attendance.objects.filter(pk=self.attendance.pk).exists())

    def test_report_counts_unique_people_and_enrollments(self):
        Enrollment.objects.create(student=self.student, group=self.other_group, starts_on=self.start, monthly_fee=300000)
        summary = Report(self.admin, 'students', self.params()).summary()
        self.assertEqual(summary['active_students'], 2)
        self.assertEqual(summary['active_enrollments'], 3)
        self.assertEqual(summary['new_students'], 2)

    def test_teacher_can_grade_student_in_their_second_enrollment(self):
        Enrollment.objects.create(student=self.foreign, group=self.group, starts_on=self.start, monthly_fee=500000)
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('take_grades', args=[self.group.pk]))
        self.assertIn(self.foreign.pk, {student.pk for student in response.context['students']})
        api = self.client.get(reverse('api_group_students', args=[self.group.pk]))
        self.assertIn(self.foreign.pk, {student['id'] for student in api.json()['students']})
        self.client.post(reverse('take_grades', args=[self.group.pk]), {'date': str(self.today), 'grade_type': 'classwork', f'score_{self.foreign.pk}': '92'})
        self.assertEqual(Grade.objects.get(student=self.foreign, group=self.group).score, 92)

    def test_new_student_is_first_enrollment_centerwide(self):
        primary = self.student.enrollments.get(is_primary=True)
        primary.starts_on = self.start - timedelta(days=100)
        primary.save()
        Enrollment.objects.create(student=self.student, group=self.other_group, starts_on=self.start)
        summary = Report(self.admin, 'students', self.params(student=str(self.student.pk), course=str(self.other_course.pk))).summary()
        self.assertEqual(summary['new_students'], 0)

    def test_all_filters_apply_to_exported_academic_rows(self):
        Attendance.objects.create(student=self.foreign, group=self.other_group, date=self.today, status='absent', note='Secret attendance')
        params = self.params(branch=str(self.branch.pk), course=str(self.course.pk), group=str(self.group.pk), teacher=str(self.teacher.pk))
        report = Report(self.admin, 'attendance', params)
        rows = list(report.sheets()[0].rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], self.student.name)
        data = build_file(report, 'xlsx')
        workbook = load_workbook(BytesIO(data))
        text = str(list(workbook['Davomat'].values))
        self.assertIn('Valid attendance', text)
        self.assertNotIn('Secret attendance', text)

    def test_student_month_filters_and_both_file_formats(self):
        last_month = self.start - timedelta(days=1)
        Attendance.objects.create(student=self.student, group=self.group, date=last_month, status='absent', note='Older row')
        params = {'student': str(self.student.pk), 'month': self.today.strftime('%Y-%m')}
        report = Report(self.teacher_user, 'student', params)
        workbook = load_workbook(BytesIO(build_file(report, 'xlsx')))
        self.assertIn('Baholar', workbook.sheetnames)
        self.assertNotIn('To‘lovlar', workbook.sheetnames)
        self.assertNotIn('Older row', str(list(workbook['Davomat'].values)))
        document = Document(BytesIO(build_file(report, 'docx')))
        texts = ' '.join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
        self.assertIn('Valid grade', texts)
        self.assertNotIn('Older row', texts)

    def test_formula_like_names_are_exported_as_text(self):
        self.student.name = '=HYPERLINK("https://invalid.test")'
        self.student.save()
        report = Report(self.admin, 'students', self.params(student=str(self.student.pk)))
        workbook = load_workbook(BytesIO(build_file(report, 'xlsx')), data_only=False)
        value = workbook["O'quvchilar"]['C2']
        self.assertNotEqual(value.data_type, 'f')
        self.assertTrue(value.value.startswith("'="))

    def test_report_jobs_are_private_and_revalidate_permissions(self):
        job = create_job(self.teacher_user, 'student', self.params(student=str(self.student.pk)), 'xlsx')
        generate_job(job)
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(reverse('report_job_download', args=[job.public_id])).status_code, 404)
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('report_job_download', args=[job.public_id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content))
        StaffCapability.objects.create(user=self.teacher_user, code='grades.view', allowed=False)
        self.assertEqual(self.client.get(reverse('report_job_download', args=[job.public_id])).status_code, 403)

    def test_large_export_is_queued_and_worker_generates_without_sending(self):
        self.client.force_login(self.admin)
        with patch('core.reporting.Report.estimate', return_value=501):
            response = self.client.post(reverse('report_export'), self.params(kind='students', format='xlsx'))
        self.assertEqual(response.status_code, 302)
        job = ReportJob.objects.get()
        self.assertEqual(job.status, 'pending')
        with patch('core.messaging.telegram_request') as sender:
            call_command('process_crm_jobs', stdout=StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, 'ready')
        sender.assert_not_called()

    def test_cohort_excludes_test_invalid_and_voided_payments(self):
        valid = Lead.objects.create(name='Valid', course='Python', student=self.student, status='enrolled', channel='telegram', advertising_source='Instagram ad')
        invalid = Lead.objects.create(name='Invalid', course='Python', status='invalid')
        test = Lead.objects.create(name='Test', course='Python', is_test=True)
        unpaid = Lead.objects.create(name='Unpaid', course='Python')
        timestamp = timezone.now() - timedelta(hours=1)
        Lead.all_objects.filter(pk__in=[valid.pk, invalid.pk, test.pk, unpaid.pk]).update(created_at=timestamp)
        payment = Payment.objects.create(student=self.student, month=self.start, amount=1000)
        report = Report(self.admin, 'leads', self.params())
        cohort = report.cohort()
        self.assertEqual((cohort['valid'], cohort['invalid'], cohort['test'], cohort['paid']), (2, 1, 1, 1))
        self.assertEqual(cohort['conversion'], Decimal('50.00'))
        self.assertEqual(cohort['sources'][0]['channel'], 'telegram')
        payment.void('Test reversal')
        self.assertEqual(report.cohort()['paid'], 0)

    def test_course_filter_keeps_unconverted_interested_leads_in_denominator(self):
        Lead.objects.create(name='No enrollment yet', course=self.course.name)
        Lead.objects.create(name='Other course', course=self.other_course.name)
        report = Report(self.admin, 'leads', self.params(course=str(self.course.pk)))
        self.assertEqual(report.cohort()['valid'], 1)
        self.assertEqual(report.cohort()['paid'], 0)
        workbook = load_workbook(BytesIO(build_file(report, 'xlsx')))
        self.assertIn('Kohorta', workbook.sheetnames)
        self.assertIn('Manbalar va bosqichlar', workbook.sheetnames)

    def test_lead_filters_allow_course_and_branch_without_existing_groups(self):
        branch = Branch.objects.create(name='New branch without groups')
        course = Course.objects.create(name='New course without groups')
        Lead.objects.create(name='Interested', course=course.name, branch=branch)
        report = Report(self.rec_user, 'leads', self.params(course=str(course.pk), branch=str(branch.pk)))
        self.assertEqual(report.cohort()['valid'], 1)

    def test_student_register_filters_are_preserved_in_report_link(self):
        from urllib.parse import parse_qs
        self.student.source = 'bot'; self.student.save()
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('student_list'), {'status': 'active', 'source': 'bot', 'date_from': str(self.start), 'date_to': str(self.today)})
        params = {key: values[0] for key, values in parse_qs(response.context['report_query']).items()}
        report = Report(self.rec_user, 'students', params)
        self.assertEqual(list(report.students().values_list('pk', flat=True)), [self.student.pk])

    def test_service_month_is_separate_from_cash_period_and_survives_job(self):
        previous = self.start - timedelta(days=1)
        Payment.objects.create(student=self.student, amount=100000, month=previous.replace(day=1))
        Payment.objects.create(student=self.student, amount=200000, month=self.start)
        params = self.params(service_month=previous.strftime('%Y-%m'))
        job = create_job(self.admin, 'payments', params, 'xlsx')
        self.assertEqual(job.filters['service_month'], previous.strftime('%Y-%m'))
        generate_job(job)
        workbook = load_workbook(private_path(job.file_name))
        rows = list(workbook['To‘lovlar'].values)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3], 100000)

    def test_observation_date_and_historical_cash_balance(self):
        student = Student.objects.create(name='Historical', group=self.group, registration_date=date(2026, 8, 1))
        payment = Payment.objects.create(student=student, month=date(2026, 8, 1), amount=200000,
                                         paid_date=timezone.make_aware(datetime(2026, 9, 10, 10)))
        params = {'date_from': '2026-08-01', 'date_to': '2026-08-31', 'student': str(student.pk)}
        report = Report(self.admin, 'accounts', params)
        summary = report.summary()
        self.assertEqual(summary['gross'], 0)
        self.assertEqual(summary['overdue'], Decimal(500000))
        payment.void('Now cancelled')
        row = student_accounts(student, date(2026, 9, 30))[0]
        self.assertEqual(row['paid'], Decimal(200000))

    def test_account_month_paid_partial_unpaid_and_due_day(self):
        self.student.payment_due_day = 15
        self.student.save()
        Payment.objects.create(student=self.student, month=self.start, amount=200000)
        report = Report(self.rec_user, 'accounts', {'month': self.today.strftime('%Y-%m'), 'student': str(self.student.pk), 'payment_state': 'partial'})
        rows = list(report.sheets()[0].rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][-1], 'Qisman')
        self.assertEqual(rows[0][7], Decimal(300000))

    def test_primary_account_filters_do_not_include_second_course(self):
        Enrollment.objects.create(student=self.student, group=self.other_group, starts_on=self.start, monthly_fee=300000)
        report = Report(self.admin, 'accounts', self.params(group=str(self.other_group.pk), student=str(self.student.pk)))
        rows = list(report.sheets()[0].rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], self.other_group.name)

    def test_advance_refund_and_cash_are_separate(self):
        payment = Payment.objects.create(student=self.student, month=self.start, amount=700000)
        Refund.objects.create(payment=payment, amount=100000, reason='Returned', created_by=self.admin)
        summary = Report(self.admin, 'payments', self.params(student=str(self.student.pk))).summary()
        self.assertEqual(summary['gross'], Decimal(700000))
        self.assertEqual(summary['refunds'], Decimal(100000))
        self.assertEqual(summary['net_cash'], Decimal(600000))
        self.assertEqual(summary['advance'], Decimal(100000))
        with self.assertRaises(ValidationError):
            Refund.objects.create(payment=payment, amount=700000, reason='Too much', created_by=self.admin)
        with self.assertRaises(ValidationError):
            payment.amount = 800000
            payment.save()
        payment.refresh_from_db()
        payment.void('Wrong entry after refund')
        summary = Report(self.admin, 'payments', self.params(student=str(self.student.pk))).summary()
        self.assertEqual(summary['gross'], Decimal(700000))
        self.assertEqual(summary['refunds'], Decimal(100000))
        self.assertEqual(summary['cancellations'], Decimal(600000))
        self.assertEqual(summary['net_cash'], 0)
        self.assertEqual(summary['advance'], 0)

    def test_import_preview_then_confirmation_is_idempotent(self):
        self.client.force_login(self.rec_user)
        row = ['', 'New XLSX', '+998901231231', '', '', '', str(self.group.pk), 'active', '12', 'Imported']
        response = self.client.post(reverse('xlsx_import'), {'kind': 'students', 'strategy': 'reject', 'file': self.upload('students', [row])})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(name='New XLSX').exists())
        batch = ImportBatch.objects.get()
        self.assertEqual(batch.errors, [])
        response = self.client.post(reverse('xlsx_import_confirm', args=[batch.public_id]))
        self.assertEqual(response.status_code, 302)
        imported = Student.objects.get(name='New XLSX')
        self.assertEqual(imported.group, self.group)
        self.assertEqual(imported.payment_due_day, 12)
        self.client.post(reverse('xlsx_import_confirm', args=[batch.public_id]))
        self.assertEqual(Student.objects.filter(name='New XLSX').count(), 1)

    def test_import_reports_row_column_and_reason_without_partial_write(self):
        self.client.force_login(self.admin)
        rows = [['', 'Bad phone', 'bad', '', '', '', '', 'pending', '', ''], ['', 'Good phone', '+998901231234', '', '', '', '', 'pending', '', '']]
        self.client.post(reverse('xlsx_import'), {'kind': 'students', 'strategy': 'reject', 'file': self.upload('students', rows)})
        batch = ImportBatch.objects.get()
        self.assertEqual(batch.errors[0]['line'], 2)
        self.assertEqual(batch.errors[0]['column'], 'phone')
        self.client.post(reverse('xlsx_import_confirm', args=[batch.public_id]))
        self.assertFalse(Student.objects.filter(name='Good phone').exists())

    def test_selected_student_import_cannot_change_other_person(self):
        self.client.force_login(self.teacher_user)
        row = [self.foreign.student_number, self.group.pk, str(self.today), 'present', 'Wrong person']
        self.client.post(reverse('xlsx_import'), {'kind': 'attendance', 'student': self.student.pk, 'strategy': 'update', 'file': self.upload('attendance', [row])})
        self.assertTrue(ImportBatch.objects.get().errors)

    def test_teacher_can_import_own_grades_after_preview(self):
        self.client.force_login(self.teacher_user)
        row = [self.student.student_number, self.group.pk, str(self.today), 'classwork', 95, 'Updated safely']
        self.client.post(reverse('xlsx_import'), {'kind': 'grades', 'student': self.student.pk, 'strategy': 'update', 'file': self.upload('grades', [row])})
        batch = ImportBatch.objects.get()
        self.assertEqual(batch.errors, [])
        self.client.post(reverse('xlsx_import_confirm', args=[batch.public_id]))
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.score, 95)

    def test_academic_import_rejects_date_before_enrollment(self):
        previous = self.start - timedelta(days=1)
        raw = [{'line': 2, 'data': dict(zip(HEADERS['attendance'], [self.student.student_number, str(self.group.pk), str(previous), 'present', '']))}]
        rows, errors = validate_rows(self.teacher_user, 'attendance', raw, 'update', self.student)
        self.assertEqual(errors[0]['column'], 'date')
        self.assertEqual(rows[0]['action'], 'error')

    def test_import_permission_and_stale_record_are_rechecked(self):
        raw = [{'line': 2, 'data': dict(zip(HEADERS['grades'], [self.student.student_number, str(self.group.pk), str(self.today), 'classwork', '93', '']))}]
        rows, errors = validate_rows(self.teacher_user, 'grades', raw, 'update', self.student)
        batch = ImportBatch.objects.create(owner=self.teacher_user, kind='grades', student=self.student, strategy='update', rows=rows, errors=errors, fingerprint=digest(rows))
        self.grade.score = 94
        self.grade.save()
        with self.assertRaises(ValidationError):
            confirm_batch(batch, self.teacher_user)
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'preview')
        self.assertEqual(Grade.objects.get(pk=self.grade.pk).score, 94)

    def test_financial_sheet_and_formulas_are_rejected(self):
        self.client.force_login(self.admin)
        file = self.upload('students', [['', '=1+1', '+998901234121', '', '', '', '', 'pending', '', '']])
        response = self.client.post(reverse('xlsx_import'), {'kind': 'students', 'strategy': 'reject', 'file': file})
        self.assertContains(response, 'formula', status_code=200)
        workbook = Workbook()
        workbook.active.title = 'payments'
        workbook.active.append(['amount', 'student_number'])
        data = BytesIO(); workbook.save(data)
        response = self.client.post(reverse('xlsx_import'), {'kind': 'students', 'strategy': 'reject', 'file': SimpleUploadedFile('payments.xlsx', data.getvalue())})
        self.assertContains(response, 'Moliyaviy tarix', status_code=200)
        self.assertFalse(ImportBatch.objects.exists())

    def test_corrupt_xlsx_xml_is_a_validation_error_not_server_error(self):
        self.client.force_login(self.admin)
        valid = self.upload('students', []).read()
        output = BytesIO()
        with zipfile.ZipFile(BytesIO(valid)) as source, zipfile.ZipFile(output, 'w') as target:
            for entry in source.infolist():
                target.writestr(entry.filename, b'<broken' if entry.filename == 'xl/workbook.xml' else source.read(entry.filename))
        response = self.client.post(reverse('xlsx_import'), {'kind': 'students', 'strategy': 'reject', 'file': SimpleUploadedFile('corrupt.xlsx', output.getvalue())})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'XLSX faylini')
        self.assertFalse(ImportBatch.objects.exists())

    def test_financial_migration_reconciles_and_does_not_guess_staff_or_group(self):
        from .financial_migration import HEADERS as financial_headers
        self.client.force_login(self.admin)
        workbook = Workbook()
        workbook.active.title = 'payments_migration'
        workbook.active.append(financial_headers)
        workbook.active.append([self.student.student_number, 125000, '2023-06', '2023-06-05T12:30', 'cash', 'Legacy'])
        stream = BytesIO(); workbook.save(stream)
        data = stream.getvalue()
        response = self.client.post(reverse('financial_migration'), {'file': SimpleUploadedFile('history.xlsx', data), 'expected_total': '120000'})
        self.assertEqual(response.status_code, 302)
        wrong = ImportBatch.objects.get()
        self.assertTrue(wrong.errors)
        self.client.post(reverse('financial_migration_confirm', args=[wrong.public_id]))
        self.assertFalse(Payment.objects.exists())
        self.client.post(reverse('financial_migration'), {'file': SimpleUploadedFile('history.xlsx', data), 'expected_total': '125000'})
        batch = ImportBatch.objects.exclude(pk=wrong.pk).get()
        self.assertEqual(batch.errors, [])
        self.client.post(reverse('financial_migration_confirm', args=[batch.public_id]))
        self.client.post(reverse('financial_migration_confirm', args=[batch.public_id]))
        payment = Payment.all_objects.get()
        self.assertEqual(payment.amount, Decimal(125000))
        self.assertIsNone(payment.teacher_at_payment_id)
        self.assertIsNone(payment.group_at_payment_id)
        from .models import ReceptionistCommission
        self.assertFalse(ReceptionistCommission.all_objects.filter(payment=payment).exists())

    def test_financial_migration_is_not_available_to_reception(self):
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(reverse('financial_migration')).status_code, 302)
        self.assertFalse(ImportBatch.objects.exists())

    def test_guardian_can_link_multiple_children_but_cannot_opt_out_from_bot(self):
        redeem_link_code(issue_link_code('guardian', self.student.pk, self.admin), 777)
        redeem_link_code(issue_link_code('guardian', self.foreign.pk, self.admin), 777)
        self.assertEqual(GuardianBinding.objects.filter(chat_id=777).count(), 2)
        update = {'update_id': 901, 'message': {'chat': {'id': 777, 'type': 'private'}, 'from': {'id': 777}, 'text': '/stop_reports'}}
        with patch('core.telegram_bot.telegram_api', return_value=True):
            process_update(update)
        self.assertEqual(GuardianBinding.objects.filter(chat_id=777, reports_enabled=True).count(), 2)

    def test_student_report_queues_then_sends_verified_document(self):
        redeem_link_code(issue_link_code('student', self.student.pk, self.admin), 777)
        binding = TelegramBinding.objects.get(role='student', target_id=self.student.pk)
        delivery = queue_student_report(self.teacher_user, self.student, f'student:{binding.pk}', self.params(), 'xlsx')
        self.assertEqual(delivery.status, 'pending')
        with patch('core.messaging.telegram_request', return_value={'ok': True, 'result': {'message_id': 1234}}) as sender:
            call_command('process_crm_jobs', stdout=StringIO())
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'sent')
        self.assertEqual(delivery.provider_message_id, 1234)
        self.assertEqual(sender.call_count, 1)
        process_deliveries()
        self.assertEqual(TelegramDelivery.objects.count(), 1)

    def test_student_report_can_link_student_then_send_to_verified_telegram(self):
        self.client.force_login(self.teacher_user)
        self.assertFalse(TelegramBinding.objects.filter(target_id=self.student.pk).exists())

        link_response = self.client.post(
            reverse('student_report_link', args=[self.student.pk]),
            {'role': 'student', **self.params()},
        )
        self.assertEqual(link_response.status_code, 302)
        self.assertIn('date_from=', link_response['Location'])
        link = self.client.session[f'student_report_link_{self.student.pk}']
        self.assertEqual(link['role'], 'student')
        self.assertTrue(TelegramLinkToken.objects.filter(role='student', target_id=self.student.pk, used_at__isnull=True).exists())
        reply = registration_reply({
            'chat': {'id': 888777666, 'type': 'private'},
            'from': {'id': 888777666},
            'text': f"/start link_{link['code']}",
        })
        self.assertIn('muvaffaqiyatli ulandi', reply['text'])
        binding = TelegramBinding.objects.get(role='student', target_id=self.student.pk)

        payload = self.params()
        payload.update({'recipient': f'student:{binding.pk}', 'format': 'xlsx'})
        response = self.client.post(reverse('student_report_send', args=[self.student.pk]), payload)

        self.assertEqual(response.status_code, 302)
        self.assertIn(f'date_from={self.start.isoformat()}', response['Location'])
        self.assertIn(f'date_to={self.today.isoformat()}', response['Location'])
        delivery = TelegramDelivery.objects.get(recipient=f'student:{binding.pk}', student=self.student)
        self.assertEqual(delivery.chat_id, 888777666)
        self.assertEqual(delivery.status, 'pending')
        self.assertEqual(delivery.report_job.filters['student'], str(self.student.pk))

        with patch('core.messaging.telegram_request', return_value={'ok': True, 'result': {'message_id': 7654}}) as sender:
            call_command('process_crm_jobs', stdout=StringIO())
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'sent')
        self.assertEqual(delivery.provider_message_id, 7654)
        sender.assert_called_once()

    def test_repeated_report_click_does_not_duplicate_pending_delivery(self):
        redeem_link_code(issue_link_code('student', self.student.pk, self.admin), 888666555)
        binding = TelegramBinding.objects.get(role='student', target_id=self.student.pk)
        recipient = f'student:{binding.pk}'

        first = queue_student_report(self.teacher_user, self.student, recipient, self.params(), 'xlsx')
        second = queue_student_report(self.teacher_user, self.student, recipient, self.params(), 'xlsx')

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TelegramDelivery.objects.filter(student=self.student, recipient=recipient).count(), 1)
        self.assertEqual(ReportJob.objects.filter(owner=self.teacher_user, kind='student').count(), 1)

    def test_unverified_manual_chat_id_is_rejected(self):
        self.client.force_login(self.teacher_user)
        payload = self.params()
        payload.update({'recipient': 'manual', 'chat_id': 'not-a-chat-id', 'format': 'xlsx'})

        response = self.client.post(reverse('student_report_send', args=[self.student.pk]), payload)

        self.assertEqual(response.status_code, 302)
        self.assertIn(f'date_from={self.start.isoformat()}', response['Location'])
        self.assertIn(f'date_to={self.today.isoformat()}', response['Location'])
        self.assertFalse(TelegramDelivery.objects.filter(student=self.student).exists())
        self.assertFalse(ReportJob.objects.filter(owner=self.teacher_user).exists())

    def test_unlinked_target_and_opt_out_block_delivery(self):
        with self.assertRaises(ValidationError):
            queue_student_report(self.teacher_user, self.student, 'student:999', self.params(), 'xlsx')
        redeem_link_code(issue_link_code('guardian', self.student.pk, self.admin), 777)
        binding = GuardianBinding.objects.get()
        delivery = queue_student_report(self.teacher_user, self.student, f'guardian:{binding.pk}', self.params(), 'docx')
        generate_job(delivery.report_job)
        binding.reports_enabled = False; binding.save()
        with patch('core.messaging.telegram_request') as sender:
            process_deliveries()
        sender.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'cancelled')

    def test_subscription_produces_previous_month_once(self):
        redeem_link_code(issue_link_code('student', self.student.pk, self.admin), 777)
        binding = TelegramBinding.objects.get(role='student')
        next_month = date(self.today.year + (self.today.month == 12), self.today.month % 12 + 1, 1)
        ReportSubscription.objects.create(owner=self.teacher_user, student=self.student, recipient=f'student:{binding.pk}', next_run_on=next_month)
        queue_subscriptions(next_month)
        queue_subscriptions(next_month)
        self.assertEqual(TelegramDelivery.objects.count(), 1)
        job = ReportJob.objects.get()
        self.assertEqual(job.filters['date_from'], self.start.isoformat())
        self.assertEqual(job.filters['date_to'], (next_month - timedelta(days=1)).isoformat())

    def test_linked_students_receive_monthly_academic_and_payment_report_automatically(self):
        redeem_link_code(issue_link_code('student', self.student.pk, self.admin), 777)
        redeem_link_code(issue_link_code('guardian', self.student.pk, self.admin), 778)
        next_month = date(self.today.year + (self.today.month == 12), self.today.month % 12 + 1, 1)
        paid_at = timezone.make_aware(datetime.combine(self.start, time(12)))
        payment = Payment.objects.create(
            student=self.student, amount=Decimal('125000'), month=self.start,
            paid_date=paid_at, received_by=self.admin,
        )

        queue_subscriptions(next_month)
        queue_subscriptions(next_month)

        deliveries = list(TelegramDelivery.objects.order_by('chat_id'))
        self.assertEqual([delivery.chat_id for delivery in deliveries], [777, 778])
        self.assertTrue(all(delivery.status == 'pending' for delivery in deliveries))
        jobs = [delivery.report_job for delivery in deliveries]
        self.assertEqual(len({job.pk for job in jobs}), 2)
        for job in jobs:
            self.assertEqual(job.owner, self.admin)
            self.assertEqual(job.filters['date_from'], self.start.isoformat())
            self.assertEqual(job.filters['date_to'], (next_month - timedelta(days=1)).isoformat())
            generate_job(job)
            workbook = load_workbook(private_path(job.file_name), read_only=True)
            self.assertIn('Davomat', workbook.sheetnames)
            self.assertIn('Baholar', workbook.sheetnames)
            self.assertIn('To‘lovlar', workbook.sheetnames)
            payment_rows = list(workbook['To‘lovlar'].values)
            self.assertIn(payment.receipt_number, [row[0] for row in payment_rows[1:]])
            workbook.close()
        with patch('core.messaging.telegram_request', return_value={'ok': True, 'result': {'message_id': 1234}}) as sender:
            process_deliveries()
        self.assertEqual(sender.call_count, 2)
        self.assertTrue(all(delivery.status == 'sent' for delivery in TelegramDelivery.objects.all()))

    def test_delivery_retries_provider_429_and_is_not_duplicated(self):
        lead = Lead.objects.create(name='Telegram lead', course='Python', telegram_chat_id=777, telegram_user_id=777)
        delivery = TelegramDelivery.objects.create(key='manual-test', chat_id=777, lead=lead, owner=self.rec_user, recipient=f'lead:{lead.pk}', text='Hello')
        with patch('core.messaging.telegram_request', return_value={'ok': False, 'error_code': 429, 'parameters': {'retry_after': 120}}):
            process_deliveries()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'retry')
        self.assertEqual(delivery.attempts, 1)
        with patch('core.messaging.telegram_request') as sender:
            process_deliveries()
        sender.assert_not_called()

    def test_new_lead_and_debt_notifications_go_to_assigned_reception(self):
        redeem_link_code(issue_link_code('receptionist', self.rec.pk, self.admin), 777)
        lead = Lead.objects.create(name='Incoming', course='Python', assigned_to=self.rec_user)
        from .reminders import notify_lead_staff
        notify_lead_staff(lead, 'New lead')
        self.assertTrue(TelegramDelivery.objects.filter(chat_id=777, lead=lead).exists())
        call_command('send_reminders', stdout=StringIO())
        self.assertTrue(Notification.objects.filter(recipient=self.rec_user, type='debt').exists())
        self.assertTrue(TelegramDelivery.objects.filter(chat_id=777, student=self.student).exists())

    def test_campaign_sets_channel_and_source_without_guessing(self):
        Campaign.objects.create(name='Instagram October', start_parameter='ig_oct', advertising_source='Instagram ad')
        from .telegram_bot import registration_reply
        from .models import TelegramSession
        with transaction_for_test():
            registration_reply({'chat': {'id': 777}, 'from': {'id': 777}, 'text': '/start ig_oct'})
            session = TelegramSession.objects.get(chat_id=777)
            session.step = 'phone'
            session.data.update(first_name='Ali', last_name='Bot', course='Python')
            session.save()
            registration_reply({'chat': {'id': 777}, 'from': {'id': 777}, 'text': '+998901234321'})
        lead = Lead.objects.get(telegram_chat_id=777)
        self.assertEqual(lead.channel, 'telegram')
        self.assertEqual(lead.advertising_source, 'Instagram ad')

    def test_incoming_telegram_reply_is_saved_once_and_not_a_new_lead(self):
        from .models import TelegramSession, LeadActivity
        lead = Lead.objects.create(name='Conversation', course='Python', telegram_chat_id=777, telegram_user_id=777)
        TelegramSession.objects.create(chat_id=777, step='done')
        update = {'update_id': 10001, 'message': {'chat': {'id': 777, 'type': 'private'}, 'from': {'id': 777}, 'text': 'Ertaga kelaman'}}
        with patch('core.telegram_bot.telegram_api', return_value=True):
            process_update(update)
            process_update(update)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(LeadActivity.objects.filter(lead=lead, kind='incoming').count(), 1)
        self.assertTrue(Notification.objects.filter(lead=lead, title='Murojaat egasidan yangi xabar').exists())


def transaction_for_test():
    from django.db import transaction
    return transaction.atomic()
