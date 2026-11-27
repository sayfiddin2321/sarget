from django import forms
from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import FinancialAudit, OperationalRun, Student, Teacher, Receptionist, TelegramBinding, GuardianBinding, ReportJob, TelegramDelivery
from .permissions import capability_required, admin_required, is_admin, get_teacher, get_receptionist, visible_students, has_capability
from .telegram_linking import issue_link_code
from .utils import paginate


@login_required
@capability_required('finance.history')
def financial_history(request):
    events = FinancialAudit.objects.select_related('actor')
    entity = request.GET.get('entity', '')
    if entity:
        events = events.filter(entity=entity)
    object_id = request.GET.get('object_id', '')
    if object_id.isascii() and object_id.isdigit() and len(object_id) <= 18:
        events = events.filter(object_id=int(object_id))
    return render(request, 'core/financial_history.html', {
        'events': paginate(request, events), 'selected_entity': entity,
    })


@login_required
@capability_required('system.view')
def system_status(request):
    reminder = OperationalRun.objects.filter(job='reminders').first()
    backup = OperationalRun.objects.filter(job='backup').first()
    worker = OperationalRun.objects.filter(job='report_worker').first()
    return render(request, 'core/system_status.html', {
        'reminder': reminder, 'backup': backup,
        'worker_stale': not worker or (timezone.now() - worker.started_at).total_seconds() > 180,
        'pending_reports': ReportJob.objects.filter(status__in=['pending', 'running']).count(),
        'pending_messages': TelegramDelivery.objects.filter(status__in=['pending', 'running', 'retry']).count(),
        'failed_messages': TelegramDelivery.objects.filter(status='failed').count(),
        'reminder_stale': not reminder or (timezone.now() - reminder.started_at).total_seconds() > 180,
        'backup_stale': not backup or (timezone.now() - backup.started_at).total_seconds() > 86400,
        'reminder_failed': reminder and reminder.status in ('failed', 'degraded'),
        'backup_failed': backup and backup.status == 'failed',
        'runs': OperationalRun.objects.all()[:30],
    })


class LinkForm(forms.Form):
    target = forms.ChoiceField(label='Telegramga ulanadigan hisob', widget=forms.Select(attrs={'class': 'form-select select2'}))


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def telegram_link(request):
    choices = []
    if is_admin(request.user):
        students = Student.objects.exclude(status='inactive')
        teachers = Teacher.objects.filter(is_active=True)
        receptionists = Receptionist.objects.filter(is_active=True)
    else:
        # Teachers can link their own account; reception can also assist their students.
        students = visible_students(request.user).exclude(status='inactive') if has_capability(request.user, 'messages.send') else Student.objects.none()
        teacher = get_teacher(request.user)
        rec = get_receptionist(request.user)
        teachers = Teacher.objects.filter(pk=teacher.pk) if teacher else Teacher.objects.none()
        receptionists = Receptionist.objects.filter(pk=rec.pk) if rec else Receptionist.objects.none()
    for role, label, queryset in [('student', "O'quvchi", students), ('teacher', "O'qituvchi", teachers), ('receptionist', 'Retsepshen', receptionists)]:
        choices.extend((f'{role}:{obj.pk}', f'{label}: {obj.name} (#{obj.pk})') for obj in queryset)
    choices.extend((f'guardian:{obj.pk}', f'Ota-ona/vasiy: {obj.name} (#{obj.pk})') for obj in students)
    form = LinkForm(request.POST or None)
    form.fields['target'].choices = choices
    code = None
    if request.method == 'POST' and form.is_valid():
        role, target_id = form.cleaned_data['target'].split(':')
        if request.POST.get('action') == 'disconnect':
            from .telegram_linking import TARGETS
            TelegramBinding.objects.filter(role=role, target_id=int(target_id)).delete()
            if role == 'guardian':
                GuardianBinding.objects.filter(student_id=int(target_id)).delete()
            else:
                TARGETS[role].objects.filter(pk=int(target_id)).update(telegram_chat_id=None)
            from .models import TelegramLinkToken
            TelegramLinkToken.objects.filter(role=role, target_id=int(target_id), used_at__isnull=True).update(used_at=timezone.now())
            messages.success(request, 'Telegram ulanishi uzildi; eski kodlar bekor qilindi.')
            return redirect('telegram_link')
        try:
            code = issue_link_code(role, int(target_id), request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
    response = render(request, 'core/telegram_link.html', {'form': form, 'code': code})
    response['Cache-Control'] = 'no-store'
    # Native POST forms need a real Origin (and an HTTPS same-site Referer).
    # Keep referrers on our own site while hiding them from external origins.
    response['Referrer-Policy'] = 'same-origin'
    return response
