from itertools import islice
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import ReportJob, Student, TelegramDelivery
from .permissions import has_capability, visible_students
from .reporting import Report, ReportFilterForm, REPORT_KINDS, FINANCIAL_KINDS
from .report_files import create_job, generate_job, private_path, validate_job_access


REPORT_GUIDES = {
    'students': ('O‘quvchilar', 'O‘quvchilar ro‘yxati', 'O‘quvchilar, ularning aloqa ma’lumotlari va ro‘yxatdan o‘tgan sanasini ko‘ring.', 'fa-user-graduate'),
    'attendance': ('O‘quv jarayoni', 'Davomat', 'Tanlangan davrda kim darsga kelgan, kechikkan yoki kelmaganini ko‘ring.', 'fa-calendar-check'),
    'grades': ('O‘quv jarayoni', 'Baholar', 'O‘quvchilarning baholari va darsdagi natijalarini tekshiring.', 'fa-star'),
    'groups': ('O‘quv jarayoni', 'Guruhlardagi bo‘sh joylar', 'Guruh sig‘imi, o‘quvchilar soni va bo‘sh o‘rinlarni solishtiring.', 'fa-layer-group'),
    'payments': ('Moliya', 'Qabul qilingan to‘lovlar', 'Qachon, kimdan va qancha to‘lov qabul qilinganini ko‘ring.', 'fa-money-bill-wave'),
    'accounts': ('Moliya', 'Qarzdorlik va to‘lov holati', 'Kim to‘lagan, kim qisman to‘lagan va kimning qarzi borligini aniqlang.', 'fa-file-invoice-dollar'),
    'advances': ('Moliya', 'Oldindan to‘lovlar', 'Keyingi oylar uchun oldindan to‘langan summalarni ko‘ring.', 'fa-coins'),
    'refunds': ('Moliya', 'Qaytarilgan pullar', 'O‘quvchilarga qaytarilgan summalar va qaytarish sabablarini tekshiring.', 'fa-arrow-rotate-left'),
    'tasks': ('Qabul', 'Qayta bog‘lanish vazifalari', 'Qayta qo‘ng‘iroq qilish yoki bog‘lanish kerak bo‘lgan murojaatlarni ko‘ring.', 'fa-phone-volume'),
    'leads': ('Qabul', 'Murojaatlar natijasi', 'Murojaatlar qayerdan kelganini va nechtasi to‘lov qilgan o‘quvchiga aylanganini ko‘ring.', 'fa-chart-line'),
}


def report_center_context(request, form, kind):
    kinds = allowed_kinds(request.user)
    options = []
    for category in ('O‘quvchilar', 'O‘quv jarayoni', 'Moliya', 'Qabul'):
        items = [{'key': key, 'label': REPORT_GUIDES[key][1], 'description': REPORT_GUIDES[key][2]}
                 for key in kinds if REPORT_GUIDES[key][0] == category]
        if items:
            options.append({'label': category, 'items': items})
    guide = REPORT_GUIDES.get(kind, ('', 'Hisobot', '', 'fa-file-lines'))
    presets = []
    for key, label in (('day', 'Bugun'), ('week', 'Shu hafta'), ('month', 'Shu oy'), ('year', 'Shu yil')):
        params = request.GET.copy()
        for field in ('month', 'date_from', 'date_to'):
            params.pop(field, None)
        params['period'] = key
        presets.append({'label': label, 'url': '?' + params.urlencode(), 'active': request.GET.get('period') == key})
    sections = []
    for title, codes, names in (
        ('O‘quvchi bo‘yicha', 'students attendance grades accounts advances refunds payments groups',
         ('student', 'q', 'status', 'student_source', 'registered_from', 'registered_to', 'month')),
        ('To‘lov va qarzdorlik bo‘yicha', 'accounts advances refunds payments', ('as_of', 'payment_state', 'service_month', 'payment_type')),
        ('Murojaat va reklama bo‘yicha', 'leads tasks', ('observation_end', 'lead_status', 'lead_source', 'assignee_scope', 'source', 'channel')),
    ):
        fields = [form[name] for name in names]
        active = any(field.value() not in (None, '') or field.errors for field in fields)
        sections.append({'title': title, 'kinds': codes, 'fields': fields,
                         'visible': kind in codes.split() or active, 'has_errors': any(field.errors for field in fields)})
    return {'report_options': options, 'report_heading': guide[1], 'report_description': guide[2], 'report_icon': guide[3],
            'period_presets': presets, 'primary_fields': [form[name] for name in ('period', 'date_from', 'date_to', 'branch', 'course', 'group', 'teacher')],
            'advanced_filter_sections': sections}


