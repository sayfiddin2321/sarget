"""Explicit server lifecycle, local process locks, and restartable background commands."""
import hashlib
import os
from contextlib import contextmanager
from threading import Event, Thread

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections


def close_database_connections(*, stale_only=False):
    """Leave connections owned by a caller's transaction open."""
    for connection in connections.all(initialized_only=True):
        if not connection.in_atomic_block:
            if stale_only:
                connection.close_if_unusable_or_obsolete()
            else:
                connection.close()


@contextmanager
def process_lock(name, identity):
    # Keep the inode: removing lock files on exit would let two processes lock different files.
    directory = settings.BASE_DIR / 'private' / 'runtime'
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(identity).encode()).hexdigest()[:24]
    handle = (directory / f'{name}-{digest}.lock').open('a+b')
    locked = False
    try:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise CommandError(f'{name} jarayoni bu loyihada allaqachon ishlayapti. Ikkinchi nusxa ishga tushirilmadi.') from None
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def bot_mode():
    mode = settings.TELEGRAM_BOT_MODE
    if mode not in ('auto', 'polling', 'webhook', 'disabled'):
        raise CommandError('TELEGRAM_BOT_MODE: auto, polling, webhook yoki disabled bo‘lsin.')
    if mode == 'disabled' or not settings.TELEGRAM_BOT_TOKEN:
        return 'disabled'
    return ('polling' if settings.DEBUG else 'webhook') if mode == 'auto' else mode


class ServerRuntime:
    def __init__(self, stdout, stderr, *, without_bot=False, without_jobs=False):
        self.stdout, self.stderr = stdout, stderr
        self.without_bot, self.without_jobs = without_bot, without_jobs
        self.stop_event = Event()
        self.threads = []

    def start(self):
        mode = 'disabled' if self.without_bot else bot_mode()
        if mode == 'webhook':
            if not settings.TELEGRAM_PUBLIC_URL:
                raise CommandError('Webhook uchun TELEGRAM_PUBLIC_URL=https://CRM-DOMAIN ni sozlang.')
            from .management.commands.setup_telegram_webhook import webhook_payload
            webhook_payload(settings.TELEGRAM_PUBLIC_URL)
            # Retry network failures without taking the CRM offline; finish after registration succeeds.
            self._start('setup_telegram_webhook', command_args=(settings.TELEGRAM_PUBLIC_URL,), once=True)
            self.stdout.write('Telegram webhook rejimi tanlandi; ulanish fonda sozlanmoqda.')
        elif mode == 'polling':
            self._start('run_telegram_bot')
        else:
            self.stdout.write('Telegram polling o‘chiq (token yo‘q, disabled yoki --without-bot).')
        if settings.CRM_BACKGROUND_JOBS and not self.without_jobs:
            self._start('process_crm_jobs', loop=True, with_reminders=True, skip_telegram=not bool(settings.TELEGRAM_BOT_TOKEN))
        return self

    def _start(self, command, *, command_args=(), once=False, **options):
        thread = Thread(target=self._supervise, args=(command, options, command_args, once), name=f'crm-{command}', daemon=True)
        self.threads.append(thread)
        thread.start()

    def _supervise(self, command, options, command_args=(), once=False):
        while not self.stop_event.is_set():
            try:
                lifecycle = {} if once else {'stop_event': self.stop_event}
                call_command(command, *command_args, stdout=self.stdout, stderr=self.stderr, **lifecycle, **options)
                if once:
                    return
            except CommandError as exc:
                self.stderr.write(f'{command}: {exc}')
            except Exception as exc:
                # Exception text can include request URLs containing bot tokens. Log only the class.
                self.stderr.write(f'{command}: {type(exc).__name__}; 5 soniyadan keyin qayta uriniladi.')
            finally:
                connections.close_all()
            if not self.stop_event.is_set():
                self.stop_event.wait(5)

    def stop(self):
        self.stop_event.set()
        # Workers are daemon threads; network operations have their own bounded timeouts.
        for thread in self.threads:
            thread.join(timeout=1)
