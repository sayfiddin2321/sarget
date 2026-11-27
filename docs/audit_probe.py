"""Read current application behavior using an isolated, in-memory database.

Run from the project root: python docs/audit_probe.py
This records defects; it is an audit snapshot, not a passing regression suite.
No Telegram requests are sent and the project's database is never opened.
"""
import json
import os
import sys
from datetime import date, time, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sargetcrm.settings')
from django.conf import settings

settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
settings.ALLOWED_HOSTS = ['testserver']
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

import django
django.setup()
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.template import Context, Template
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from core.forms import ExpenseForm, GroupForm, StudentForm, TeacherForm
from core.models import Attendance, Grade, Group, Lead, Payment, Receptionist, Salary, Student, Teacher
from core.permissions import get_role

call_command('migrate', verbosity=0)
results = []


def record(key, observed, **details):
    results.append({'id': key, 'observed': observed, **details})


User = get_user_model()
unknown = User.objects.create_user('audit_unknown', password='audit-pass')
admin = User.objects.create_user('audit_admin', password='audit-pass', is_superuser=True, is_staff=True)
teacher_user = User.objects.create_user('audit_teacher', password='audit-pass')
teacher = Teacher.objects.create(name='Audit Teacher', phone='900000001', subject='Test', user=teacher_user)
other_teacher = Teacher.objects.create(name='Other Teacher', phone='900000002', subject='Test')
rec_user = User.objects.create_user('audit_reception', password='audit-pass')
rec = Receptionist.objects.create(name='Audit Reception', phone='900000003', user=rec_user)
rec2 = Receptionist.objects.create(name='Other Reception', phone='900000004')
group = Group.objects.create(name='Audit Group', teacher=other_teacher, days='1-3-5',
                             start_time=time(10), end_time=time(11), monthly_fee=500000, max_students=1)
student = Student.objects.create(name='Audit Student', phone='+998900000005', group=group,
                                 teacher=other_teacher, receptionist=rec2, status='active')
client = Client(raise_request_exception=False)

client.force_login(unknown)
response = client.get(reverse('dashboard'))
record('P01_unknown_dashboard', response.status_code, role=get_role(unknown), exposes_finance_labels='Bu oylik tushum' in response.content.decode())
response = client.post(reverse('payment_create'), {'student': student.pk, 'amount': '1000', 'month': '2026-10', 'payment_type': 'cash'})
record('P02_unknown_payment_create', response.status_code, payment_created=Payment.objects.filter(received_by=unknown).exists())

client.force_login(teacher_user)
response = client.get(reverse('api_group_students', args=[group.pk]))
record('P03_teacher_other_group_api', response.status_code, students=response.json())

client.force_login(rec_user)
denied = client.get(reverse('student_detail', args=[student.pk]))
card = client.get(reverse('student_card_print', args=[student.pk]))
record('P04_reception_card_scope', card.status_code, detail_status=denied.status_code, exposes_other_student=student.name in card.content.decode())
grade = Grade.objects.create(student=student, group=group, date=date(2026, 10, 29), score=80, graded_by=teacher_user)
response = client.get(reverse('grade_delete', args=[grade.pk]))
record('P05_grade_delete_get', response.status_code, deleted=not Grade.objects.filter(pk=grade.pk).exists(), actor='receptionist')
response = client.post(reverse('take_attendance', args=[group.pk]), {f'attendance_{student.pk}': 'unrecognised-status'})
record('P06_reception_attendance_invalid', response.status_code, saved_status=Attendance.objects.get(student=student, group=group).status)

client.logout()
response = client.post(reverse('login') + '?next=https://example.invalid/audit', {'username': unknown.username, 'password': 'audit-pass'})
record('P07_login_redirect', response.status_code, location=response.get('Location'))

with patch('core.models.date') as model_date:
    model_date.today.return_value = date(2026, 10, 29)
    partial = Student.objects.create(name='Partial audit', phone='900000006', group=group)
    Student.objects.filter(pk=partial.pk).update(registration_date=date(2026, 8, 1))
    Payment.objects.create(student=partial, amount=1, month=date(2026, 10, 1))
    partial.refresh_from_db()
    record('P08_partial_debt', partial.get_debt_months(), monthly_fee=str(partial.get_effective_fee()), paid='1', registration_date=str(partial.registration_date))

form = ExpenseForm({'title': 'Audit', 'category': 'other', 'amount': '-1000', 'date': '2026-10-29'})
record('P09_negative_expense', form.is_valid(), errors=form.errors.get_json_data())
form = StudentForm({'name': 'Mismatch audit', 'phone': '900000007', 'teacher': teacher.pk,
                    'group': group.pk, 'status': 'active', 'source': 'walk_in', 'discount_percent': '0'})
record('P10_group_teacher_capacity', form.is_valid(), group_is_full=group.is_full(), teacher_matches_group=teacher.pk == group.teacher_id)
Grade.objects.bulk_create([Grade(student=student, group=group, date=date(2026, 10, 29), grade_type='exam', score=80) for _ in range(2)])
record('P11_duplicate_grade', Grade.objects.filter(student=student, group=group, date=date(2026, 10, 29), grade_type='exam').count())