def allowed_kinds(user):
    result = dict(REPORT_KINDS)
    result.pop('student')
    if not has_capability(user, 'payments.view'):
        for key in FINANCIAL_KINDS:
            result.pop(key, None)
    if not has_capability(user, 'leads.manage'):
        for key in ('tasks', 'leads'):
            result.pop(key, None)
    for kind, cap in [('attendance', 'attendance.view'), ('grades', 'grades.view')]:
        if not has_capability(user, cap):
            result.pop(kind, None)
    return result


@login_required
def report_center(request):
    kind = request.GET.get('kind', 'students')
    form = ReportFilterForm(request.GET, user=request.user)
    context = {'filter_form': form, 'report_kinds': allowed_kinds(request.user), 'kind': kind}
    context.update(report_center_context(request, form, kind))
    if not form.is_valid():
        return render(request, 'core/report_center.html', context, status=400)
    try:
        report = Report(request.user, kind, request.GET)
        sheet = report.sheets()[0]
        rows = list(islice(sheet.rows, 51))
        headers = sheet.headers
        if kind == 'students' and 'UUID' in headers:
            # Internal identifiers remain in exports used for imports, but not the on-screen list.
            index = headers.index('UUID')
            headers = headers[:index] + headers[index + 1:]
            rows = [row[:index] + row[index + 1:] for row in rows]
        context.update(report=report, headers=headers, preview_rows=rows[:50], truncated=len(rows) > 50,
                       summary=report.summary(), cohort=report.cohort() if kind == 'leads' else None,
                       filters_query=request.GET.urlencode())
    except ValidationError as exc:
        form.add_error(None, exc)
        return render(request, 'core/report_center.html', context, status=400)
    return render(request, 'core/report_center.html', context)


@login_required
def student_report(request, pk):
    student = get_object_or_404(visible_students(request.user), pk=pk)
    params = request.GET.copy()
    if not any(params.get(key) for key in ('date_from', 'date_to', 'period', 'month')):
        today = timezone.localdate()
        params['date_from'] = today.replace(day=1).isoformat()
        params['date_to'] = today.isoformat()
    params['student'] = str(pk)
    params['kind'] = 'student'
    form = ReportFilterForm(params, user=request.user)
    context = {'student': student, 'filter_form': form,
               'link_code': request.session.pop(f'student_report_link_{student.pk}', None)}
    if not form.is_valid():
        return render(request, 'core/student_report.html', context, status=400)
    report = Report(request.user, 'student', params)
    previews = []
    for sheet in report.sheets():
        rows = list(islice(sheet.rows, 101))
        previews.append({'title': sheet.title, 'headers': sheet.headers, 'rows': rows[:100], 'truncated': len(rows) > 100})
    from .messaging import student_recipients
    context.update(report=report, previews=previews, filters_query=params.urlencode(),
                   academic_summary=report.academic_summary(),
                   recipients=student_recipients(student),
                   deliveries=TelegramDelivery.objects.filter(student=student, report_job__isnull=False).order_by('-created_at')[:20])
    return render(request, 'core/student_report.html', context)


@login_required
@require_POST
def report_export(request):
    kind, file_format = request.POST.get('kind', 'students'), request.POST.get('format', 'xlsx')
    try:
        job = create_job(request.user, kind, request.POST, file_format)
        report = Report(request.user, kind, job.filters)
        if report.estimate() <= 500:
            generate_job(job)
            return redirect('report_job_download', public_id=job.public_id)
    except ValidationError as exc:
        return HttpResponseBadRequest('; '.join(exc.messages))
    messages.success(request, 'Katta hisobot navbatga qo‘yildi. Fayllar sahifasidan yuklab olasiz.')
    return redirect('report_jobs')


@login_required
def report_jobs(request):
    jobs = list(ReportJob.objects.filter(owner=request.user).order_by('-created_at')[:100])
    for job in jobs:
        job.report_label = REPORT_GUIDES[job.kind][1] if job.kind in REPORT_GUIDES else REPORT_KINDS.get(job.kind, 'Hisobot')
        params = {key: value for key, value in job.filters.items() if not key.startswith('_')}
        destination = reverse('student_report', args=[params['student']]) if job.kind == 'student' and params.get('student') else reverse('report_center')
        job.report_url = destination + '?' + urlencode({**params, 'kind': job.kind})
    return render(request, 'core/report_jobs.html', {'jobs': jobs})


@login_required
def report_job_download(request, public_id):
    job = get_object_or_404(ReportJob, public_id=public_id, owner=request.user)
    validate_job_access(job, request.user)
    if job.status != 'ready':
        return HttpResponseBadRequest('Fayl hali tayyor emas.')
    path = private_path(job.file_name)
    if not path.is_file():
        return HttpResponseBadRequest('Fayl topilmadi. Hisobotni qayta yarating.')
    response = FileResponse(path.open('rb'), as_attachment=True, filename=f'{job.kind}-{job.public_id}.{job.file_format}')
    response['Cache-Control'] = 'no-store'
    return response
