from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import Mock, patch

from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from .management.commands.run_telegram_bot import Command as BotCommand
from .management.commands.runserver import Command as RunserverCommand, DjangoRunserver
from .runtime import ServerRuntime, bot_mode, process_lock


@override_settings(TELEGRAM_BOT_TOKEN='dummy-token', TELEGRAM_BOT_MODE='auto', CRM_BACKGROUND_JOBS=True)
class ServerLifecycleTests(SimpleTestCase):
    def test_default_mode_is_polling_locally_and_webhook_in_production(self):
        with override_settings(DEBUG=True):
            self.assertEqual(bot_mode(), 'polling')
        with override_settings(DEBUG=False):
            self.assertEqual(bot_mode(), 'webhook')
        with override_settings(TELEGRAM_BOT_TOKEN=''):
            self.assertEqual(bot_mode(), 'disabled')
        with override_settings(TELEGRAM_BOT_MODE='invalid'):
            with self.assertRaises(CommandError):
                bot_mode()

    @override_settings(DEBUG=True)
    def test_runtime_starts_both_workers_and_sets_stop_event(self):
        with patch('core.runtime.Thread') as thread:
            runtime = ServerRuntime(StringIO(), StringIO()).start()
            self.assertEqual(thread.call_count, 2)
            self.assertEqual([call.kwargs['name'] for call in thread.call_args_list],
                             ['crm-run_telegram_bot', 'crm-process_crm_jobs'])
            runtime.stop()
            self.assertTrue(runtime.stop_event.is_set())

    @override_settings(DEBUG=False, TELEGRAM_PUBLIC_URL='https://crm.example.test', TELEGRAM_WEBHOOK_SECRET='test-secret')
    def test_webhook_mode_registers_once_without_polling(self):
        with patch('core.runtime.call_command') as command, patch('core.runtime.Thread') as thread:
            ServerRuntime(StringIO(), StringIO(), without_jobs=True).start()
            command.assert_not_called()
            self.assertEqual(thread.call_args.kwargs['name'], 'crm-setup_telegram_webhook')
            self.assertEqual(thread.call_args.kwargs['args'], ('setup_telegram_webhook', {}, ('https://crm.example.test',), True))

    def test_webhook_registration_retries_network_error_then_finishes(self):
        runtime = ServerRuntime(StringIO(), StringIO())
        runtime.stop_event.wait = Mock()
        with patch('core.runtime.call_command', side_effect=[CommandError('API unavailable'), None]) as command, \
                patch('core.runtime.connections.close_all'):
            runtime._supervise('setup_telegram_webhook', {}, ('https://crm.example.test',), True)
        self.assertEqual(command.call_count, 2)
        self.assertNotIn('stop_event', command.call_args.kwargs)
        self.assertFalse(runtime.stop_event.is_set())

    @override_settings(DEBUG=False, TELEGRAM_PUBLIC_URL='')
    def test_missing_public_url_fails_before_starting_threads(self):
        with patch('core.runtime.Thread') as thread:
            with self.assertRaises(CommandError):
                ServerRuntime(StringIO(), StringIO()).start()
            thread.assert_not_called()

    def test_runserver_override_preserves_staticfiles_and_starts_only_after_bind(self):
        self.assertEqual(get_commands()['runserver'], 'core')
        command = RunserverCommand(stdout=StringIO(), stderr=StringIO())
        with patch('core.management.commands.runserver.ServerRuntime') as runtime:
            runtime.assert_not_called()
            with patch.object(DjangoRunserver, 'inner_run', autospec=True,
                              side_effect=lambda cmd, *args, **kwargs: cmd.on_bind(8000)), patch.object(DjangoRunserver, 'on_bind'):
                command.inner_run(without_bot=False, without_jobs=False)
            runtime.assert_called_once()
            runtime.return_value.start.assert_called_once()
            runtime.return_value.stop.assert_called_once()

    def test_worker_restarts_after_failure_without_logging_secret_exception_text(self):
        output = StringIO()
        runtime = ServerRuntime(StringIO(), output)
        runtime.stop_event.wait = Mock()
        attempts = []
        def worker(*args, **kwargs):
            attempts.append(args[0])
            if len(attempts) == 1:
                raise RuntimeError('DO-NOT-LOG-TOKEN')
            runtime.stop_event.set()
        with patch('core.runtime.call_command', side_effect=worker), patch('core.runtime.connections.close_all'):
            runtime._supervise('run_telegram_bot', {})
        self.assertEqual(len(attempts), 2)
        self.assertIn('RuntimeError', output.getvalue())
        self.assertNotIn('DO-NOT-LOG-TOKEN', output.getvalue())

    def test_older_django_handler_fallback_starts_runtime_once(self):
        command = RunserverCommand(stdout=StringIO(), stderr=StringIO())
        command.runtime = None
        command.runtime_options = {'without_bot': False, 'without_jobs': False}
        with patch('core.management.commands.runserver.HAS_BIND_HOOK', False), \
                patch.object(DjangoRunserver, 'get_handler'), patch('core.management.commands.runserver.ServerRuntime') as runtime:
            command.get_handler()
            command.get_handler()
        runtime.return_value.start.assert_called_once()

    def test_duplicate_process_lock_is_rejected_and_lock_releases_after_exception(self):
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=Path(directory)):
            with process_lock('telegram-polling', 'secret-token'):
                with self.assertRaises(CommandError):
                    with process_lock('telegram-polling', 'secret-token'):
                        self.fail('Second process acquired the lock')
            try:
                with process_lock('telegram-polling', 'secret-token'):
                    raise ValueError('test')
            except ValueError:
                pass
            with process_lock('telegram-polling', 'secret-token'):
                pass
            self.assertNotIn('secret-token', ''.join(path.name for path in Path(directory).rglob('*')))

    @override_settings(TELEGRAM_WEBHOOK_SECRET='test-secret')
    def test_webhook_setup_preserves_pending_updates_and_validates_configuration(self):
        with patch('core.management.commands.setup_telegram_webhook.telegram_api', return_value=True) as api:
            call_command('setup_telegram_webhook', 'https://crm.example.test', stdout=StringIO())
            payload = api.call_args.args[1]
            self.assertEqual(payload['url'], 'https://crm.example.test/integrations/telegram/webhook/')
            self.assertEqual(payload['secret_token'], 'test-secret')
            self.assertNotIn('drop_pending_updates', payload)
            api.reset_mock()
            for url in ('http://crm.example.test', 'https://crm.example.test/path', 'https://user:password@crm.example.test'):
                with self.assertRaises(CommandError):
                    call_command('setup_telegram_webhook', url, stdout=StringIO())
            api.assert_not_called()


