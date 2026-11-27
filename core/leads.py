import csv
import json
from datetime import datetime
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.db import transaction
from django.db.models import Count
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Lead, LeadActivity, Student, Notification, Branch
from .permissions import is_admin, is_receptionist, get_receptionist, has_capability, capability_required
from .admissions import filtered_leads
from .utils import paginate, report_query


def authorized(user):
    return has_capability(user, 'leads.manage')

@login_required
def lead_list(request):
    if not authorized(request.user): return HttpResponseForbidden('Ruxsat yo\'q')
    qs = filtered_leads(request.user, request.GET).prefetch_related(
        Prefetch(
            'activities',
            queryset=LeadActivity.objects.select_related('user').order_by('-created_at', '-pk')[:1],
            to_attr='recent_activities',
        )
    )
    status = request.GET.get('status', '')
    term = request.GET.get('q', '').strip()
    counts = dict(Lead.objects.values('status').annotate(total=Count('pk')).values_list('status', 'total'))
    results = [(label, counts.get(value, 0)) for value, label in Lead.STATUS]
    columns = []
    for value, label in Lead.STATUS:
        if status and status != value:
            continue
        page = Paginator(qs.filter(status=value), 20).get_page(request.GET.get(f'p_{value}', 1))
        def page_url(number):
            params = request.GET.copy()
            params.pop('page', None)
            params[f'p_{value}'] = number
            return '?' + params.urlencode() + f'#lead-column-{value}'
        columns.append({'key': value, 'label': label, 'page': page,
                        'previous_url': page_url(page.previous_page_number()) if page.has_previous() else '',
                        'next_url': page_url(page.next_page_number()) if page.has_next() else ''})
    return render(request, 'core/lead_list.html', {'leads':paginate(request, qs), 'lead_columns': columns,
        'board_total': qs.count(), 'is_archived': request.GET.get('archived') == '1' and has_capability(request.user, 'leads.archive'),
        'statuses':Lead.STATUS, 'current_status':status, 'current_scope':request.GET.get('scope', ''), 'current_due':request.GET.get('due', ''), 'term':term, 'total':Lead.objects.count(), 'pending':Lead.objects.filter(status='new').count(), 'due':Lead.objects.filter(status='callback',follow_up_at__lte=timezone.now()).count(), 'results': results, 'report_query': report_query(request, 'leads', {'source': 'lead_source', 'status': 'lead_status', 'scope': 'assignee_scope'})})


@login_required
@require_POST
@transaction.atomic
def lead_claim(request, pk):
    if not authorized(request.user):
        return HttpResponseForbidden("Arizani retsepshen o'ziga biriktirishi mumkin.")
    updated = Lead.objects.filter(pk=pk, assigned_to__isnull=True).update(assigned_to=request.user, updated_at=timezone.now())
    lead = get_object_or_404(Lead, pk=pk)
    if updated:
        LeadActivity.objects.create(lead=lead, user=request.user, status=lead.status, note="Arizani o'ziga biriktirdi")
        messages.success(request, "Ariza sizga biriktirildi.")
    else:
        if lead.assigned_to_id != request.user.pk:
            messages.error(request, "Bu ariza boshqa xodimga biriktirilgan.")
            return redirect('lead_list')
    return redirect('lead_edit', pk=pk)

