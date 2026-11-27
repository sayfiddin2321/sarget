from urllib.parse import urlparse
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.telegram_bot import telegram_api


def webhook_payload(base_url):
    base_url = base_url.rstrip('/')
    parsed = urlparse(base_url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/')
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise CommandError('CRM uchun HTTPS manzil kiriting.')
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_WEBHOOK_SECRET:
        raise CommandError('TELEGRAM_BOT_TOKEN va TELEGRAM_WEBHOOK_SECRET ni sozlang.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', settings.TELEGRAM_WEBHOOK_SECRET):
        raise CommandError('TELEGRAM_WEBHOOK_SECRET faqat A-Z, a-z, 0-9, _ va - belgilaridan iborat bo‘lsin (1–256 belgi).')
    return {'url': base_url + '/integrations/telegram/webhook/', 'secret_token': settings.TELEGRAM_WEBHOOK_SECRET,
            'allowed_updates': ['message'], 'max_connections': 1}


class Command(BaseCommand):
    help = 'Telegram webhookni HTTPS CRM manziliga ulash'

    def add_arguments(self, parser):
        parser.add_argument('base_url', help='Masalan: https://crm.example.com')

    def handle(self, *args, **options):
        if not telegram_api('setWebhook', webhook_payload(options['base_url'])):
            raise CommandError('Telegram webhook ulanmagan. Token, secret va tarmoqni tekshiring.')
        self.stdout.write(self.style.SUCCESS('Telegram webhook ulandi.'))
