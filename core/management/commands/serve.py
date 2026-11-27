from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from core.runtime import ServerRuntime, close_database_connections


class Command(BaseCommand):
    help = 'Production: bitta buyruqda CRM, Telegram va fon vazifalarini ishga tushirish'

    def add_arguments(self, parser):
        parser.add_argument('--host', default='127.0.0.1')
        parser.add_argument('--port', type=int, default=8000)
        parser.add_argument('--threads', type=int, default=4)
        parser.add_argument('--trusted-proxy', default='127.0.0.1', help='HTTPS reverse proxy IP manzili')
        parser.add_argument('--without-bot', action='store_true')
        parser.add_argument('--without-jobs', action='store_true')

    def handle(self, *args, **options):
        if settings.DEBUG:
            raise CommandError('Production uchun DJANGO_DEBUG=False kiriting. Lokal ish uchun runserver ishlating.')
        if not 1 <= options['port'] <= 65535 or not 1 <= options['threads'] <= 32:
            raise CommandError('Port 1–65535, threads 1–32 oralig‘ida bo‘lsin.')
        if options['trusted_proxy'] == '*':
            raise CommandError('trusted-proxy uchun aniq IP manzil kiriting.')
        connection = connections['default']
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError('Avval python manage.py migrate buyrug‘ini bajaring.')
        close_database_connections()
        try:
            from waitress import create_server
        except ImportError:
            raise CommandError('Avval python -m pip install -r requirements.txt buyrug‘ini bajaring.') from None
        server = create_server(get_wsgi_application(), host=options['host'], port=options['port'],
                               threads=options['threads'], trusted_proxy=options['trusted_proxy'],
                               trusted_proxy_headers={'x-forwarded-proto', 'x-forwarded-for'},
                               clear_untrusted_proxy_headers=True)
        runtime = ServerRuntime(self.stdout, self.stderr, without_bot=options['without_bot'], without_jobs=options['without_jobs'])
        try:
            runtime.start()
            self.stdout.write(self.style.SUCCESS(f"CRM http://{options['host']}:{options['port']} da ishlayapti (HTTPS reverse proxy orqali oching)."))
            server.run()
        except KeyboardInterrupt:
            self.stdout.write('CRM va fon jarayonlari to‘xtatilmoqda.')
        finally:
            runtime.stop()
            server.task_dispatcher.shutdown()
            server.close()
