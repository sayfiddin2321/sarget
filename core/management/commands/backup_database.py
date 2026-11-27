from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import connection

from core.backups import create_backup
from core.models import OperationalRun


class Command(BaseCommand):
    help = 'SQLite bazasi va media rasmlarini tekshirilgan ZIP zaxiraga olish'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', help='Zaxira saqlanadigan papka')

    def handle(self, *args, **options):
        # Backing up must also work before applying this update's migration.
        available = OperationalRun._meta.db_table in connection.introspection.table_names()
        run = OperationalRun.objects.create(job='backup') if available else None
        try:
            path, count = create_backup(options.get('output_dir'))
        except Exception as exc:
            if run:
                run.status = 'failed'
                run.details = {'error': type(exc).__name__}
            raise CommandError('Zaxiralash bajarilmadi: ' + str(exc)) from exc
        else:
            if run:
                run.status = 'success'
                run.details = {'archive': path.name, 'media_files': count, 'verified': True}
            self.stdout.write(self.style.SUCCESS(f'Zaxira tayyor, baza va fayllar tekshirildi: {path}'))
        finally:
            if run:
                run.finished_at = timezone.now()
                run.save(update_fields=['status', 'details', 'finished_at'])
