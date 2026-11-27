from django.contrib.staticfiles.management.commands.runserver import Command as DjangoRunserver

from core.runtime import ServerRuntime

HAS_BIND_HOOK = hasattr(DjangoRunserver, 'on_bind')


class Command(DjangoRunserver):
    help = 'CRM, Telegram polling va fon vazifalarini birga ishga tushirish (lokal muhit)'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--without-bot', action='store_true', help='Telegram botni boshlamaslik')
        parser.add_argument('--without-jobs', action='store_true', help='Fon vazifalarini boshlamaslik')

    def inner_run(self, *args, **options):
        self.runtime = None
        self.runtime_options = options
        try:
            return super().inner_run(*args, **options)
        finally:
            if self.runtime:
                self.runtime.stop()

    def on_bind(self, server_port):
        super().on_bind(server_port)
        self._start_runtime()

    def get_handler(self, *args, **options):
        handler = super().get_handler(*args, **options)
        # Older supported Django versions have no on_bind callback.
        if not HAS_BIND_HOOK:
            self._start_runtime()
        return handler

    def _start_runtime(self):
        if self.runtime is not None:
            return
        # Serving child only; after bind on Django versions that expose on_bind.
        self.runtime = ServerRuntime(self.stdout, self.stderr,
                                     without_bot=self.runtime_options['without_bot'],
                                     without_jobs=self.runtime_options['without_jobs'])
        self.runtime.start()
