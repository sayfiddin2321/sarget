import csv
from datetime import datetime, time, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admissions import receptionist_work
from .models import Grade, Group, Lead, LeadActivity, Notification, Payment, Receptionist, Student, Teacher
from .reminders import notify_lead_staff


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user('admin', password='test-pass', is_superuser=True, is_staff=True)
        cls.rec_user = User.objects.create_user('rec', password='test-pass')
        cls.other_user = User.objects.create_user('other-rec', password='test-pass')
        cls.rec = Receptionist.objects.create(user=cls.rec_user, name='Reception')
        Receptionist.objects.create(user=cls.other_user, name='Other')
        cls.teacher_user = User.objects.create_user('teacher', password='test-pass')
        cls.teacher = Teacher.objects.create(user=cls.teacher_user, name='Teacher', subject='Python')
        cls.group = Group.objects.create(name='Python', teacher=cls.teacher, start_time=time(10), end_time=time(11))
        cls.student = Student.objects.create(name='Ali', teacher=cls.teacher, group=cls.group, receptionist=cls.rec)

    def test_leads_beyond_old_limit_are_reachable_without_duplicates(self):
        Lead.objects.bulk_create([Lead(name=f'Lead {i}', course='Python') for i in range(503)])
        self.client.force_login(self.admin)
        first = self.client.get(reverse('lead_list')).context['leads']
        last = self.client.get(reverse('lead_list'), {'page': 11}).context['leads']
        self.assertEqual(first.paginator.count, 503)
        self.assertEqual(len(first), 50)
        self.assertEqual(len(last), 3)
        self.assertFalse({lead.pk for lead in first} & {lead.pk for lead in last})

    def test_student_page_preserves_search_and_teacher_scope(self):
        Student.objects.bulk_create([Student(name='Same name', teacher=self.teacher) for _ in range(52)])
        Student.objects.create(name='Same name')
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('student_list'), {'q': 'Same name', 'page': 2})
        page = response.context['students']
        self.assertEqual(page.paginator.count, 52)
        self.assertEqual(len(page), 2)
        self.assertContains(response, 'q=Same+name')
        self.assertEqual([student.pk for student in page], list(Student.objects.filter(teacher=self.teacher, name='Same name').order_by('pk').values_list('pk', flat=True))[50:])

    def test_payment_totals_cover_entire_filtered_result(self):
        Payment.objects.bulk_create([Payment(student=self.student, amount=1000, month=timezone.localdate().replace(day=1)) for _ in range(53)])
        self.client.force_login(self.admin)
        response = self.client.get(reverse('payment_list'), {'page': 2})
        self.assertEqual(len(response.context['payments']), 3)
        self.assertEqual(response.context['total'], 53000)

    def test_grades_beyond_previous_cap_are_reachable(self):
        now = timezone.localdate()
        Grade.objects.bulk_create([Grade(student=self.student, group=self.group, date=now - timedelta(days=i), score=80) for i in range(203)])
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('grade_list'), {'page': 5})
        self.assertEqual(response.context['total_count'], 203)
        self.assertEqual(len(response.context['grades']), 3)

    def test_invalid_and_empty_pages_are_safe(self):
        self.client.force_login(self.admin)
        for number in ('bad', '-1', '999999', ''):
            response = self.client.get(reverse('lead_list'), {'page': number})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['leads'].number, 1)

    def test_claim_is_idempotent_and_cannot_steal_other_ownership(self):
        lead = Lead.objects.create(name='New', course='Python')
        url = reverse('lead_claim', args=[lead.pk])
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse('lead_edit', args=[lead.pk]))
        self.client.post(url)
        self.assertEqual(LeadActivity.objects.filter(lead=lead).count(), 1)
        self.client.force_login(self.other_user)
        self.assertRedirects(self.client.post(url), reverse('lead_list'))
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to, self.rec_user)

    def test_claim_requires_reception_role_and_csrf(self):
        lead = Lead.objects.create(name='New', course='Python')
        url = reverse('lead_claim', args=[lead.pk])
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.post(url).status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.rec_user)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        lead.refresh_from_db()
        self.assertIsNone(lead.assigned_to_id)

    def test_dashboard_work_excludes_other_owners_closed_and_tomorrow(self):
        now = timezone.make_aware(datetime(2026, 10, 29, 10))
        new = Lead.objects.create(name='New', course='Python')
        due = Lead.objects.create(name='Due', course='Python', status='callback', assigned_to=self.rec_user, follow_up_at=now - timedelta(hours=1))
        upcoming = Lead.objects.create(name='Later', course='Python', status='callback', follow_up_at=now + timedelta(hours=1))
        Lead.objects.create(name='Other', course='Python', assigned_to=self.other_user)
        Lead.objects.create(name='Closed', course='Python', status='enrolled', assigned_to=self.rec_user)
        Lead.objects.create(name='Tomorrow', course='Python', status='callback', follow_up_at=now + timedelta(days=1))
        work = receptionist_work(self.rec_user, now)
        self.assertEqual(list(work['work_new']), [new])
        self.assertEqual(list(work['work_due']), [due])
        self.assertEqual(list(work['work_upcoming']), [upcoming])
        self.client.force_login(self.rec_user)
        with patch('core.admissions.timezone.now', return_value=now):
            response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Bugungi ishlar')
        self.assertContains(response, reverse('lead_claim', args=[new.pk]))

    def test_same_filters_apply_to_list_and_export(self):
        now = timezone.now()
        included = Lead.objects.create(name='Python interested', course='Python', assigned_to=self.rec_user, status='callback', follow_up_at=now - timedelta(hours=1))
        Lead.objects.create(name='Python other', course='Python', assigned_to=self.other_user, status='callback', follow_up_at=now - timedelta(hours=1))
        Lead.objects.create(name='Python new', course='Python', assigned_to=self.rec_user)
        self.client.force_login(self.rec_user)
        params = {'q': 'Python', 'scope': 'mine', 'due': '1'}
        response = self.client.get(reverse('lead_list'), params)
        self.assertEqual(list(response.context['leads']), [included])
        exported = self.client.get(reverse('lead_export'), params)
        rows = list(csv.reader(StringIO(exported.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], str(included.pk))

    def test_admin_edit_keeps_unassigned_lead_available_for_reception(self):
        lead = Lead.objects.create(name='Lead', course='Python')
        self.client.force_login(self.admin)
        self.client.post(reverse('lead_edit', args=[lead.pk]), {'name': 'Lead', 'course': 'Python', 'status': 'new'})
        lead.refresh_from_db()
        self.assertIsNone(lead.assigned_to_id)

    def test_new_lead_notification_has_action_url_and_marks_read(self):
        lead = Lead.objects.create(name='Lead', course='Python')
        notify_lead_staff(lead, 'Yangi ariza')
        notification = Notification.objects.get(recipient=self.rec_user)
        self.client.force_login(self.rec_user)
        data = self.client.get(reverse('notification_poll')).json()
        self.assertEqual(data['notifications'][0]['url'], reverse('lead_edit', args=[lead.pk]))
        response = self.client.post(reverse('mark_notification_read', args=[notification.pk]))
        self.assertEqual(response.json()['url'], reverse('lead_edit', args=[lead.pk]))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_notification_history_older_unread_items_are_accessible(self):
        Notification.objects.bulk_create([Notification(recipient=self.rec_user, title=f'Own notification {i}', message='Test') for i in range(13)])
        Notification.objects.create(recipient=self.other_user, title='Private other', message='Secret')
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.context['notifications'].paginator.count, 13)
        self.assertContains(response, 'Own notification 0')
        self.assertNotContains(response, 'Private other')

    def test_notification_open_is_post_only_and_owner_only(self):
        lead = Lead.objects.create(name='Lead', course='Python')
        notification = Notification.objects.create(recipient=self.rec_user, lead=lead, title='Own', message='Test')
        url = reverse('notification_open', args=[notification.pk])
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.post(reverse('mark_notification_read', args=[notification.pk])).status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse('lead_edit', args=[lead.pk]))

    def test_deleted_lead_notification_falls_back_to_history(self):
        lead = Lead.objects.create(name='Lead', course='Python')
        notification = Notification.objects.create(recipient=self.rec_user, lead=lead, title='Own', message='Test')
        lead.delete()
        self.client.force_login(self.rec_user)
        self.assertRedirects(self.client.post(reverse('notification_open', args=[notification.pk])), reverse('notification_list'))