form = TeacherForm({'name': 'New audit teacher', 'phone': '900000009', 'subject': 'Test', 'percent': '40',
                    'username': 'audit_without_password', 'password': '', 'is_active': 'on'})
valid = form.is_valid()
try:
    form.save()
    error = None
except Exception as exc:
    error = type(exc).__name__ + ': ' + str(exc)
record('P12_teacher_empty_password', valid, save_error=error)

pay = Payment.objects.create(student=student, amount=10000, month=date(2026, 10, 1))
student.receptionist = rec
student.save()
pay.amount = 20000
try:
    with transaction.atomic():
        pay.save()
    error = None
except IntegrityError as exc:
    error = type(exc).__name__
record('P13_commission_reassignment', error)

client.force_login(admin)


class Charts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.charts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'canvas' and 'data-chart' in attrs:
            raw = attrs['data-chart']
            try:
                json.loads(raw)
                valid = True
            except ValueError:
                valid = False
            self.charts.append({'id': attrs.get('id'), 'raw': raw, 'valid_json': valid})


for name in ['dashboard', 'reports']:
    response = client.get(reverse(name))
    parser = Charts()
    parser.feed(response.content.decode())
    record('P14_chart_' + name, response.status_code, charts=parser.charts)

with patch('core.views.date') as view_date:
    view_date.today.return_value = date(2026, 3, 1)
    view_date.side_effect = date
    # Demonstrate the exact expression used by the views independently of templates.
    months = [(date(2026, 3, 1) - timedelta(days=30 * i)).replace(day=1).isoformat() for i in range(11, -1, -1)]
record('P15_month_series', months, unique_count=len(set(months)))

Attendance.objects.update_or_create(student=student, group=group, date=date.today(), defaults={'status': 'absent'})
response = client.get(reverse('take_attendance', args=[group.pk]))
html = response.content.decode()
record('P16_attendance_reopen', response.status_code, absent_radio_checked=('value="absent"\n                checked' in html), model_object_used_as_css_class=('marked-Audit Student' in html))

lead = Lead.objects.create(name='Enroll audit', phone='900000010', course='Test')
client.force_login(rec_user)
response = client.post(reverse('lead_enroll', args=[lead.pk]))
lead.refresh_from_db()
next_response = client.get(response['Location'])
record('P17_enroll_handoff', response.status_code, student_receptionist=lead.student.receptionist_id,
       status=lead.status, target=response['Location'], target_status=next_response.status_code,
       next_target=next_response.get('Location'), visible_in_reception_list=Student.objects.filter(pk=lead.student_id, receptionist=rec).exists())

client.force_login(admin)
salary = Salary.objects.create(teacher=other_teacher, month=date(2026, 10, 1), total_income=10000, percent=40, salary_amount=4000, is_paid=True)
client.post(reverse('calculate_salaries'), {'month': '2026-10'})
salary.refresh_from_db()
record('P18_paid_salary_recalculation', str(salary.salary_amount), still_paid=salary.is_paid, original_salary='4000')

client.post(reverse('student_delete', args=[student.pk]))
record('P19_student_delete_finance', Payment.objects.filter(pk=pay.pk).exists(), meaning='whether original payment survives student deletion')

from core.reminders import dispatch_due_callback_reminders, lead_staff
from core.models import Notification
callback = Lead.objects.create(name='Callback audit', course='Test', status='callback', follow_up_at=timezone.now())
dispatch_due_callback_reminders()
before = Notification.objects.filter(message__startswith=callback.name + ' |').count()
callback.follow_up_at = timezone.now() + timedelta(hours=1)
callback.save()
dispatch_due_callback_reminders(timezone.now() + timedelta(minutes=55))
after = Notification.objects.filter(message__startswith=callback.name + ' |').count()
record('P20_callback_reschedule', after - before, initial_notifications=before, meaning='notifications for the second callback on the same calendar day')
teacher.is_active = False
teacher.save()
client.force_login(teacher_user)
record('P21_inactive_profile', client.get(reverse('dashboard')).status_code, role=get_role(teacher_user), user_active=teacher_user.is_active)
client.force_login(admin)
import logging
logging.getLogger('django.request').disabled = True
record('P22_malformed_filter', client.get(reverse('student_list'), {'teacher': 'not-an-id'}).status_code)
record('P23_invalid_salary_month', client.post(reverse('calculate_salaries'), {'month': '2026-13'}).status_code)

from django.test.utils import CaptureQueriesContext
from django.db import connection
with CaptureQueriesContext(connection) as captured:
    client.get(reverse('receptionist_list'))
small_queries = len(captured)
Receptionist.objects.bulk_create([Receptionist(name=f'Audit Reception {i}', phone='900000000') for i in range(10)])
with CaptureQueriesContext(connection) as captured:
    client.get(reverse('receptionist_list'))
record('P24_reception_list_query_growth', len(captured), previous_queries=small_queries, added_receptionists=10)

output = {'audit_date': '2026-10-29', 'database': ':memory:', 'django': django.get_version(),
          'scope': 'Synthetic data only; HTTP and template probes, no real browser or load test.', 'results': results}
target = ROOT / 'docs' / 'audit_evidence_2026-10-29.json'
target.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(json.dumps(output, ensure_ascii=True, indent=2, default=str))
