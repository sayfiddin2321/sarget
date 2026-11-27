"""Durable Telegram delivery queue. Live sending only happens in the worker."""
import json
from datetime import date, timedelta
from uuid import uuid4
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (GuardianBinding, Lead, Notification, ReportJob, ReportSubscription,
                     Student, TelegramBinding, TelegramDelivery)
from .permissions import has_capability, get_receptionist, visible_students
from .report_files import create_job, private_path, validate_job_access
from .reporting import Report


def student_recipients(student):
    if student.status == 'inactive':
        return []
    result = []
    for binding in TelegramBinding.objects.filter(role='student', target_id=student.pk, reports_enabled=True):
        result.append({'key': f'student:{binding.pk}', 'label': 'O‘quvchining tasdiqlangan Telegrami', 'chat_id': binding.chat_id})
    for binding in student.guardian_bindings.filter(reports_enabled=True):
        result.append({'key': f'guardian:{binding.pk}', 'label': f'Tasdiqlangan ota-ona/vasiy #{binding.pk}', 'chat_id': binding.chat_id})
    return result


def recipient_for_student(student, key):
    recipient = next((row for row in student_recipients(student) if row['key'] == key), None)
    if recipient is None:
        raise ValidationError('Tasdiqlangan va bildirishnomaga rozilik bergan Telegram qabul qiluvchini tanlang.')
    return recipient


def queue_text(*, key, chat_id, text, owner=None, student=None, lead=None, recipient=''):
    if not chat_id:
        return None
    delivery, _ = TelegramDelivery.objects.get_or_create(key=key, defaults={
        'chat_id': chat_id, 'text': text, 'owner': owner, 'student': student, 'lead': lead, 'recipient': recipient,
    })
    return delivery


def queue_staff_notifications(users, text, key, *, lead=None, student=None):
    for user in users:
        rec = get_receptionist(user)
        if rec and rec.is_active:
            binding = TelegramBinding.objects.filter(role='receptionist', target_id=rec.pk).first()
            if binding:
                queue_text(key=f'{key}:staff:{user.pk}', chat_id=binding.chat_id, text=text,
                           owner=user, recipient=f'staff:{user.pk}', lead=lead, student=student)
    raw_chat = settings.TELEGRAM_STAFF_CHAT_ID
    if raw_chat and str(raw_chat).lstrip('-').isdigit():
        queue_text(key=f'{key}:staff-group', chat_id=int(raw_chat), text=text,
                   recipient='staff-group', lead=lead, student=student)


@transaction.atomic
def queue_student_report(user, student, recipient_key, params, file_format, *, key=None):
    if not has_capability(user, 'messages.send') or not visible_students(user).filter(pk=student.pk).exists():
        raise PermissionDenied()
    recipient = recipient_for_student(student, recipient_key)
    data = dict(params)
    data['student'] = str(student.pk)
    if not key:
        normalized_filters = Report(user, 'student', data).form.serialized()
        queued = TelegramDelivery.objects.select_for_update().filter(
            student=student,
            owner=user,
            recipient=recipient_key,
            status__in=('pending', 'retry', 'running'),
            report_job__kind='student',
            report_job__file_format=file_format,
        ).select_related('report_job').order_by('-created_at')
        for delivery in queued:
            filters = {name: value for name, value in delivery.report_job.filters.items() if not name.startswith('_')}
            if filters == normalized_filters:
                return delivery
    key = key or f'student-report:{uuid4()}'
    existing = TelegramDelivery.objects.filter(key=key).first()
    if existing:
        return existing
    job = create_job(user, 'student', data, file_format)
    return TelegramDelivery.objects.create(key=key, chat_id=recipient['chat_id'], report_job=job,
                                           student=student, owner=user, recipient=recipient_key,
                                           text=f'{student.name}: davomat, baholar va oylik hisobot.')


