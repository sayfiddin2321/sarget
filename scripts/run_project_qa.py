"""Run CRM QA in a new database, recording individual outcomes and full logs."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('labels', nargs='*', default=['core'])
parser.add_argument('--sqlite', action='store_true')
parser.add_argument('--no-browser', action='store_true')
args = parser.parse_args()
run_id = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8]
output = ROOT / 'artifacts' / 'qa' / run_id
output.mkdir(parents=True)
os.environ['DJANGO_SETTINGS_MODULE'] = 'sargetcrm.settings'
os.environ['TELEGRAM_BOT_TOKEN'] = ''
os.environ['TELEGRAM_STAFF_CHAT_ID'] = ''
os.environ['TELEGRAM_BOT_MODE'] = 'disabled'
os.environ['CRM_BACKGROUND_JOBS'] = 'False'
os.environ['CRM_API_KEY'] = 'isolated-qa-api-key'
if args.sqlite:
    os.environ['DB_ENGINE'] = 'sqlite'
    from unittest.mock import patch
    patch('decouple.RepositoryEnv', return_value={}).start()

from django.conf import settings

database = deepcopy(settings.DATABASES['default'])
original_name = str(database['NAME'])
test_name = 'test_sarget_qa_' + uuid4().hex[:12]
if database['ENGINE'].endswith('postgresql'):
    # Even the default connection cannot reach the application database.
    database['NAME'] = test_name
    database['TEST'] = {'NAME': test_name}
elif args.sqlite:
    database['NAME'] = ':memory:'
    database['TEST'] = {'NAME': ':memory:'}
else:
    raise SystemExit('Expected PostgreSQL. Use --sqlite explicitly for SQLite QA.')
assert str(database['NAME']) != original_name
database['CONN_MAX_AGE'] = 0
settings.DATABASES = {'default': database}
media = tempfile.TemporaryDirectory(prefix='sarget-qa-media-')
settings.MEDIA_ROOT = Path(media.name)
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
settings.ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
if not args.no_browser:
    browser = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    if browser.exists():
        for name in ('ROSTER_TEST_CHROMIUM', 'NOTIFICATION_TEST_CHROMIUM', 'RECEIPT_PRINT_CHROMIUM'):
            os.environ[name] = str(browser)
        os.environ['ROSTER_TEST_ARTIFACTS'] = str(output / 'rosters')
        os.environ['NOTIFICATION_TEST_ARTIFACTS'] = str(output / 'notifications')
        os.environ['RECEIPT_PRINT_ARTIFACTS'] = str(output / 'receipts')

import django
django.setup()
from django.test.runner import DiscoverRunner

records = []
subtests = []
requests = []
current_test = None
from django.core.handlers.base import BaseHandler
original_response = BaseHandler.get_response


def traced_response(handler, request):
    response = original_response(handler, request)
    match = getattr(request, 'resolver_match', None)
    requests.append({'test': current_test, 'method': request.method, 'path': request.path,
                     'route': match.view_name if match else None, 'status': response.status_code})
    return response


BaseHandler.get_response = traced_response


class Result(unittest.TextTestResult):
    def startTest(self, test):
        global current_test
        current_test = test.id()
        self.started_at = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        if not any(row['test'] == test.id() for row in records):
            self.record(test, 'FAIL', 'See failed subtests.')
        super().stopTest(test)

    def record(self, test, status, detail=''):
        records.append({'test': test.id(), 'status': status, 'detail': detail,
                        'seconds': round(time.monotonic() - getattr(self, 'started_at', time.monotonic()), 4)})

    def addSuccess(self, test):
        self.record(test, 'PASS')
        super().addSuccess(test)

    def addFailure(self, test, err):
        self.record(test, 'FAIL', self._exc_info_to_string(err, test))
        super().addFailure(test, err)

    def addError(self, test, err):
        self.record(test, 'FAIL', self._exc_info_to_string(err, test))
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.record(test, 'BLOCKED', reason)
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        subtests.append({'test': test.id(), 'case': str(subtest),
                         'status': 'FAIL' if err else 'PASS',
                         'detail': self._exc_info_to_string(err, test) if err else ''})
        super().addSubTest(test, subtest, err)


class TextRunner(unittest.TextTestRunner):
    resultclass = Result


class Runner(DiscoverRunner):
    test_runner = TextRunner

    def get_test_runner_kwargs(self):
        return {**super().get_test_runner_kwargs(), 'stream': log}


print('QA artifacts:', output, flush=True)
print('Isolated database:', database['ENGINE'], test_name if not args.sqlite else ':memory:', flush=True)
start = time.monotonic()
failure_count = None
try:
    with (output / 'tests.log').open('w', encoding='utf-8') as log:
        failure_count = Runner(verbosity=2, interactive=False).run_tests(args.labels or ['core'])
finally:
    summary = {'backend': database['ENGINE'], 'isolated_database': test_name if not args.sqlite else ':memory:',
               'application_database_accessed': False, 'labels': args.labels or ['core'],
               'seconds': round(time.monotonic() - start, 3), 'failure_count': failure_count,
               'passed': sum(r['status'] == 'PASS' for r in records),
               'failed': sum(r['status'] == 'FAIL' for r in records),
               'skipped': sum(r['status'] == 'BLOCKED' for r in records), 'tests': records}
    summary['test_methods'] = len(records)
    summary['subtests_passed'] = sum(r['status'] == 'PASS' for r in subtests)
    summary['subtests_failed'] = sum(r['status'] == 'FAIL' for r in subtests)
    (output / 'requests.json').write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'subtests.json').write_text(json.dumps(subtests, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'tests'}, ensure_ascii=False), flush=True)
    for record in records:
        if record['status'] != 'PASS':
            print(record['test'], record['status'], record['detail'][-3500:], flush=True)
    media.cleanup()
sys.exit(bool(failure_count))