class PollingTests(SimpleTestCase):
    def test_polling_does_not_acknowledge_failed_update_and_stops_cleanly(self):
        stop = Event()
        stop.wait = Mock(side_effect=lambda timeout: stop.set())
        cmd = BotCommand(stdout=StringIO(), stderr=StringIO())
        with patch('core.management.commands.run_telegram_bot.telegram_api_result', side_effect=[
            {'url': ''}, {'username': 'test_bot'}, [{'update_id': 12}, {'update_id': 13}],
        ]) as api, patch('core.management.commands.run_telegram_bot.process_update', return_value=False) as process, \
                patch('core.management.commands.run_telegram_bot.close_old_connections'):
            cmd.poll(stop)
        process.assert_called_once_with({'update_id': 12})
        self.assertEqual(api.call_args.args[1]['offset'], None)
        self.assertTrue(stop.is_set())

    def test_success_advances_offset_and_shutdown_does_not_process_new_batch(self):
        stop = Event()
        cmd = BotCommand(stdout=StringIO(), stderr=StringIO())
        offsets = []
        def api(method, payload=None, **kwargs):
            if method == 'getWebhookInfo':
                return {'url': ''}
            if method == 'getMe':
                return {'username': 'test_bot'}
            offsets.append(payload['offset'])
            if len(offsets) == 1:
                return [{'update_id': 12}]
            stop.set()
            return [{'update_id': 13}]
        with patch('core.management.commands.run_telegram_bot.telegram_api_result', side_effect=api), \
                patch('core.management.commands.run_telegram_bot.process_update', return_value=True) as process, \
                patch('core.management.commands.run_telegram_bot.close_old_connections'):
            cmd.poll(stop)
        self.assertEqual(offsets, [None, 13])
        process.assert_called_once_with({'update_id': 12})

    def test_existing_webhook_is_not_deleted_by_polling(self):
        with patch('core.management.commands.run_telegram_bot.telegram_api_result', return_value={'url': 'https://production.test'}) as api:
            with self.assertRaises(CommandError):
                BotCommand(stdout=StringIO(), stderr=StringIO()).poll(Event())
            api.assert_called_once_with('getWebhookInfo')


@override_settings(DEBUG=False, TELEGRAM_BOT_TOKEN='', CRM_BACKGROUND_JOBS=False)
class ProductionCommandTests(TestCase):
    def test_production_server_binds_then_starts_runtime_and_cleans_up(self):
        with patch('waitress.create_server') as create, patch('core.management.commands.serve.ServerRuntime') as runtime:
            call_command('serve', stdout=StringIO())
        self.assertEqual(create.call_args.kwargs['host'], '127.0.0.1')
        self.assertEqual(create.call_args.kwargs['trusted_proxy_headers'], {'x-forwarded-proto', 'x-forwarded-for'})
        create.return_value.run.assert_called_once()
        create.return_value.close.assert_called_once()
        runtime.return_value.start.assert_called_once()
        runtime.return_value.stop.assert_called_once()

    def test_startup_failure_closes_bound_server(self):
        with patch('waitress.create_server') as create, patch('core.management.commands.serve.ServerRuntime') as runtime:
            runtime.return_value.start.side_effect = CommandError('Webhook unavailable')
            with self.assertRaises(CommandError):
                call_command('serve', stdout=StringIO())
        create.return_value.run.assert_not_called()
        create.return_value.close.assert_called_once()
        runtime.return_value.stop.assert_called_once()

    @override_settings(DEBUG=True)
    def test_production_command_rejects_debug(self):
        with self.assertRaises(CommandError):
            call_command('serve', stdout=StringIO())

    def test_unapplied_migrations_prevent_startup(self):
        with patch('core.management.commands.serve.MigrationExecutor') as executor, patch('waitress.create_server') as create:
            executor.return_value.migration_plan.return_value = ['pending']
            with self.assertRaises(CommandError):
                call_command('serve', stdout=StringIO())
        create.assert_not_called()
