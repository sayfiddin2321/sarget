from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from decimal import Decimal

from .forms import StudentForm
from .models import Course, Lead, LeadActivity, Notification, Payment, ReminderDispatch, Student


class NotificationViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='staff',
            email='staff@example.com',
            password='test-pass',
        )
        self.other_user = get_user_model().objects.create_user(username='other', password='test-pass')
        self.client.force_login(self.user)

    def test_poll_returns_only_this_users_unread_notifications(self):
        notification = Notification.objects.create(
            recipient=self.user,
            title='Qayta aloqa',
            message='Qo‘ng‘iroq vaqti',
        )
        Notification.objects.create(
            recipient=self.other_user,
            title='Boshqa xabar',
            message='Boshqa foydalanuvchiga tegishli',
        )

        response = self.client.get(reverse('notification_poll'), {'after': 0})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 1)
        self.assertEqual(response.json()['notifications'][0]['id'], notification.pk)

    def test_scheduler_creates_callback_and_poll_only_reads_it(self):
        lead = Lead.objects.create(
            name='Callback lead',
            course='Python',
            status='callback',
            follow_up_at=timezone.now() + timedelta(minutes=5),
        )

        self.assertEqual(self.client.get(reverse('notification_poll')).json()['unread_count'], 0)
        from unittest.mock import patch
        with patch('core.messaging.telegram_request') as sender:
            call_command('send_reminders', verbosity=0)
        sender.assert_not_called()
        response = self.client.get(reverse('notification_poll'), {'after': 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 1)
        self.assertEqual(response.json()['notifications'][0]['title'], 'Qayta qo‘ng‘iroq vaqti')
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.user,
                message__startswith=f'{lead.name} |',
            ).count(),
            1,
        )
        self.assertTrue(ReminderDispatch.objects.filter(key__startswith=f'callback:{lead.pk}:').exists())

        self.client.get(reverse('notification_poll'), {'after': 0})
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.user,
                message__startswith=f'{lead.name} |',
            ).count(),
            1,
        )

    def test_mark_read_requires_post_and_only_marks_own_notification(self):
        notification = Notification.objects.create(
            recipient=self.user,
            title='Qayta aloqa',
            message='Qo‘ng‘iroq vaqti',
        )
        other_notification = Notification.objects.create(
            recipient=self.other_user,
            title='Boshqa xabar',
            message='Boshqa foydalanuvchiga tegishli',
        )

        get_response = self.client.get(reverse('mark_notification_read', args=[notification.pk]))
        response = self.client.post(reverse('mark_notification_read', args=[notification.pk]))

        self.assertEqual(get_response.status_code, 405)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        notification.refresh_from_db()
        other_notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertFalse(other_notification.is_read)


class LeadViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='test-pass',
        )
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(
            name='Ali Valiyev',
            phone='+998901234567',
            course='Python',
        )

    def test_lead_list_displays_styled_edit_action(self):
        response = self.client.get(reverse('lead_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('lead_edit', args=[self.lead.pk]))
        self.assertContains(response, 'Tahrirlash')
        self.assertContains(response, 'lead-actions')

    def test_lead_list_shows_latest_status_activity_time(self):
        activity = LeadActivity.objects.create(
            lead=self.lead,
            user=self.user,
            status='contacted',
            note='Bog‘landik',
        )
        LeadActivity.objects.filter(pk=activity.pk).update(
            created_at=datetime(2026, 10, 30, 10, 30, tzinfo=timezone.get_current_timezone())
        )

        response = self.client.get(reverse('lead_list'))

        self.assertContains(response, '30.10.2026 10:30')

    def test_inline_contact_status_records_contact_time(self):
        response = self.client.post(
            reverse('lead_status_update', args=[self.lead.pk]),
            {'status': 'contacted'},
            HTTP_REFERER=reverse('lead_list'),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('lead_list'))
        self.lead.refresh_from_db()
        activity = LeadActivity.objects.get(lead=self.lead)
        self.assertEqual(self.lead.status, 'contacted')
        self.assertIsNone(self.lead.follow_up_at)
        self.assertEqual(activity.status, 'contacted')
        self.assertLess((timezone.now() - activity.created_at).total_seconds(), 5)

    def test_inline_callback_requires_and_saves_callback_time(self):
        url = reverse('lead_status_update', args=[self.lead.pk])
        missing_time_response = self.client.post(
            url,
            {'status': 'callback'},
            HTTP_REFERER=reverse('lead_list'),
        )

        self.assertEqual(missing_time_response.status_code, 302)
        self.assertEqual(missing_time_response['Location'], reverse('lead_list'))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'new')
        self.assertFalse(LeadActivity.objects.filter(lead=self.lead).exists())

        response = self.client.post(
            url,
            {'status': 'callback', 'follow_up_at': '2026-10-30T10:30'},
            HTTP_REFERER=reverse('lead_list'),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('lead_list'))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'callback')
        self.assertEqual(
            timezone.localtime(self.lead.follow_up_at).strftime('%Y-%m-%d %H:%M'),
            '2026-10-30 10:30',
        )
        self.assertEqual(LeadActivity.objects.get(lead=self.lead).status, 'callback')

    def test_edit_saves_lead_and_activity(self):
        response = self.client.post(
            reverse('lead_edit', args=[self.lead.pk]),
            {
                'name': 'Ali Valiyev',
                'phone': '+998901234567',
                'course': 'Python Pro',
                'source': 'referral',
                'status': 'callback',
                'follow_up_at': '2026-10-30T10:30',
                'notes': 'Kechki guruhga qiziqdi',
                'activity_note': 'Juma kuni qayta qo‘ng‘iroq',
            },
        )

        self.assertRedirects(response, reverse('lead_list'))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.course, 'Python Pro')
        self.assertEqual(self.lead.source, 'referral')
        self.assertEqual(self.lead.status, 'callback')
        self.assertEqual(
            timezone.localtime(self.lead.follow_up_at).strftime('%Y-%m-%d %H:%M'),
            '2026-10-30 10:30',
        )
        self.assertTrue(
            LeadActivity.objects.filter(
                lead=self.lead,
                user=self.user,
                note='Juma kuni qayta qo‘ng‘iroq',
            ).exists()
        )

    def test_edit_form_shows_activity_note_after_validation_error(self):
        response = self.client.post(
            reverse('lead_edit', args=[self.lead.pk]),
            {
                'name': '',
                'course': 'Python',
                'source': 'referral',
                'status': 'new',
                'activity_note': 'Bu matn formadagi xatodan keyin saqlanib qolsin',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bu matn formadagi xatodan keyin saqlanib qolsin')


class StudentPaymentHistoryTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='history-admin',
            email='history-admin@example.com',
            password='test-pass',
        )
        self.client.force_login(self.admin)
        self.student = Student.objects.create(
            name='Historical student',
            phone='+998901234567',
            status='graduated',
            registration_date=datetime(2023, 5, 12).date(),
        )

    def test_student_register_exposes_archive_import_export_and_camera_capture(self):
        response = self.client.get(reverse('student_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('xlsx_import'))
        self.assertContains(response, reverse('report_center'))
        self.assertContains(response, 'Bitirgan')
        self.assertContains(response, '12.05.2023')
        self.assertEqual(StudentForm().fields['photo'].widget.attrs['capture'], 'user')

    def test_student_export_includes_students_and_prefetched_payment_totals(self):
        Payment.objects.create(
            student=self.student,
            amount=Decimal('450000'),
            month=datetime(2023, 6, 1).date(),
            received_by=self.admin,
        )

        response = self.client.get(reverse('student_export'))

        self.assertEqual(response.status_code, 200)
        csv_text = response.content.decode('utf-8-sig')
        self.assertIn('Historical student', csv_text)
        self.assertIn('450,000', csv_text)

    def test_payment_import_screen_is_available(self):
        response = self.client.get(reverse('payment_import'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('financial_migration_template'))
        self.assertContains(response, "To'lov sanasi")

    def test_payment_import_saves_month_and_historical_datetime(self):
        from io import BytesIO
        from openpyxl import Workbook
        from .financial_migration import HEADERS
        from .models import ImportBatch
        workbook = Workbook()
        workbook.active.title = 'payments_migration'
        workbook.active.append(HEADERS)
        workbook.active.append([self.student.student_number, '450000', '2023-06', '2023-06-07T14:25', 'cash', 'Eski tolov'])
        data = BytesIO(); workbook.save(data)
        upload = SimpleUploadedFile('payments.xlsx', data.getvalue())
        response = self.client.post(reverse('payment_import'), {'file': upload, 'expected_total': '450000'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Payment.objects.filter(student=self.student).exists())
        batch = ImportBatch.objects.get(kind='payments_migration')
        self.assertEqual(batch.errors, [])
        self.client.post(reverse('financial_migration_confirm', args=[batch.public_id]))
        payment = Payment.objects.get(student=self.student)
        self.assertEqual(payment.amount, Decimal('450000'))
        self.assertEqual(payment.month, datetime(2023, 6, 1).date())
        self.assertEqual(timezone.localtime(payment.paid_date).strftime('%Y-%m-%d %H:%M'), '2023-06-07 14:25')
        self.assertEqual(payment.received_by, self.admin)

    def test_student_import_keeps_historical_status_and_registration_date(self):
        from io import BytesIO
        from openpyxl import Workbook
        from .report_imports import HEADERS
        from .models import ImportBatch
        workbook = Workbook()
        workbook.active.title = 'students'
        workbook.active.append(HEADERS['students'])
        workbook.active.append(['', 'Old student', '+998901234568', '', '2005-04-12', '2022-03-15', '', 'graduated', '', 'Tamomlagan'])
        output = BytesIO()
        workbook.save(output)
        upload = SimpleUploadedFile('students.xlsx', output.getvalue())
        response = self.client.post(reverse('student_import'), {'kind': 'students', 'strategy': 'reject', 'file': upload})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(phone='+998901234568').exists())
        batch = ImportBatch.objects.get()
        self.assertEqual(batch.errors, [])
        self.client.post(reverse('xlsx_import_confirm', args=[batch.public_id]))
        student = Student.objects.get(phone='+998901234568')
        self.assertEqual(student.status, 'graduated')
        self.assertEqual(student.registration_date, datetime(2022, 3, 15).date())
        self.assertEqual(student.birth_date, datetime(2005, 4, 12).date())
        self.assertEqual(student.discount_percent, 0)

    def test_payment_import_rejects_malformed_historical_datetime(self):
        from io import BytesIO
        from openpyxl import Workbook
        from .financial_migration import HEADERS
        from .models import ImportBatch
        workbook = Workbook()
        workbook.active.title = 'payments_migration'
        workbook.active.append(HEADERS)
        workbook.active.append([self.student.student_number, '450000', '2023-06', 'not-a-date', 'cash', ''])
        data = BytesIO(); workbook.save(data)
        upload = SimpleUploadedFile('payments.xlsx', data.getvalue())
        response = self.client.post(reverse('payment_import'), {'file': upload, 'expected_total': '450000'})
        self.assertEqual(response.status_code, 302)
        batch = ImportBatch.objects.get(kind='payments_migration')
        self.assertTrue(batch.errors)
        self.client.post(reverse('financial_migration_confirm', args=[batch.public_id]))
        self.assertFalse(Payment.objects.filter(student=self.student).exists())

    def test_payment_list_and_student_history_link_to_saved_receipt(self):
        payment = Payment.objects.create(
            student=self.student,
            amount=Decimal('450000'),
            month=datetime(2023, 6, 1).date(),
            paid_date=timezone.make_aware(datetime(2023, 6, 7, 14, 25)),
            received_by=self.admin,
        )
        receipt_url = reverse('payment_receipt', args=[payment.pk])

        payment_list_response = self.client.get(reverse('payment_list'))
        student_detail_response = self.client.get(reverse('student_detail', args=[self.student.pk]))
        receipt_response = self.client.get(receipt_url)

        self.assertContains(payment_list_response, receipt_url)
        self.assertContains(payment_list_response, payment.receipt_number)
        self.assertContains(student_detail_response, receipt_url)
        self.assertContains(student_detail_response, '07.06.2023 14:25')
        self.assertContains(receipt_response, payment.receipt_number)


class CourseManagementTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='course-admin',
            email='course-admin@example.com',
            password='test-pass',
        )
        self.reception = get_user_model().objects.create_user(
            username='course-reception',
            password='test-pass',
        )

    def test_admin_can_create_and_deactivate_course(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('course_create'),
            {'name': '  Python dasturlash  ', 'description': 'Boshlang‘ich kurs', 'is_active': 'on'},
        )

        self.assertRedirects(response, reverse('course_list'))
        course = Course.objects.get()
        self.assertEqual(course.name, 'Python dasturlash')
        self.assertTrue(course.is_active)

        response = self.client.post(
            reverse('course_edit', args=[course.pk]),
            {'name': course.name, 'description': course.description},
        )
        self.assertRedirects(response, reverse('course_list'))
        course.refresh_from_db()
        self.assertFalse(course.is_active)

    def test_course_creation_rejects_case_insensitive_duplicate(self):
        Course.objects.create(name='Python')
        self.client.force_login(self.admin)

        response = self.client.post(reverse('course_create'), {'name': ' python '})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bu kurs nomi allaqachon qo‘shilgan.')
        self.assertEqual(Course.objects.count(), 1)

    def test_receptionist_cannot_manage_courses(self):
        self.client.force_login(self.reception)

        response = self.client.get(reverse('course_list'))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Course.objects.exists())



class GradeAndAttendanceFeatureTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(username='admin_user', password='pass')
        self.rec_user = user_model.objects.create_user(username='rec_user', password='pass')
        from .models import Receptionist, Teacher, Group, Student, Grade
        self.receptionist = Receptionist.objects.create(user=self.rec_user, name='Rec Test', phone='+998901112233')
        self.teacher_user = user_model.objects.create_user(username='teacher_user', password='pass')
        self.teacher = Teacher.objects.create(user=self.teacher_user, name='Ustoz Test', phone='+998902223344', subject='Matematika')
        self.group = Group.objects.create(
            name='Matem-101', teacher=self.teacher, start_time='09:00', end_time='10:30', monthly_fee=300000
        )
        self.student = Student.objects.create(
            name='Test Student', phone='+998903334455', group=self.group, teacher=self.teacher, receptionist=self.receptionist
        )

    def test_receptionist_can_view_attendance_but_grades_are_disabled_by_default(self):
        self.client.force_login(self.rec_user)
        res_att = self.client.get(reverse('attendance_list'))
        self.assertEqual(res_att.status_code, 200)

        res_grades = self.client.get(reverse('grade_list'))
        self.assertEqual(res_grades.status_code, 403)

    def test_take_grades_saves_grade_and_shows_on_student_card(self):
        self.client.force_login(self.teacher_user)
        post_data = {
            'date': timezone.localdate().isoformat(),
            'grade_type': 'classwork',
            f'score_{self.student.id}': '95',
            f'note_{self.student.id}': 'A\'lo qatnashdi',
        }
        res = self.client.post(reverse('take_grades', args=[self.group.pk]), post_data)
        self.assertRedirects(res, reverse('grade_list'))

        from .models import Grade
        grade = Grade.objects.filter(student=self.student).first()
        self.assertIsNotNone(grade)
        self.assertEqual(grade.score, 95)

        # Student card page renders
        res_card = self.client.get(reverse('student_card_print', args=[self.student.pk]))
        self.assertEqual(res_card.status_code, 200)
        self.assertContains(res_card, 'O\'QUVCHI KARTASI')
