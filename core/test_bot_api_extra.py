import json
from django.test import TestCase, Client, override_settings
from core.models import Lead, LeadActivity, Student


@override_settings(CRM_API_KEY='test-api-key')
class BotApiExtraTests(TestCase):
    H = {'HTTP_X_CRM_API_KEY': 'test-api-key'}

    def test_account_requires_key(self):
        self.assertEqual(Client().get('/api/bot/account/?chat_id=5').status_code, 401)

    def test_account_not_linked(self):
        r = Client().get('/api/bot/account/?chat_id=5', **self.H)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['linked'])

    def test_account_bad_chat_id(self):
        self.assertEqual(Client().get('/api/bot/account/?chat_id=abc', **self.H).status_code, 400)

    def test_lead_message_saved(self):
        lead = Lead.objects.create(name='A B', phone='+998901112233', course='X',
                                   source='bot', channel='telegram',
                                   telegram_chat_id=77, telegram_user_id=77)
        r = Client().post('/api/bot/lead-message/', data=json.dumps(
            {'chat_id': 77, 'user_id': 77, 'text': 'Salom'}),
            content_type='application/json', **self.H)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['saved'])
        self.assertTrue(LeadActivity.objects.filter(lead=lead, kind='incoming', note='Salom').exists())

    def test_lead_message_unknown_chat(self):
        r = Client().post('/api/bot/lead-message/', data=json.dumps(
            {'chat_id': 1, 'user_id': 1, 'text': 'Salom'}),
            content_type='application/json', **self.H)
        self.assertEqual(r.json(), {'ok': True, 'saved': False})
