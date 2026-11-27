from django.core.management.base import BaseCommand
from core.backups import verify_backup


class Command(BaseCommand):
    help = 'Zaxira fayllari va bazani tekshirish; ixtiyoriy yangi papkaga tiklash'

    def add_arguments(self, parser):
        parser.add_argument('archive')
        parser.add_argument('--restore-to', help='Yangi, hali mavjud bo‘lmagan papka; ishchi baza almashtirilmaydi')

    def handle(self, *args, **options):
        count = verify_backup(options['archive'], options.get('restore_to'))
        self.stdout.write(self.style.SUCCESS(f'Zaxira tekshirildi: baza yaxlit, {count} ta media fayl mos.'))
