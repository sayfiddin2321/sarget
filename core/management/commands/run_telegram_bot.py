from threading import Event

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connections

from core.telegram_bot import process_update, telegram_api_result
from core.runtime import process_lock


class Command(BaseCommand):
    help = 'Telegram botni polling rejimida doimiy ishlatish'
    stealth_options = ('stop_event',)

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError('.env faylida TELEGRAM_BOT_TOKEN sozlanmagan.')
        stop = options.get('stop_event') or Event()
        with process_lock('telegram-polling', settings.TELEGRAM_BOT_TOKEN):
            try:
                self.poll(stop)
            except KeyboardInterrupt:
                self.stdout.write('Telegram bot to‘xtatildi.')
            finally:
                connections.close_all()

    def poll(self, stop):
        webhook = telegram_api_result('getWebhookInfo')
        if webhook is None:
            raise CommandError('Telegram API bilan bog‘lanib bo‘lmadi; token yoki internetni tekshiring.')
        if webhook.get('url'):
            raise CommandError(
                'Telegram webhook yoqilgan. Polling bilan birga ishlamaydi; '
                'avval mavjud webhook manzilini tekshiring.'
            )

        bot = telegram_api_result('getMe')
        if bot is None:
            raise CommandError('Telegram bot tokeni API tomonidan qabul qilinmadi.')

        offset = None
        self.stdout.write(self.style.SUCCESS(
            f"@{bot.get('username', 'bot')} ishga tushdi. To‘xtatish uchun Ctrl+C bosing."
        ))

        while not stop.is_set():
            updates = telegram_api_result('getUpdates', {
                'offset': offset,
                'timeout': 10,
                'allowed_updates': ['message'],
            }, timeout=15)
            if stop.is_set():
                break
            if updates is None:
                self.stderr.write('Telegram yangilanishlarini olishda xato; 5 soniyadan keyin qayta urinadi.')
                stop.wait(5)
                continue

            if not isinstance(updates, list):
                self.stderr.write('Telegram javobi noto‘g‘ri; qayta uriniladi.')
                stop.wait(5)
                continue
            retry = False
            for update in updates:
                if stop.is_set():
                    break
                update_id = update.get('update_id') if isinstance(update, dict) else None
                if type(update_id) is not int:
                    self.stderr.write('update_id yo‘q yangilanish o‘tkazib yuborildi.')
                    continue
                try:
                    close_old_connections()
                    delivered = process_update(update)
                except Exception as exc:
                    self.stderr.write(f'Telegram yangilanishi saqlanmadi ({type(exc).__name__}); qayta uriniladi.')
                    delivered = False
                finally:
                    close_old_connections()
                if not delivered:
                    self.stderr.write(
                        f'Telegram javobi #{update_id} yuborilmadi; yangilanish keyinroq qayta urinadi.'
                    )
                    retry = True
                    break
                offset = update_id + 1
            if retry:
                stop.wait(5)
