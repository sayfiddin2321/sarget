from datetime import timedelta
from threading import Event
from time import monotonic
from io import StringIO
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings
from django.utils import timezone
from core.models import ReportJob, OperationalRun, TelegramDelivery
from core.report_files import generate_job
from core.messaging import queue_subscriptions, process_deliveries
from core.runtime import close_database_connections, process_lock


class Command(BaseCommand):
    help = 'Hisobot fayllari, oylik obunalar va Telegram yuborish navbatini bajarish'
    stealth_options = ('stop_event',)

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true', help='Har 2 soniyada navbatni tekshirish')
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--with-reminders', action='store_true', help='Har daqiqada CRM eslatmalarini ham tekshirish')
        parser.add_argument('--skip-telegram', action='store_true', help='Token bo‘lmaganda Telegram navbatiga tegmaslik')

    def handle(self, *args, **options):
        with process_lock('crm-jobs', settings.DATABASES['default']['NAME']):
            try:
                self.process(options)
            finally:
                close_database_connections()

    def process(self, options):
        stop = options.get('stop_event') or Event()
        next_reminder = 0
        run = OperationalRun.objects.create(job='report_worker')
        try:
            while not stop.is_set():
                close_database_connections(stale_only=True)
                run.status, run.started_at, run.finished_at = 'running', timezone.now(), None
                run.save(update_fields=['status', 'started_at', 'finished_at'])
                if options['with_reminders'] and monotonic() >= next_reminder:
                    call_command('send_reminders', stdout=StringIO())
                    next_reminder = monotonic() + 60
                queue_subscriptions()
                now = timezone.now()
                ReportJob.objects.filter(status='running', started_at__lt=now - timedelta(minutes=30)).update(status='pending')
                for pk in ReportJob.objects.filter(status='pending').order_by('created_at').values_list('pk', flat=True)[:max(1, min(options['limit'], 100))]:
                    if not ReportJob.objects.filter(pk=pk, status='pending').update(status='running', started_at=now):
                        continue
                    job = ReportJob.objects.select_related('owner').get(pk=pk)
                    try:
                        generate_job(job)
                    except Exception as exc:
                        job.status, job.error, job.completed_at = 'failed', type(exc).__name__, timezone.now()
                        job.save(update_fields=['status', 'error', 'completed_at'])
                if not options['skip_telegram']:
                    process_deliveries(limit=max(1, min(options['limit'], 100)))
                run.status, run.finished_at = 'success', timezone.now()
                run.details = {'reports_pending': ReportJob.objects.filter(status__in=['pending', 'running']).count(),
                               'telegram_pending': TelegramDelivery.objects.filter(status__in=['pending', 'retry', 'running']).count(),
                               'telegram_failed': TelegramDelivery.objects.filter(status='failed').count()}
                run.save(update_fields=['status', 'finished_at', 'details'])
                if not options['loop']:
                    break
                stop.wait(2)
        except KeyboardInterrupt:
            self.stdout.write('Vazifalar jarayoni to‘xtatildi.')
        except Exception as exc:
            run.status, run.finished_at, run.details = 'failed', timezone.now(), {'error': type(exc).__name__}
            run.save(update_fields=['status', 'finished_at', 'details'])
            raise