@login_required
@transaction.atomic
def lead_edit(request, pk=None):
    if not authorized(request.user): return HttpResponseForbidden('Ruxsat yo\'q')
    lead = get_object_or_404(Lead.objects.select_for_update(), pk=pk) if pk else Lead(source='walk_in')
    if request.method == 'POST':
        activity_note = request.POST.get('activity_note', '').strip()
        lead.name = request.POST.get('name','').strip()[:200]
        lead.phone = request.POST.get('phone','').strip()[:30]
        lead.course = request.POST.get('course','').strip()[:150]
        lead.status = request.POST.get('status') if request.POST.get('status') in dict(Lead.STATUS) else 'new'
        source = request.POST.get('source')
        if source in dict(Lead.SOURCE): lead.source = source
        if 'branch' in request.POST:
            raw_branch = request.POST.get('branch', '')
            lead.branch = Branch.objects.filter(pk=int(raw_branch)).first() if raw_branch.isdigit() and len(raw_branch) <= 18 else None
        channel = request.POST.get('channel', lead.channel).strip()
        if channel in ('', 'telegram', 'phone', 'walk_in', 'website', 'other'):
            lead.channel = channel
        lead.advertising_source = request.POST.get('advertising_source', lead.advertising_source).strip()[:150]
        if is_admin(request.user):
            lead.is_test = request.POST.get('is_test') == 'on'
        lead.notes = request.POST.get('notes','')
        raw = request.POST.get('follow_up_at','')
        try: lead.follow_up_at = timezone.make_aware(datetime.fromisoformat(raw)) if raw else None
        except ValueError:
            messages.error(request, 'Eslatma sanasi noto\'g\'ri'); return render(request, 'core/lead_form.html', {'lead':lead,'statuses':Lead.STATUS,'sources':Lead.SOURCE,'activity_note':request.POST.get('activity_note','')})
        if not lead.name or not lead.course:
            messages.error(request, 'Ism va kurs majburiy'); return render(request, 'core/lead_form.html', {'lead':lead,'statuses':Lead.STATUS,'sources':Lead.SOURCE,'activity_note':request.POST.get('activity_note','')})
        if lead.status != 'new' and not activity_note:
            messages.error(request, 'Aloqa natijasini yozing.'); return render(request, 'core/lead_form.html', {'lead':lead,'statuses':Lead.STATUS,'sources':Lead.SOURCE,'activity_note':activity_note})
        if lead.status == 'callback' and not lead.follow_up_at:
            messages.error(request, 'Qayta aloqa sanasi va vaqtini belgilang.'); return render(request, 'core/lead_form.html', {'lead':lead,'statuses':Lead.STATUS,'sources':Lead.SOURCE,'activity_note':activity_note})
        if lead.status != 'callback': lead.follow_up_at = None
        if not lead.assigned_to_id and is_receptionist(request.user): lead.assigned_to = request.user
        lead.save()
        LeadActivity.objects.create(lead=lead, user=request.user, status=lead.status, note=request.POST.get('activity_note', ''))
        messages.success(request, 'Ariza saqlandi')
        return redirect('lead_list')
    return render(request, 'core/lead_form.html', {'lead':lead,'statuses':Lead.STATUS,'sources':Lead.SOURCE})

@login_required
@require_POST
@transaction.atomic
def lead_status_update(request, pk):
    if not authorized(request.user):
        return HttpResponseForbidden('Ruxsat yo\'q')
    lead = get_object_or_404(Lead.objects.select_for_update(), pk=pk)
    new_status = request.POST.get('status')
    note = request.POST.get('note', '').strip()
    if new_status not in dict(Lead.STATUS):
        messages.error(request, "Noto'g'ri ariza holati tanlandi.")
        return redirect(request.META.get('HTTP_REFERER', 'lead_list'))

    follow_up_at = None
    if new_status == 'callback':
        raw_follow_up = request.POST.get('follow_up_at', '').strip()
        try:
            follow_up_at = datetime.fromisoformat(raw_follow_up) if raw_follow_up else None
        except ValueError:
            follow_up_at = None
        if follow_up_at is None:
            messages.error(request, "Qayta aloqa holati uchun sana va vaqtni kiriting.")
            return redirect(request.META.get('HTTP_REFERER', 'lead_list'))
        if timezone.is_naive(follow_up_at):
            follow_up_at = timezone.make_aware(follow_up_at, timezone.get_current_timezone())

    old_status_display = lead.get_status_display()
    lead.status = new_status
    lead.follow_up_at = follow_up_at
    if not lead.assigned_to_id and is_receptionist(request.user):
        lead.assigned_to = request.user
    lead.save(update_fields=['status', 'follow_up_at', 'assigned_to', 'updated_at'])
    LeadActivity.objects.create(
        lead=lead,
        user=request.user,
        status=new_status,
        note=note or f"Holat o'zgartirildi: {old_status_display} → {lead.get_status_display()}"
    )
    messages.success(request, f"✓ {lead.name} holati \"{lead.get_status_display()}\"ga saqlandi.")
    return redirect(request.META.get('HTTP_REFERER', 'lead_list'))


