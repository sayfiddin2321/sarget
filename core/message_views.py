from datetime import date
from uuid import uuid4
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Lead, LeadActivity, ReportSubscription, TelegramDelivery
from .messaging import queue_student_report, queue_text, recipient_for_student
from .permissions import has_capability, visible_students
from .telegram_linking import issue_link_code


def _student_report_redirect(request, student_id):
    params = {
        key: request.POST[key]
        for key in ('date_from', 'date_to', 'period')
        if request.POST.get(key)
    }
    url = reverse('student_report', args=[student_id])
    return redirect(f'{url}?{urlencode(params)}' if params else url)


@login_required
@require_POST
def student_report_send(request, pk):
    student = get_object_or_404(visible_students(request.user), pk=pk)
    try:
        queue_student_report(request.user, student, request.POST.get('recipient', ''),
                             request.POST.dict(), request.POST.get('format', 'xlsx'))
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return _student_report_redirect(request, student.pk)
    messages.success(request, 'Hisobot navbatga qo‘yildi. Tayyorlash va yuborish holatini pastdagi jadvaldan ko‘rasiz.')
    return _student_report_redirect(request, student.pk)


@login_required
@require_POST
def student_report_link(request, pk):
    student = get_object_or_404(visible_students(request.user).exclude(status='inactive'), pk=pk)
    role = request.POST.get('role', '')
    if role not in ('student', 'guardian'):
        return HttpResponseBadRequest('Telegram ulash turi noto‘g‘ri.')
    try:
        code = issue_link_code(role, student.pk, request.user)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        request.session[f'student_report_link_{student.pk}'] = {'role': role, 'code': code}
        messages.success(request, 'Bir martalik ulash kodi yaratildi. Kod 10 daqiqa amal qiladi.')

    return _student_report_redirect(request, student.pk)


@login_required
@require_POST
@transaction.atomic
def student_report_subscribe(request, pk):
    student = get_object_or_404(visible_students(request.user), pk=pk)
    key = request.POST.get('recipient', '')
    try:
        recipient_for_student(student, key)
    except ValidationError as exc:
        return HttpResponseBadRequest('; '.join(exc.messages))
    file_format = request.POST.get('format', 'xlsx')
    if file_format not in ('xlsx', 'docx'):
        return HttpResponseBadRequest('Format noto‘g‘ri.')
    today = timezone.localdate()
    following = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    subscription, _ = ReportSubscription.objects.update_or_create(student=student, recipient=key, defaults={
        'owner': request.user, 'enabled': request.POST.get('enabled') == '1',
        'file_format': file_format, 'next_run_on': following,
    })
    messages.success(request, 'Oylik avtomatik hisobot sozlamasi saqlandi.')
    return redirect('student_report', pk=pk)


@login_required
@require_POST
@transaction.atomic
def student_telegram_message(request, pk):
    if not has_capability(request.user, 'messages.send'):
        raise PermissionDenied()
    student = get_object_or_404(visible_students(request.user).exclude(status='inactive'), pk=pk)
    recipient_key = request.POST.get('recipient', '')
    text = request.POST.get('text', '').strip()
    if not text or len(text) > 4000:
        messages.error(request, 'Xabar matni 1–4000 belgi bo‘lishi kerak.')
        return redirect('student_detail', pk=student.pk)
    try:
        recipient = recipient_for_student(student, recipient_key)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('student_detail', pk=student.pk)

    queue_text(
        key=f'student-message:{uuid4()}',
        chat_id=recipient['chat_id'],
        text=text,
        owner=request.user,
        student=student,
        recipient=recipient_key,
    )
    messages.success(request, 'Xabar Telegramga yuborish navbatiga qo‘yildi.')
    return redirect('student_detail', pk=student.pk)


@login_required
@transaction.atomic
def lead_message(request, pk):
    if not has_capability(request.user, 'leads.manage'):
        raise PermissionDenied()
    lead = get_object_or_404(Lead, pk=pk, archived_at__isnull=True)
    if not lead.telegram_chat_id or lead.telegram_chat_id != lead.telegram_user_id:
        return HttpResponseBadRequest('Bu murojaat uchun tasdiqlangan Telegram chat yo‘q. Telefon orqali bog‘laning.')
    error = ''
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if not text or len(text) > 4000:
            error = 'Xabar 1–4000 belgi bo‘lsin.'
        else:
            queue_text(key=f'lead-reply:{uuid4()}', chat_id=lead.telegram_chat_id, text=text,
                       owner=request.user, lead=lead, recipient=f'lead:{lead.pk}')
            LeadActivity.objects.create(lead=lead, user=request.user, status=lead.status, kind='outgoing', note='Telegram xabari navbatga qo‘yildi: ' + text)
            messages.success(request, 'Xabar yuborish navbatiga qo‘yildi.')
            return redirect('lead_message', pk=pk)
    return render(request, 'core/lead_message.html', {'lead': lead, 'error': error,
                  'incoming': lead.activities.filter(kind='incoming').order_by('-created_at')[:50],
                  'deliveries': TelegramDelivery.objects.filter(lead=lead, recipient=f'lead:{lead.pk}').order_by('-created_at')[:50]})
