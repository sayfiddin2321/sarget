import json
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Course, Lead, Notification, Receptionist, Student, TelegramBinding, TelegramSession
from .reminders import dispatch_new_lead_reminders


@override_settings(TELEGRAM_WEBHOOK_SECRET='test-secret', TELEGRAM_BOT_TOKEN='test-token')
class TelegramRegistrationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user('boss', is_superuser=True)
        self.reception = get_user_model().objects.create_user('reception')
        Receptionist.objects.create(user=self.reception, name='Qabul', phone='901234567')
        Course.objects.create(name='Python')
        Course.objects.create(name='Frontend', is_active=False)
        self.url = reverse('telegram_webhook')
        self.counter = 0
        self.api = patch('core.telegram_bot.telegram_api', return_value=True).start()
        self.addCleanup(patch.stopall)

    def send(self, text='', contact=None, update_id=None):
        self.counter += 1
        message = {'chat': {'id': 123, 'type': 'private'}, 'from': {'id': 123}, 'text': text}
        if contact is not None:
            message['contact'] = contact
        return self.client.post(self.url, json.dumps({'update_id': update_id or self.counter, 'message': message}),
                                content_type='application/json', HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret')

    def registration(self):
        for text in ['/start instagram', 'Ali', 'Valiyev', 'Python']:
            self.assertEqual(self.send(text).status_code, 200)

    def test_course_step_offers_active_crm_courses_and_rejects_typed_course(self):
        self.send('/start')
        self.send('Ali')
        self.send('Valiyev')

        course_prompt = self.api.call_args.args[1]
        self.assertIn('Kerakli kursni', course_prompt['text'])
        self.assertEqual(course_prompt['reply_markup']['keyboard'], [['Python']])
        self.assertNotIn('Frontend', str(course_prompt['reply_markup']))

        self.send('O‘zim yozgan kurs')
        invalid_reply = self.api.call_args.args[1]
        self.assertIn('tugmalardan tanlang', invalid_reply['text'])
        self.assertEqual(TelegramSession.objects.get().step, 'course')
        self.assertFalse(Lead.objects.exists())

        self.send('pYtHoN')
        self.assertEqual(TelegramSession.objects.get().data['course'], 'Python')
        self.assertEqual(TelegramSession.objects.get().step, 'phone')

    def test_no_active_courses_prompts_user_to_try_later(self):
        Course.objects.update(is_active=False)
        self.send('/start')
        self.send('Ali')
        self.send('Valiyev')

        reply = self.api.call_args.args[1]
        self.assertIn('faol kurs mavjud emas', reply['text'])
        self.assertEqual(TelegramSession.objects.get().step, 'course')

    def test_registration_notifies_reception_and_admin_only_once(self):
        self.registration()
        response = self.send(contact={'phone_number': '998901234567', 'user_id': 123}, update_id=10)
        self.assertEqual(response.status_code, 200)
        self.send(contact={'phone_number': '998901234567', 'user_id': 123}, update_id=10)
        lead = Lead.objects.get()
        self.assertEqual((lead.name, lead.phone, lead.course, lead.campaign), ('Ali Valiyev', '+998901234567', 'Python', 'instagram'))
        self.assertEqual(set(Notification.objects.values_list('recipient_id', flat=True)), {self.admin.pk, self.reception.pk})
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(lead.activities.count(), 1)
        self.assertEqual(TelegramSession.objects.get().step, 'done')

    def test_delivery_failure_retries_reply_without_creating_second_lead(self):
        self.registration()
        self.api.return_value = False
        self.assertEqual(self.send('+998901234567', update_id=10).status_code, 503)
        self.api.return_value = True
        self.assertEqual(self.send('+998901234567', update_id=10).status_code, 200)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 2)

    def test_invalid_phone_and_someone_elses_contact_do_not_create_lead(self):
        self.registration()
        self.send('invalid-phone')
        self.send(contact={'phone_number': '998901234567', 'user_id': 777})
        self.assertFalse(Lead.objects.exists())
        self.assertEqual(TelegramSession.objects.get().step, 'phone')
        self.send('90 123 45 67')
        self.assertEqual(Lead.objects.get().phone, '+998901234567')

    def test_cancel_and_restart(self):
        self.registration()
        self.send('/cancel')
        self.send('+998901234567')
        self.assertFalse(Lead.objects.exists())
        self.send('/start')
        self.assertEqual(TelegramSession.objects.get().step, 'first_name')

    def test_linked_student_start_shows_help_instead_of_starting_another_lead(self):
        student = Student.objects.create(name='Linked student', phone='+998901234567')
        TelegramBinding.objects.create(role='student', target_id=student.pk, chat_id=123)

        self.send('/start')

        self.assertFalse(Lead.objects.exists())
        self.assertFalse(TelegramSession.objects.filter(chat_id=123).exists())
        self.assertIn('hisobingiz CRMga ulangan', self.api.call_args.args[1]['text'])
        self.assertNotIn('/stop_reports', self.api.call_args.args[1]['text'])
        self.assertNotIn('/start_reports', self.api.call_args.args[1]['text'])

    def test_help_and_report_commands_do_not_allow_report_opt_out(self):
        self.send('/help')
        self.assertIn('/link KOD', self.api.call_args.args[1]['text'])
        student = Student.objects.create(name='Linked student', phone='+998901234567')
        from .models import GuardianBinding
        GuardianBinding.objects.create(student=student, chat_id=123)

        self.send('/stop_reports')
        self.assertIn('Bu buyruq mavjud emas', self.api.call_args.args[1]['text'])
        self.assertTrue(GuardianBinding.objects.get(chat_id=123).reports_enabled)

        self.send('/start_reports')
        self.assertIn('Bu buyruq mavjud emas', self.api.call_args.args[1]['text'])
        self.assertTrue(GuardianBinding.objects.get(chat_id=123).reports_enabled)

    def test_secret_and_payload_validation(self):
        self.assertEqual(self.client.post(self.url, '{}', content_type='application/json').status_code, 403)
        for payload in ['[]', '{}', '{broken']:
            response = self.client.post(self.url, payload, content_type='application/json',
                                        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret')
            self.assertEqual(response.status_code, 400)
        self.assertFalse(Lead.objects.exists())


class NewLeadReminderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('reception')
        Receptionist.objects.create(user=self.user, name='Qabul', phone='901234567')
        self.now = timezone.make_aware(datetime(2026, 10, 29, 9))
        self.lead = Lead.objects.create(name='Ali Valiyev', phone='+998901234567', course='Python')
        # Previous calendar day, even when fewer than 24 hours have elapsed.
        Lead.objects.filter(pk=self.lead.pk).update(created_at=self.now - timedelta(hours=10))

    def test_one_reminder_each_day_then_stop_after_result(self):
        dispatch_new_lead_reminders(self.now)
        dispatch_new_lead_reminders(self.now)
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 1)
        dispatch_new_lead_reminders(self.now + timedelta(days=1))
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 2)
        self.lead.status = 'contacted'
        self.lead.save()
        dispatch_new_lead_reminders(self.now + timedelta(days=2))
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 2)

    def test_no_reminder_on_registration_day_or_for_inactive_reception(self):
        dispatch_new_lead_reminders(self.now - timedelta(hours=10))
        self.assertFalse(Notification.objects.exists())
        Receptionist.objects.filter(user=self.user).update(is_active=False)
        dispatch_new_lead_reminders(self.now)
        self.assertFalse(Notification.objects.exists())

    def test_result_required_and_first_receptionist_becomes_responsible(self):
        self.client.force_login(self.user)
        data = {'name': self.lead.name, 'course': 'Python', 'status': 'contacted'}
        self.client.post(reverse('lead_edit', args=[self.lead.pk]), data)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'new')
        data['activity_note'] = "Bog'landim, kechki kursga keladi"
        response = self.client.post(reverse('lead_edit', args=[self.lead.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to, self.user)
        self.assertEqual(self.lead.status, 'contacted')
        self.assertEqual(self.lead.activities.get().note, data['activity_note'])
