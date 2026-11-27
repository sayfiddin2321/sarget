from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Lead, Notification, Teacher


@override_settings(TELEGRAM_BOT_TOKEN='', TIME_ZONE='Asia/Tashkent',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NotificationHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('history-owner', password='test')
        cls.other = get_user_model().objects.create_user('other-history-user')
        Teacher.objects.create(user=cls.other, name='Other teacher')

    def setUp(self):
        self.client.force_login(self.user)

    def notification(self, title, when='2026-11-15T12:00:00', **kwargs):
        item = Notification.objects.create(recipient=self.user, title=title, message='Stored message', **kwargs)
        Notification.objects.filter(pk=item.pk).update(created_at=timezone.make_aware(datetime.fromisoformat(when)))
        return item

    def test_all_history_includes_read_and_unread_and_is_linked_in_navigation(self):
        self.notification('Old read message', when='2025-01-01T10:00:00', is_read=True)
        self.notification('New unread message')
        Notification.objects.create(recipient=self.other, title='Other private message', message='Secret')
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.context['notifications'].paginator.count, 2)
        self.assertEqual(response.context['history_count'], 2)
        self.assertEqual(response.context['history_unread_count'], 1)
        self.assertContains(response, 'Old read message')
        self.assertContains(response, 'New unread message')
        self.assertNotContains(response, 'Other private message')
        self.assertContains(response, '<span>Bildirishnomalar</span>', html=True)
        self.assertContains(response, '01.01.2025')

    def test_date_range_includes_both_full_days_in_tashkent(self):
        self.notification('Before', '2026-11-09T23:59:59')
        first = self.notification('First boundary', '2026-11-10T00:00:00')
        last = self.notification('Last boundary', '2026-11-20T23:59:59')
        self.notification('After', '2026-11-21T00:00:00')
        response = self.client.get(reverse('notification_list'), {'date_from': '2026-11-10', 'date_to': '2026-11-20'})
        self.assertEqual([n.pk for n in response.context['notifications']], [last.pk, first.pk])
        self.assertEqual(response.context['history_count'], 4)

    def test_status_type_search_and_old_unread_link(self):
        read = self.notification('Paid tuition', is_read=True, type='payment')
        unread = self.notification('Debt reminder', type='debt')
        self.notification('Other information')
        response = self.client.get(reverse('notification_list'), {'status': 'read', 'type': 'payment', 'q': 'tuition'})
        self.assertEqual([n.pk for n in response.context['notifications']], [read.pk])
        response = self.client.get(reverse('notification_list'), {'unread': '1', 'q': 'Debt'})
        self.assertEqual([n.pk for n in response.context['notifications']], [unread.pk])

    def test_invalid_date_range_shows_errors_and_does_not_mark_anything_read(self):
        item = self.notification('Keep unread')
        for params in ({'date_from': 'broken'}, {'date_from': '2026-11-21', 'date_to': '2026-11-20'}):
            response = self.client.get(reverse('notification_list'), params)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['filter_form'].errors)
            self.assertEqual(response.context['notifications'].paginator.count, 0)
            self.client.post(reverse('notification_read_all'), params)
            item.refresh_from_db()
            self.assertFalse(item.is_read)

    def test_bell_clear_keeps_all_rows_and_only_marks_the_owners_items(self):
        first = self.notification('Keep first')
        self.notification('Keep already read', is_read=True)
        other = Notification.objects.create(recipient=self.other, title='Other unread', message='Secret')
        response = self.client.post(reverse('api_notification_clear_all'), HTTP_ACCEPT='application/json')
        self.assertEqual(response.json()['deleted_count'], 0)
        self.assertEqual(response.json()['unread_count'], 0)
        first.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(first.is_read)
        self.assertFalse(other.is_read)
        self.assertEqual(Notification.objects.count(), 3)
        self.assertEqual(self.client.get(reverse('notification_poll')).json()['notifications'], [])
        history = self.client.get(reverse('notification_list'))
        self.assertContains(history, 'Keep first')
        self.assertEqual(history.context['notifications'].paginator.count, 2)

    def test_legacy_delete_keeps_the_message_in_history_and_is_owner_post_only(self):
        item = self.notification('Keep this message')
        url = reverse('notification_delete', args=[item.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url).status_code, 302)
        item.refresh_from_db()
        self.assertTrue(item.is_read)
        self.assertContains(self.client.get(reverse('notification_list')), item.title)

    def test_mark_filtered_items_read_preserves_other_dates_and_returns_to_filter(self):
        old = self.notification('Older', '2026-10-01T12:00:00')
        current = self.notification('Current')
        target = reverse('notification_list') + '?date_from=2026-11-01&date_to=2026-11-20'
        response = self.client.post(reverse('notification_read_all'), {
            'date_from': '2026-11-01', 'date_to': '2026-11-20', 'next': target,
        })
        self.assertRedirects(response, target)
        old.refresh_from_db()
        current.refresh_from_db()
        self.assertFalse(old.is_read)
        self.assertTrue(current.is_read)

    def test_history_mark_read_retains_filter_and_rejects_external_redirect(self):
        item = self.notification('Mark only')
        target = reverse('notification_list') + '?q=Mark'
        response = self.client.post(reverse('notification_open', args=[item.pk]), {'history': '1', 'next': target})
        self.assertRedirects(response, target)
        response = self.client.post(reverse('notification_open', args=[item.pk]), {'history': '1', 'next': 'https://example.test/'})
        self.assertRedirects(response, reverse('notification_list'))
        self.assertTrue(Notification.objects.filter(pk=item.pk, is_read=True).exists())

    def test_pagination_retains_filters_and_reaches_older_messages(self):
        Notification.objects.bulk_create([
            Notification(recipient=self.user, title=f'Archived info {i}', message='Persistent text', type='info')
            for i in range(61)
        ])
        response = self.client.get(reverse('notification_list'), {'q': 'Archived', 'type': 'info'})
        self.assertEqual(response.context['notifications'].paginator.count, 61)
        self.assertTrue(response.context['notifications'].has_next())
        self.assertContains(response, 'q=Archived&amp;type=info&amp;page=2')
        second = self.client.get(reverse('notification_list'), {'q': 'Archived', 'type': 'info', 'page': 2})
        self.assertEqual(len(second.context['notifications']), 11)

    def test_financial_and_lead_notifications_keep_existing_permission_scope(self):
        lead = Lead.objects.create(name='Private lead', course='Python')
        for title, extra in (
            ('Allowed info', {}), ('Private debt', {'type': 'debt'}), ('Private lead notice', {'lead': lead}),
        ):
            Notification.objects.create(recipient=self.other, title=title, message='Text', **extra)
        self.client.force_login(self.other)
        response = self.client.get(reverse('notification_list'))
        self.assertContains(response, 'Allowed info')
        self.assertNotContains(response, 'Private debt')
        self.assertNotContains(response, 'Private lead notice')
        self.assertEqual(response.context['history_count'], 1)
