from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Lead, Receptionist, Teacher


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProfileAndLeadBoardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser('profile-board-admin', 'admin@example.test', 'test-pass')
        cls.teacher_user = users.objects.create_user('profile-board-teacher', password='test-pass')
        cls.rec_user = users.objects.create_user('profile-board-rec', password='test-pass')
        cls.teacher = Teacher.objects.create(user=cls.teacher_user, name='Initial Teacher', subject='Python', percent=40)
        cls.rec = Receptionist.objects.create(user=cls.rec_user, name='Initial Reception', commission_percent=10)

    def test_admin_without_employee_profile_can_change_name_and_keep_role(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('profile_edit')).status_code, 200)
        response = self.client.post(reverse('profile_edit'), {'first_name': 'Updated', 'last_name': 'Director'})
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.get_full_name(), 'Updated Director')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, '<div class="user-name">Updated Director</div>', html=True)
        self.assertContains(response, 'Boshliq')
        self.assertTrue(self.admin.is_superuser)

    def test_employee_name_saves_update_account_and_sidebar_without_touching_pay_or_login(self):
        for profile, user, role in ((self.teacher, self.teacher_user, "O'qituvchi"), (self.rec, self.rec_user, 'Retsepshen')):
            original_login = user.username
            profile.name = 'Changed Employee Name Longer Than Thirty Characters'
            profile.save(update_fields=['name'])
            user.refresh_from_db()
            self.assertEqual(user.get_full_name(), profile.name)
            self.assertEqual(user.username, original_login)
            self.client.force_login(user)
            response = self.client.get(reverse('dashboard'))
            self.assertContains(response, profile.name)
            self.assertContains(response, role)
        self.teacher.refresh_from_db()
        self.rec.refresh_from_db()
        self.assertEqual(self.teacher.percent, 40)
        self.assertEqual(self.rec.commission_percent, 10)

    def test_account_name_change_updates_linked_employee_and_unrelated_save_does_not_rename(self):
        self.teacher_user.first_name, self.teacher_user.last_name = 'Account', 'Renamed'
        self.teacher_user.save(update_fields=['first_name', 'last_name'])
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.name, 'Account Renamed')
        Teacher.objects.filter(pk=self.teacher.pk).update(name='Legacy Profile Name')
        self.teacher_user.last_login = timezone.now()
        self.teacher_user.save(update_fields=['last_login'])
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.name, 'Legacy Profile Name')
        self.client.force_login(self.teacher_user)
        self.assertContains(self.client.get(reverse('dashboard')), '<div class="user-name">Legacy Profile Name</div>', html=True)

    def test_invalid_password_form_still_renders_both_profile_forms(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(reverse('profile_edit'), {
            'form_type': 'password', 'old_password': 'incorrect', 'new_password1': 'NewSecretPassword829', 'new_password2': 'NewSecretPassword829',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['form'])
        self.assertTrue(response.context['password_form'].errors)
        self.teacher_user.refresh_from_db()
        self.assertTrue(self.teacher_user.check_password('test-pass'))

    def test_board_has_independent_columns_and_pagination(self):
        Lead.objects.bulk_create([Lead(name=f'New applicant {i}', course='Python', status='new') for i in range(25)])
        contacted = Lead.objects.create(name='Already contacted', course='Python', status='contacted')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('lead_list'))
        columns = {column['key']: column for column in response.context['lead_columns']}
        self.assertEqual(len(columns), len(Lead.STATUS))
        self.assertEqual(columns['new']['page'].paginator.count, 25)
        self.assertEqual(len(columns['new']['page']), 20)
        self.assertEqual(list(columns['contacted']['page']), [contacted])
        self.assertContains(response, 'id="lead-column-new"')
        self.assertContains(response, 'id="lead-column-contacted"')
        self.assertContains(response, 'class="lead-table"')
        self.assertContains(response, 'id="all-leads"')
        following = self.client.get(reverse('lead_list') + columns['new']['next_url'].split('#')[0])
        next_columns = {column['key']: column for column in following.context['lead_columns']}
        self.assertEqual(len(next_columns['new']['page']), 5)
        self.assertFalse({lead.pk for lead in columns['new']['page']} & {lead.pk for lead in next_columns['new']['page']})
        self.assertEqual(next_columns['contacted']['page'].number, 1)

    def test_board_filters_and_next_page_preserve_scope(self):
        Lead.objects.bulk_create([Lead(name=f'Target {i}', course='Python', assigned_to=self.admin) for i in range(23)])
        Lead.objects.create(name='Target foreign owner', course='Python', assigned_to=self.rec_user)
        Lead.objects.create(name='Other search text', course='English', assigned_to=self.admin)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('lead_list'), {'q': 'Target', 'scope': 'mine', 'status': 'new'})
        columns = response.context['lead_columns']
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0]['page'].paginator.count, 23)
        query = parse_qs(urlsplit(columns[0]['next_url']).query)
        self.assertEqual(query, {'q': ['Target'], 'scope': ['mine'], 'status': ['new'], 'p_new': ['2']})
        self.assertNotContains(response, 'Target foreign owner')

    def test_full_list_below_board_keeps_its_own_pagination(self):
        Lead.objects.bulk_create([Lead(name=f'List entry {i}', course='Python') for i in range(53)])
        self.client.force_login(self.admin)
        response = self.client.get(reverse('lead_list'), {'page': 2, 'p_new': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['leads']), 3)
        self.assertEqual(response.context['lead_columns'][0]['page'].number, 1)
        html = response.content.decode()
        self.assertLess(html.index('class="lead-board"'), html.index('id="all-leads"'))
        table = html.split('id="all-leads"', 1)[1]
        for lead in response.context['leads']:
            self.assertIn(f'data-lead-row="{lead.pk}"', table)

    def test_saved_status_moves_card_to_its_group(self):
        lead = Lead.objects.create(name='Move me', course='Python')
        self.client.force_login(self.admin)
        self.client.post(reverse('lead_status_update', args=[lead.pk]), {'status': 'contacted'}, HTTP_REFERER=reverse('lead_list'))
        columns = {column['key']: column for column in self.client.get(reverse('lead_list')).context['lead_columns']}
        self.assertEqual(columns['new']['page'].paginator.count, 0)
        self.assertEqual(list(columns['contacted']['page']), [lead])