def sync_linked_report_subscriptions(today=None):
    today = today or timezone.localdate()
    current_month = today.replace(day=1)
    next_month = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    student_ids = Student.objects.exclude(status='inactive').values('pk')
    bindings = [
        (binding.target_id, f'student:{binding.pk}', binding.reports_enabled, timezone.localdate(binding.verified_at))
        for binding in TelegramBinding.objects.filter(role='student', target_id__in=student_ids)
    ]
    bindings.extend(
        (binding.student_id, f'guardian:{binding.pk}', binding.reports_enabled, timezone.localdate(binding.verified_at))
        for binding in GuardianBinding.objects.filter(student_id__in=student_ids)
    )
    if not bindings:
        return

    owner = get_user_model().objects.filter(is_active=True, is_superuser=True).order_by('pk').first()
    if owner is None:
        raise ValidationError('Telegram hisobotlari uchun faol superuser hisobini yarating.')

    for student_id, recipient, reports_enabled, verified_on in bindings:
        first_run = current_month if verified_on <= current_month else next_month
        subscription, _ = ReportSubscription.objects.get_or_create(
            student_id=student_id,
            recipient=recipient,
            defaults={
                'owner': owner,
                'file_format': 'xlsx',
                'enabled': reports_enabled,
                'next_run_on': first_run,
            },
        )
        was_enabled = subscription.enabled
        changed_fields = []
        if subscription.owner_id != owner.pk:
            subscription.owner = owner
            changed_fields.append('owner')
        if subscription.file_format != 'xlsx':
            subscription.file_format = 'xlsx'
            changed_fields.append('file_format')
        if subscription.enabled != reports_enabled:
            subscription.enabled = reports_enabled
            changed_fields.append('enabled')
        if not reports_enabled and subscription.next_run_on <= today:
            subscription.next_run_on = next_month
            changed_fields.append('next_run_on')
        elif reports_enabled and not was_enabled and subscription.next_run_on <= today:
            subscription.next_run_on = next_month
            changed_fields.append('next_run_on')
        if changed_fields:
            subscription.save(update_fields=changed_fields)


def queue_subscriptions(today=None):
    today = today or timezone.localdate()
    sync_linked_report_subscriptions(today)
    for pk in ReportSubscription.objects.filter(enabled=True, next_run_on__lte=today).values_list('pk', flat=True):
        with transaction.atomic():
            sub = ReportSubscription.objects.select_for_update().get(pk=pk)
            if not sub.enabled or sub.next_run_on > today:
                continue
            # One closed month per iteration; after downtime, catch up month by month.
            end = sub.next_run_on.replace(day=1) - timedelta(days=1)
            params = {'date_from': end.replace(day=1).isoformat(), 'date_to': end.isoformat()}
            try:
                queue_student_report(sub.owner, sub.student, sub.recipient, params, sub.file_format,
                                     key=f'monthly-report:{sub.student_id}:{sub.recipient}:{end:%Y-%m}')
            except (PermissionDenied, ValidationError):
                sub.enabled = False
                sub.save(update_fields=['enabled'])
                continue
            month = sub.next_run_on
            sub.next_run_on = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
            sub.save(update_fields=['next_run_on'])


def validate_delivery(delivery):
    owner = delivery.owner
    if owner and (not owner.is_active or not has_capability(owner, 'messages.send') and not delivery.recipient.startswith('staff:')):
        raise PermissionDenied('Xodimning yuborish huquqi bekor qilingan.')
    if delivery.recipient.startswith(('student:', 'guardian:')):
        if not owner or not visible_students(owner).filter(pk=delivery.student_id).exists():
            raise PermissionDenied('O‘quvchi doirasi o‘zgargan.')
        try:
            recipient = recipient_for_student(delivery.student, delivery.recipient)
        except ValidationError as exc:
            raise PermissionDenied('Qabul qiluvchi ulanishni yoki hisobotlarni o‘chirgan.') from exc
        if recipient['chat_id'] != delivery.chat_id:
            raise PermissionDenied('Telegram ulanishi o‘zgargan.')
    elif delivery.recipient.startswith('staff:'):
        rec = get_receptionist(owner) if owner else None
        binding = TelegramBinding.objects.filter(role='receptionist', target_id=rec.pk, chat_id=delivery.chat_id).first() if rec and rec.is_active else None
        capability = 'leads.manage' if delivery.lead_id else 'payments.view'
        if not binding or not has_capability(owner, capability):
            raise PermissionDenied('Xodim ulanishi yoki huquqi o‘zgargan.')
    elif delivery.recipient == 'staff-group':
        if str(delivery.chat_id) != str(settings.TELEGRAM_STAFF_CHAT_ID):
            raise PermissionDenied('Xodimlar guruhi o‘zgargan.')
    elif delivery.recipient.startswith('lead:'):
        lead = delivery.lead
        if not owner or not has_capability(owner, 'leads.manage') or not lead or lead.archived_at:
            raise PermissionDenied()
        if not lead.telegram_chat_id or lead.telegram_chat_id != lead.telegram_user_id or lead.telegram_chat_id != delivery.chat_id:
            raise PermissionDenied('Murojaatning Telegram manzili tasdiqlanmagan.')
    elif delivery.recipient == 'manual':
        raise PermissionDenied('Tasdiqlanmagan Telegram manziliga hisobot yuborilmaydi. Telegramni CRM orqali ulang.')
    else:
        raise PermissionDenied('Qabul qiluvchi turi noma’lum.')
    if delivery.report_job_id:
        if delivery.report_job.status != 'ready':
            raise ValidationError('Hisobot hali tayyor emas.')
        validate_job_access(delivery.report_job, owner)
    # Never send a stale debt or callback notification after the work is done.
    if delivery.student_id and not delivery.report_job_id and not delivery.recipient.startswith(('student:', 'guardian:')):
        if delivery.student.get_debt_amount() <= 0:
            raise PermissionDenied('Qarz yopilgan.')
    if delivery.lead_id and not delivery.recipient.startswith('lead:'):
        if delivery.lead.archived_at or delivery.key.startswith('new-lead:') and delivery.lead.status != 'new':
            raise PermissionDenied('Murojaat holati o‘zgargan.')
        if delivery.key.startswith('callback:') and delivery.lead.status != 'callback':
            raise PermissionDenied('Qayta aloqa bajarilgan.')
        if delivery.key.startswith('callback:') and f'callback:{delivery.lead.pk}:{delivery.lead.follow_up_at.isoformat()}:' not in delivery.key:
            raise PermissionDenied('Qayta aloqa vaqti o‘zgargan.')


