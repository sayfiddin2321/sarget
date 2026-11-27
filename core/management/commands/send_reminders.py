"""Create CRM reminders and durable Telegram delivery tasks; run every minute."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import OperationalRun, TelegramDelivery
from core.reminders import (
    dispatch_due_callback_reminders,
    dispatch_new_lead_reminders,
    dispatch_student_payment_reminders,
)


class Command(BaseCommand):
    help = 'CRM eslatmalari va Telegram yuborish navbatini yaratish'

    def handle(self, *args, **options):
        run = OperationalRun.objects.create(job='reminders')
        try:
            now, today = timezone.now(), timezone.localdate()
            dispatch_new_lead_reminders(now)
            dispatch_due_callback_reminders(now)
            dispatch_student_payment_reminders(now)
            run.status = 'success'
            run.details = {
                'telegram_sent': TelegramDelivery.objects.filter(sent_at__date=today).count(),
                'telegram_pending': TelegramDelivery.objects.filter(status__in=['pending', 'retry', 'running']).count(),
                'telegram_failed': TelegramDelivery.objects.filter(status='failed').count(),
            }
        except Exception as exc:
            run.status, run.details = 'failed', {'error': type(exc).__name__}
            raise
        finally:
            run.finished_at = timezone.now()
            run.save(update_fields=['status', 'details', 'finished_at'])
        self.stdout.write(self.style.SUCCESS('Eslatmalar va yuborish navbati tekshirildi'))