@login_required
@require_POST
@transaction.atomic
def lead_enroll(request, pk):
    if not authorized(request.user): return HttpResponseForbidden('Ruxsat yo\'q')
    if not has_capability(request.user, 'students.create'):
        return HttpResponseForbidden("O'quvchi qabul qilish huquqi kerak.")
    lead = get_object_or_404(Lead.objects.select_for_update(), pk=pk)
    if not lead.student_id:
        receptionist = get_receptionist(lead.assigned_to) or get_receptionist(request.user)
        source = lead.source if lead.source in dict(Student.SOURCE_CHOICES) else 'other'
        student = Student.objects.create(name=lead.name,phone=lead.phone or '',status='pending', source=source,
            branch=lead.branch, receptionist=receptionist, teacher=getattr(request.user, 'teacher_profile', None),
            created_by=request.user, notes=f'Qabul #{lead.pk}: {lead.course}')
        lead.student = student
    lead.status = 'enrolled'; lead.follow_up_at = None; lead.save()
    LeadActivity.objects.create(lead=lead, user=request.user,status='enrolled',note='O\'quvchilar ro\'yxatiga o\'tkazildi')
    return redirect('student_edit' if is_admin(request.user) else 'student_detail', pk=lead.student.pk)

@login_required
@require_POST
@capability_required('leads.archive')
def lead_delete(request,pk):
    get_object_or_404(Lead,pk=pk).delete()
    return redirect('lead_list')


@login_required
@require_POST
@capability_required('leads.archive')
def lead_restore(request, pk):
    lead = get_object_or_404(Lead.all_objects, pk=pk)
    lead.archived_at = None
    lead.save(update_fields=['archived_at'])
    LeadActivity.objects.create(lead=lead, user=request.user, status=lead.status, note='Arxivdan tiklandi')
    return redirect('lead_list')

@login_required
def lead_export(request):
    if not authorized(request.user): return HttpResponseForbidden('Ruxsat yo\'q')
    r=HttpResponse(content_type='text/csv; charset=utf-8'); r['Content-Disposition']='attachment; filename="qabul_arizalari.csv"'
    r.write('\ufeff'); w=csv.writer(r); w.writerow(['ID','Ism','Telefon','Kurs','Manba','Holat','Keldi','Qayta aloqa','Izoh'])
    qs = filtered_leads(request.user, request.GET)
    def safe_cell(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value
    for lead in qs.iterator():
        w.writerow([safe_cell(value) for value in [lead.pk,lead.name,lead.phone,lead.course,lead.get_source_display(),lead.get_status_display(),timezone.localtime(lead.created_at).strftime('%Y-%m-%d %H:%M'),timezone.localtime(lead.follow_up_at).strftime('%Y-%m-%d %H:%M') if lead.follow_up_at else '',lead.notes]])
    return r

@csrf_exempt
@require_POST
def telegram_webhook(request):
    """Webhook token va Telegram secret header orqali tekshiriladi."""
    token = getattr(settings,'TELEGRAM_WEBHOOK_SECRET','')
    if not token or request.headers.get('X-Telegram-Bot-Api-Secret-Token') != token:
        return HttpResponseForbidden('Forbidden')
    try: data=json.loads(request.body)
    except (ValueError,UnicodeDecodeError): return JsonResponse({'ok':False}, status=400)
    if not isinstance(data, dict) or type(data.get('update_id')) is not int:
        return JsonResponse({'ok': False}, status=400)
    from .telegram_bot import process_update
    ok = process_update(data)
    return JsonResponse({'ok': ok}, status=200 if ok else 503)