def telegram_request(delivery):
    """Return provider JSON; do not log token, message text or personal data."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return {'ok': False, 'error_code': 503, 'description': 'Bot sozlanmagan'}
    if delivery.report_job_id:
        path = private_path(delivery.report_job.file_name)
        boundary = 'crm-' + uuid4().hex
        fields = {'chat_id': str(delivery.chat_id), 'caption': delivery.text[:1000]}
        parts = []
        for key, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
        parts.extend([path.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()])
        method, data, content_type = 'sendDocument', b''.join(parts), f'multipart/form-data; boundary={boundary}'
    else:
        method, data, content_type = 'sendMessage', json.dumps({'chat_id': delivery.chat_id, 'text': delivery.text[:4000]}).encode(), 'application/json'
    request = Request(f'https://api.telegram.org/bot{token}/{method}', data=data, headers={'Content-Type': content_type})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            return json.loads(exc.read())
        except (ValueError, OSError):
            return {'ok': False, 'error_code': exc.code}
    except (OSError, ValueError):
        return {'ok': False, 'error_code': 503}


def process_deliveries(limit=20):
    now = timezone.now()
    # Recover a worker that stopped before acknowledging its lease.
    TelegramDelivery.objects.filter(status='running', started_at__lt=now - timedelta(minutes=10)).update(status='retry', next_attempt_at=now)
    candidates = TelegramDelivery.objects.filter(status__in=['pending', 'retry'], next_attempt_at__lte=now).order_by('created_at')
    count = 0
    for pk in candidates.values_list('pk', flat=True)[:limit]:
        claimed = TelegramDelivery.objects.filter(pk=pk, status__in=['pending', 'retry']).update(status='running', started_at=now)
        if not claimed:
            continue
        delivery = TelegramDelivery.objects.select_related('owner', 'student', 'lead', 'report_job').get(pk=pk)
        try:
            validate_delivery(delivery)
        except PermissionDenied as exc:
            delivery.status, delivery.error = 'cancelled', str(exc)[:200]
        except ValidationError:
            if delivery.report_job_id and delivery.report_job.status == 'failed':
                delivery.status, delivery.error = 'failed', 'Hisobot yaratilmadi.'
            else:
                delivery.status, delivery.next_attempt_at = 'retry', now + timedelta(seconds=15)
        else:
            result = telegram_request(delivery)
            delivery.attempts += 1
            if result.get('ok'):
                delivery.status, delivery.sent_at = 'sent', timezone.now()
                delivery.provider_message_id = result.get('result', {}).get('message_id')
                delivery.error = ''
            else:
                code = result.get('error_code', 503)
                delivery.status = 'failed' if code in (400, 401, 403) or delivery.attempts >= 8 else 'retry'
                pause = result.get('parameters', {}).get('retry_after', min(3600, 30 * 2 ** min(delivery.attempts, 7)))
                delivery.next_attempt_at = now + timedelta(seconds=max(1, int(pause)))
                delivery.error = f'Telegram xatosi: {code}'
        delivery.save(update_fields=['status', 'error', 'attempts', 'next_attempt_at', 'sent_at', 'provider_message_id'])
        count += 1
    return count
