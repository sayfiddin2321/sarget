from datetime import time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import GroupForm
from .models import Group, Teacher
from .utils import group_conflict_messages


def _group(name, *, teacher=None, room='', days='1-3-5', start=time(10), end=time(11), is_active=True):
    return Group.objects.create(
        name=name, teacher=teacher, room=room, days=days,
        start_time=start, end_time=end, is_active=is_active,
    )


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ScheduleConflictTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user('admin', password='test-pass', is_superuser=True, is_staff=True)
        cls.teacher_user = User.objects.create_user('teacher', password='test-pass')
        cls.teacher = Teacher.objects.create(user=cls.teacher_user, name='Teacher', subject='Python')
        cls.other_teacher = Teacher.objects.create(name='Other', subject='IELTS')

    def _form_data(self, **overrides):
        data = {
            'name': 'New group',
            'teacher': self.teacher.pk,
            'room': '101',
            'days': '1-3-5',
            'custom_days': '',
            'start_time': '10:00',
            'end_time': '11:00',
            'monthly_fee': '500000',
            'max_students': '15',
            'is_active': 'on',
            'description': '',
        }
        data.update(overrides)
        return data

    def test_room_conflict_found_across_different_day_patterns(self):
        _group('Full week', room='101', days='1-2-3-4-5', start=time(9), end=time(11))
        _group('Odd days', room='101', days='1-3-5', start=time(10), end=time(12))

        self.client.force_login(self.admin)
        response = self.client.get(reverse('schedule'))
        cards = {g.name: g.conflict_list for g in response.context['groups']}
        self.assertTrue(any("Xona to'qnashuvi" in text for text in cards['Full week']))
        self.assertTrue(any("Xona to'qnashuvi" in text for text in cards['Odd days']))
        self.assertEqual(response.context['total_conflicts'], 2)

    def test_non_overlapping_groups_and_different_rooms_are_clean(self):
        _group('Morning', room='101', start=time(9), end=time(10))
        _group('Afternoon', room='101', start=time(11), end=time(12))
        _group('Parallel other room', room='102', start=time(9), end=time(10))

        self.client.force_login(self.admin)
        response = self.client.get(reverse('schedule'))
        self.assertEqual(response.context['total_conflicts'], 0)
        self.assertTrue(all(not g.conflict_list for g in response.context['groups']))

    def test_teacher_double_booking_in_different_rooms_is_reported(self):
        _group('Room 101', teacher=self.teacher, room='101', start=time(9), end=time(11))
        _group('Room 202', teacher=self.teacher, room='202', start=time(10), end=time(12))

        self.client.force_login(self.admin)
        response = self.client.get(reverse('schedule'))
        cards = {g.name: g.conflict_list for g in response.context['groups']}
        self.assertTrue(any("O'qituvchi to'qnashuvi" in text for text in cards['Room 101']))
        self.assertFalse(any("Xona to'qnashuvi" in text for text in cards['Room 101']))

    def test_inactive_groups_are_not_part_of_conflicts(self):
        _group('Active', room='101', start=time(10), end=time(11))
        _group('Archived', room='101', start=time(10), end=time(11), is_active=False)

        self.client.force_login(self.admin)
        response = self.client.get(reverse('schedule'))
        self.assertEqual(response.context['total_conflicts'], 0)

    def test_custom_days_without_codes_never_conflict(self):
        group = Group(name='Custom', room='101', days='custom', custom_days='Har kuni',
                      start_time=time(10), end_time=time(11))
        other = _group('Regular', room='101', start=time(10), end=time(11))
        self.assertEqual(group_conflict_messages(group, [other]), [])

    def test_form_warns_but_saves_room_conflict(self):
        existing = _group('Existing', room='101', start=time(10), end=time(11))
        form = GroupForm(data=self._form_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(any("Xona to'qnashuvi" in text for text in form.conflict_warnings))
        created = form.save()
        self.assertTrue(Group.objects.filter(name='New group').exists())

        # Endi ikkala guruh jadvalda ham qizil belgi bilan ko'rinadi.
        self.client.force_login(self.admin)
        response = self.client.get(reverse('schedule'))
        cards = {g.name: g.conflict_list for g in response.context['groups']}
        self.assertTrue(cards[existing.name])
        self.assertTrue(cards[created.name])

    def test_form_warns_but_saves_teacher_conflict(self):
        _group('Existing', teacher=self.teacher, room='999', start=time(10), end=time(11))
        form = GroupForm(data=self._form_data(room='101'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(any("O'qituvchi to'qnashuvi" in text for text in form.conflict_warnings))

    def test_editing_a_group_does_not_conflict_with_itself(self):
        existing = _group('Existing', room='101', start=time(10), end=time(11))
        form = GroupForm(data=self._form_data(name='Existing'), instance=existing)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.conflict_warnings, [])

    def test_form_without_conflict_has_no_warnings(self):
        _group('Existing', room='101', start=time(9), end=time(10))
        form = GroupForm(data=self._form_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.conflict_warnings, [])

    def test_archived_group_does_not_block_creation(self):
        _group('Old', room='101', start=time(10), end=time(11), is_active=False)
        form = GroupForm(data=self._form_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_inactive_new_group_may_overlap(self):
        _group('Existing', room='101', start=time(10), end=time(11))
        form = GroupForm(data=self._form_data(is_active=''))
        self.assertTrue(form.is_valid(), form.errors)

    def test_small_capacity_group_can_be_saved(self):
        form = GroupForm(data=self._form_data(max_students='5'))
        self.assertTrue(form.is_valid(), form.errors)
        group = form.save()
        self.assertEqual(group.max_students, 5)

    def test_conflicting_group_is_saved_with_warning_and_shown_red(self):
        _group('Existing', room='101', start=time(10), end=time(11))
        self.client.force_login(self.admin)

        # To'qnashuv saqlashga to'sqinlik qilmaydi, lekin xabar beriladi.
        response = self.client.post(reverse('group_create'), self._form_data(), follow=True)
        self.assertEqual(response.redirect_chain[0][0], reverse('group_list'))
        texts = [str(m) for m in response.context['messages']]
        self.assertTrue(any("Jadvalda to'qnashuv" in text for text in texts), texts)
        self.assertTrue(Group.objects.filter(name='New group').exists())

        schedule = self.client.get(reverse('schedule'))
        self.assertContains(schedule, 'has-conflict')
        self.assertEqual(schedule.context['total_conflicts'], 2)

        # Forma sahifasida ham aynan ogohlantirish ko'rinadi.
        group = Group.objects.get(name='Existing')
        form = GroupForm(data=self._form_data(name='Existing', start_time='10:30', end_time='11:30'), instance=group)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.conflict_warnings)
        page = self.client.get(reverse('group_edit', args=[group.pk]))
        self.assertEqual(page.status_code, 200)

    def test_group_list_shows_readable_days(self):
        _group('IELTS', days='1-3-5')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('group_list'))
        self.assertContains(response, 'Du / Chor / Ju')
