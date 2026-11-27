import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import date, time, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db.models import Sum
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .backups import create_backup, verify_backup
from .models import (
    FinancialAudit, Group, Lead, Notification, OperationalRun, Payment,
    Receptionist, ReceptionistCommission, Salary, Student, StudentTariff,
    Teacher, TelegramBinding, TelegramLinkToken,
)
from .telegram_linking import issue_link_code, redeem_link_code
from .telegram_bot import process_update


@override_settings(CRM_API_KEY='regression-test-key', TELEGRAM_BOT_TOKEN='',
                   TELEGRAM_STAFF_CHAT_ID='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FinancialImprovementsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('owner', 'owner@example.test', 'test-pass')
        cls.rec_user = get_user_model().objects.create_user('reception', password='test-pass')
        cls.teacher_user = get_user_model().objects.create_user('teacher', password='test-pass')
        cls.teacher = Teacher.objects.create(name='Teacher', user=cls.teacher_user)
        cls.rec = Receptionist.objects.create(name='Reception', user=cls.rec_user, commission_percent=10)
        cls.group = Group.objects.create(name='Python', teacher=cls.teacher, monthly_fee=500000,
                                        start_time=time(9), end_time=time(10))
        cls.student = Student.objects.create(name='Ali', group=cls.group, teacher=cls.teacher,
                                             receptionist=cls.rec, registration_date=date(2026, 8, 1))

    def payment(self, amount=100000):
        return Payment.objects.create(student=self.student, amount=amount, month=timezone.localdate().replace(day=1))

    def test_report_counts_equal_commissions_once_even_with_multiple_students(self):
        Student.objects.create(name='Vali', group=self.group, receptionist=self.rec)
        for _ in range(3):
            self.payment()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reports'))
        row = response.context['receptionist_stats'][0]
        self.assertEqual(row['student_count'], 2)
        self.assertEqual(row['month_commission'], 30000)
        self.assertEqual(row['year_commission'], 30000)

    def test_price_change_preserves_old_months_and_starts_next_month(self):
        with patch('core.billing.timezone.localdate', return_value=date(2026, 10, 29)):
            self.group.monthly_fee = 700000
            self.group.save()
        self.student.refresh_from_db()
        old = self.student.get_debt_breakdown(today=date(2026, 10, 31))
        future = self.student.get_debt_breakdown(today=date(2026, 11, 1))
        self.assertEqual([item['amount'] for item in old], [Decimal(500000)] * 3)
        self.assertEqual(future[-1]['amount'], Decimal(700000))

    def test_discount_transfer_pause_and_resume_keep_history(self):
        with patch('core.billing.timezone.localdate', return_value=date(2026, 10, 29)):
            self.student.discount_percent = 20
            self.student.save()
        self.assertEqual(self.student.tariffs.get(effective_month=date(2026, 11, 1)).fee, Decimal(400000))
        with patch('core.billing.timezone.localdate', return_value=date(2026, 11, 20)):
            self.student.status = 'inactive'
            self.student.save()
        debts = self.student.get_debt_breakdown(today=date(2026, 12, 1))
        self.assertEqual(len(debts), 4)
        self.assertEqual(debts[-1]['amount'], Decimal(400000))
        with patch('core.billing.timezone.localdate', return_value=date(2026, 12, 15)):
            self.student.status = 'active'
            self.student.save()
        self.assertEqual(self.student.get_debt_breakdown(today=date(2027, 1, 1))[-1]['amount'], Decimal(400000))

    def test_first_group_starts_now_not_at_old_admission_date(self):
        student = Student.objects.create(name='Waiting', status='pending', registration_date=date(2026, 7, 1))
        with patch('core.billing.timezone.localdate', return_value=date(2026, 10, 29)):
            student.group = self.group
            student.status = 'active'
            student.save()
        debts = student.get_debt_breakdown(today=date(2026, 10, 29))
        self.assertEqual(len(debts), 1)
        self.assertEqual(debts[0]['month'], date(2026, 10, 1))

    def test_transfer_keeps_original_fee_and_group_snapshot(self):
        other = Group.objects.create(name='English', monthly_fee=800000, start_time=time(11), end_time=time(12))
        with patch('core.billing.timezone.localdate', return_value=date(2026, 10, 29)):
            self.student.group = other
            self.student.save()
        self.assertEqual(self.student.tariffs.first().group_name, 'Python')
        debts = self.student.get_debt_breakdown(today=date(2026, 11, 1))
        self.assertEqual([item['amount'] for item in debts], [Decimal(500000)] * 3 + [Decimal(800000)])

    def test_group_deletion_stops_future_charges_without_erasing_old_debt(self):
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            Group.objects.filter(pk=self.group.pk).delete()
        self.client.force_login(self.admin)
        with patch('core.billing.timezone.localdate', return_value=date(2026, 10, 29)):
            self.client.post(reverse('group_delete', args=[self.group.pk]))
        self.student.refresh_from_db()
        self.group.refresh_from_db()
        self.assertFalse(self.group.is_active)
        self.assertEqual(self.student.group_id, self.group.pk)
        debts = self.student.get_debt_breakdown(today=date(2026, 12, 1))
        self.assertEqual([item['amount'] for item in debts], [Decimal(500000)] * 3)

    def test_unrelated_save_does_not_create_tariff_due_to_fractional_rounding(self):
        group = Group.objects.create(name='Fraction', monthly_fee=Decimal('123.45'), start_time=time(13), end_time=time(14))
        student = Student.objects.create(name='Fraction', group=group, discount_percent=33)
        self.assertEqual(student.tariffs.get().fee, Decimal('82.71'))
        student.name = 'New name'
        student.save()
        self.assertEqual(student.tariffs.count(), 1)

    def test_payment_edit_and_void_keep_actor_and_restore_debt(self):
        payment = self.payment()
        self.client.force_login(self.admin)
        response = self.client.post(reverse('payment_edit', args=[payment.pk]), {
            'student': self.student.pk, 'amount': 200000,
            'month': payment.month.strftime('%Y-%m'), 'payment_type': 'cash',
        })
        self.assertEqual(response.status_code, 302)
        event = FinancialAudit.objects.filter(entity='payment', object_id=payment.pk, action='update').first()
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(Decimal(event.before['amount']), Decimal(100000))
        self.assertEqual(Decimal(event.after['amount']), Decimal(200000))
        debt_before = self.student.get_debt_amount()
        response = self.client.post(reverse('payment_delete', args=[payment.pk]), {'reason': 'Wrong entry'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())
        self.assertEqual(Payment.all_objects.get(pk=payment.pk).void_reason, 'Wrong entry')
        self.assertFalse(ReceptionistCommission.objects.filter(payment_id=payment.pk).exists())
        self.assertTrue(ReceptionistCommission.all_objects.filter(payment_id=payment.pk).exists())
        self.assertEqual(self.student.get_debt_amount(), debt_before + 200000)
        self.assertEqual(FinancialAudit.objects.get(entity='payment', object_id=payment.pk, action='void').actor, self.admin)
        self.assertContains(self.client.get(reverse('payment_receipt', args=[payment.pk])), 'BEKOR QILINGAN')

    def test_void_requires_reason_and_paid_month_cannot_be_changed(self):
        payment = self.payment()
        self.client.force_login(self.admin)
        self.client.post(reverse('payment_delete', args=[payment.pk]))
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        salary = Salary.objects.get(teacher=self.teacher, month=payment.teacher_salary_month)
        salary.is_paid = True
        salary.save(update_fields=['is_paid'])
        response = self.client.post(reverse('payment_delete', args=[payment.pk]), {'reason': 'Try closed month'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_audit_is_immutable_and_requires_financial_history_permission(self):
        self.payment()
        event = FinancialAudit.objects.first()
        with self.assertRaises(ValidationError):
            FinancialAudit.objects.filter(pk=event.pk).update(action='changed')
        with self.assertRaises(ValidationError):
            event.delete()
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('financial_history'))
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('financial_history')).status_code, 200)
        self.assertEqual(self.client.get(reverse('system_status')).status_code, 200)

    def test_void_is_excluded_from_reports_and_hard_delete_is_forbidden(self):
        payment = self.payment()
        with self.assertRaises(ValidationError):
            Payment.objects.filter(pk=payment.pk).delete()
        payment.void('Duplicate')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reports'))
        self.assertEqual(response.context['receptionist_stats'][0]['month_commission'], 0)
        self.assertEqual(Payment.objects.aggregate(total=Sum('amount'))['total'], None)

    def test_phone_only_binding_and_phone_only_read_are_rejected(self):
        headers = {'HTTP_X_CRM_API_KEY': 'regression-test-key'}
        response = self.client.post(reverse('api_bot_auth_user'), data=json.dumps({'phone': '+998901234567', 'chat_id': 123}), content_type='application/json', **headers)
        self.assertEqual(response.status_code, 400)
        response = self.client.get(reverse('api_bot_student_info'), {'phone': self.student.phone}, **headers)
        self.assertEqual(response.status_code, 403)

    def test_codes_expire_are_one_use_and_never_stored_as_plaintext(self):
        code = issue_link_code('student', self.student.pk, self.admin)
        self.assertNotEqual(TelegramLinkToken.objects.get().token_hash, code)
        role, target = redeem_link_code(code, 123)
        self.assertEqual((role, target.pk), ('student', self.student.pk))
        with self.assertRaises(ValidationError):
            redeem_link_code(code, 456)
        code = issue_link_code('teacher', self.teacher.pk, self.admin)
        TelegramLinkToken.objects.filter(used_at__isnull=True).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            redeem_link_code(code, 456)

    def test_new_code_revokes_old_and_chat_cannot_take_second_profile(self):
        first = issue_link_code('student', self.student.pk, self.admin)
        second = issue_link_code('student', self.student.pk, self.admin)
        with self.assertRaises(ValidationError):
            redeem_link_code(first, 123)
        redeem_link_code(second, 123)
        code = issue_link_code('teacher', self.teacher.pk, self.admin)
        with self.assertRaises(ValidationError):
            redeem_link_code(code, 123)
        self.assertFalse(TelegramLinkToken.objects.filter(role='teacher', used_at__isnull=False).exists())

    def test_native_bot_can_redeem_code_and_duplicate_update_is_safe(self):
        code = issue_link_code('student', self.student.pk, self.admin)
        update = {'update_id': 888, 'message': {'chat': {'id': 123, 'type': 'private'},
                                              'from': {'id': 123}, 'text': '/link ' + code}}
        with patch('core.telegram_bot.telegram_api', return_value=True) as sender:
            self.assertTrue(process_update(update))
            self.assertTrue(process_update(update))
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(TelegramBinding.objects.get().target_id, self.student.pk)

    def test_reception_can_link_all_students_but_not_other_employees(self):
        other = Student.objects.create(name='Other')
        self.client.force_login(self.rec_user)
        for target in (f'teacher:{self.teacher.pk}',):
            response = self.client.post(reverse('telegram_link'), {'target': target})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(TelegramLinkToken.objects.exists())
        response = self.client.post(reverse('telegram_link'), {'target': f'student:{self.student.pk}'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertTrue(TelegramLinkToken.objects.exists())
        self.client.post(reverse('telegram_link'), {'target': f'student:{other.pk}'})
        self.assertEqual(TelegramLinkToken.objects.count(), 2)

    def test_inactive_account_and_legacy_unverified_chat_have_no_access(self):
        self.student.telegram_chat_id = 123
        self.student.save(update_fields=['telegram_chat_id'])
        headers = {'HTTP_X_CRM_API_KEY': 'regression-test-key'}
        self.assertEqual(self.client.get(reverse('api_bot_student_info'), {'chat_id': 123}, **headers).status_code, 403)
        redeem_link_code(issue_link_code('student', self.student.pk, self.admin), 123)
        Student.objects.filter(pk=self.student.pk).update(status='inactive')
        self.assertEqual(self.client.get(reverse('api_bot_student_info'), {'chat_id': 123}, **headers).status_code, 403)

    def test_api_disabled_without_key_and_does_not_accept_url_keys(self):
        with override_settings(CRM_API_KEY=''):
            self.assertEqual(self.client.get(reverse('api_bot_courses_list')).status_code, 503)
        self.assertEqual(self.client.get(reverse('api_bot_courses_list'), {'api_key': 'regression-test-key'}).status_code, 401)

    def test_teacher_summary_is_scoped_and_does_not_reveal_finances(self):
        other_teacher = Teacher.objects.create(name='Other teacher')
        Student.objects.create(name='Foreign', teacher=other_teacher, group=self.group)
        redeem_link_code(issue_link_code('teacher', self.teacher.pk, self.admin), 123)
        response = self.client.get(reverse('api_bot_staff_summary'), {'chat_id': 123}, HTTP_X_CRM_API_KEY='regression-test-key')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['total_active_students'], 1)
        self.assertIsNone(response.json()['summary']['total_debt_sum'])

    def test_json_arrays_null_and_scalars_are_client_errors(self):
        for endpoint in ('api_bot_create_lead', 'api_bot_auth_user'):
            for payload in ('[]', 'null', 'true', '123', '"text"'):
                response = self.client.post(reverse(endpoint), data=payload, content_type='application/json', HTTP_X_CRM_API_KEY='regression-test-key')
                self.assertEqual(response.status_code, 400)

    def test_poll_does_not_write_or_trigger_telegram_and_job_records_failures(self):
        Lead.objects.create(name='Callback', status='callback', follow_up_at=timezone.now())
        self.client.force_login(self.admin)
        self.client.get(reverse('notification_poll'))
        self.assertFalse(Notification.objects.exists())
        with override_settings(TELEGRAM_BOT_TOKEN='test-token', TELEGRAM_STAFF_CHAT_ID='123'):
            with patch('core.messaging.telegram_request') as sender:
                call_command('send_reminders', stdout=StringIO())
            sender.assert_not_called()
        run = OperationalRun.objects.get(job='reminders')
        self.assertEqual(run.status, 'success')
        self.assertEqual(run.details['telegram_pending'], 2)
        self.assertIsNotNone(run.finished_at)

    def test_backup_failure_is_recorded(self):
        with patch('core.management.commands.backup_database.create_backup', side_effect=CommandError('Disk unavailable')):
            with self.assertRaises(CommandError):
                call_command('backup_database', stdout=StringIO())
        run = OperationalRun.objects.get(job='backup')
        self.assertEqual(run.status, 'failed')
        self.assertIsNotNone(run.finished_at)

    def test_backup_command_also_works_before_status_table_exists(self):
        with patch('core.management.commands.backup_database.connection.introspection.table_names', return_value=[]):
            with patch('core.management.commands.backup_database.create_backup', return_value=(Path('backup.zip'), 1)):
                call_command('backup_database', stdout=StringIO())
        self.assertFalse(OperationalRun.objects.exists())


class BackupArchiveTests(SimpleTestCase):
    def test_roundtrip_restores_database_and_media_into_new_directory(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / 'live.sqlite3'
            with closing(sqlite3.connect(database)) as conn:
                conn.execute('CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)')
                conn.execute("INSERT INTO sample VALUES (1, 'test')")
                conn.commit()
            media = root / 'media'
            media.mkdir()
            (media / 'photo.bin').write_bytes(b'photo-test-bytes')
            backup_settings = SimpleNamespace(DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': database}}, MEDIA_ROOT=media, BASE_DIR=root)
            with patch('core.backups.settings', backup_settings):
                archive, count = create_backup(root / 'backups')
            self.assertEqual(count, 1)
            destination = root / 'restored'
            self.assertEqual(verify_backup(archive, destination), 1)
            self.assertEqual((destination / 'media/photo.bin').read_bytes(), b'photo-test-bytes')
            with closing(sqlite3.connect(destination / 'db.sqlite3')) as conn:
                self.assertEqual(conn.execute('SELECT name FROM sample').fetchone()[0], 'test')
            with self.assertRaises(CommandError):
                verify_backup(archive, destination)

    def test_modified_archive_and_unsafe_paths_are_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.zip'
            for name in ('db.sqlite3', '../outside', 'media/../../outside', 'media/C:/bad'):
                with zipfile.ZipFile(path, 'w') as archive:
                    files = {'db.sqlite3': 'wrong', name: 'wrong'}
                    archive.writestr('manifest.json', json.dumps({'version': 1, 'files': files}))
                    for filename in files:
                        archive.writestr(filename, b'corrupt')
                if name == 'db.sqlite3':
                    with self.assertRaisesMessage(CommandError, 'nazorat summasi'):
                        verify_backup(path)
                else:
                    with self.assertRaisesMessage(CommandError, 'ruxsat etilmagan'):
                        verify_backup(path)
