import json
import re
import secrets
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Course,
    Campaign,
    Lead,
    LeadActivity,
    Student,
)
from .reminders import notify_lead_staff
from .utils import get_groups_for_date
from .telegram_linking import redeem_link_code, verified_target
from .permissions import has_capability, DEFAULT_CAPABILITIES


def require_api_key(view_func):
    """Xavfsiz API kalit tekshiruvi: X-CRM-API-Key yoki Authorization: Bearer."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        expected_key = getattr(settings, 'CRM_API_KEY', '')
        if not expected_key or expected_key == 'sarget-crm-api-secret-key-2026':
            return JsonResponse({'ok': False, 'error': 'Bot API o‘chirilgan: CRM_API_KEY sozlanmagan'}, status=503)

        api_key = (
            request.headers.get('X-CRM-API-Key')
            or request.headers.get('X-Api-Key')
        )
        if not api_key:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                api_key = auth_header.split(' ', 1)[1].strip()

        if not api_key or not secrets.compare_digest(api_key.encode(), expected_key.encode()):
            return JsonResponse({'ok': False, 'error': 'Ruxsat berilmadi: API kalit noto‘g‘ri yoki kiritilmagan.'}, status=401)

        return view_func(request, *args, **kwargs)
    return wrapper


def _normalize_phone(raw):
    if not raw or not isinstance(raw, str):
        return ''
    digits = re.sub(r'[^0-9]', '', raw)
    if len(digits) == 9:
        digits = '998' + digits
    return '+' + digits if digits else ''


def _parse_json(request):
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None


# ─── 1. Yangi ariza yaratish (Bot -> CRM Lead) ────────────────────────
@csrf_exempt
@require_POST
@require_api_key
def api_bot_create_lead(request):
    data = _parse_json(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Noto‘g‘ri JSON formati'}, status=400)

    for field in ('name', 'phone', 'course', 'campaign'):
        if field in data and not isinstance(data[field], str):
            return JsonResponse({'ok': False, 'error': f'{field} matn bo‘lishi kerak'}, status=400)
    for field in ('chat_id', 'user_id'):
        if data.get(field) is not None and (type(data[field]) is not int or not 0 < data[field] < 2**63):
            return JsonResponse({'ok': False, 'error': f'{field} noto‘g‘ri'}, status=400)

    name = str(data.get('name', '')).strip()[:200]
    raw_phone = str(data.get('phone', '')).strip()
    course = str(data.get('course', '')).strip()[:150]
    chat_id = data.get('chat_id')
    user_id = data.get('user_id')
    campaign = str(data.get('campaign', '')).strip()[:180]

    phone = _normalize_phone(raw_phone)
    if not name or not course:
        return JsonResponse({'ok': False, 'error': 'Ism va kurs majburiy maydonlar'}, status=400)
    if not re.fullmatch(r'\+[0-9]{9,15}', phone):
        return JsonResponse({'ok': False, 'error': 'Telefon raqam noto‘g‘ri kiritildi'}, status=400)


    # -- Idempotentlik: bir xil chat_id+phone+course 60 daqiqa ichida qayta yaratilmaydi --
    # Bot tarmoq xatosi tufayli ikki marta so'rov yuborganida takroriy ariza ochilmaydi.
    if isinstance(chat_id, int):
        from datetime import timedelta
        from django.utils import timezone as _tz
        cutoff = _tz.now() - timedelta(minutes=60)
        existing = Lead.all_objects.filter(
            telegram_chat_id=chat_id,
            phone=phone,
            course=course,
            created_at__gte=cutoff,
        ).first()
        if existing:
            return JsonResponse({
                'ok': True,
                'lead_id': existing.pk,
                'message': f"Arizangiz allaqachon qabul qilingan! Raqami: #{existing.pk}. Tez orada mutaxassis bog'lanadi.",
                'duplicate': True,
            }, status=200)
    with transaction.atomic():
        lead = Lead.objects.create(
            name=name,
            phone=phone,
            course=course,
            source='bot', channel='telegram',
            status='new',
            telegram_chat_id=chat_id if isinstance(chat_id, int) else None,
            telegram_user_id=user_id if isinstance(user_id, int) else None,
            campaign=campaign,
        )
        campaign_record = Campaign.objects.filter(start_parameter=campaign, is_active=True).first()
        if campaign_record:
            lead.campaign_record = campaign_record
            lead.advertising_source = campaign_record.advertising_source
            lead.save(update_fields=['campaign_record', 'advertising_source'])
        LeadActivity.objects.create(
            lead=lead,
            status='new',
            note='Telegram bot REST API orqali qabul qilindi'
        )

    try:
        notify_lead_staff(lead, 'Yangi Telegram arizasi')
    except Exception:
        pass

    return JsonResponse({
        'ok': True,
        'lead_id': lead.pk,
        'message': f"Arizangiz qabul qilindi! Raqami: #{lead.pk}. Tez orada mutaxassis bog'lanadi."
    }, status=201)


# ─── 2. Telegram Foydalanuvchini CRM bilan xavfsiz bog'lash ───────────
@csrf_exempt
@require_POST
@require_api_key
def api_bot_auth_user(request):
    data = _parse_json(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Noto‘g‘ri JSON'}, status=400)

    try:
        role, target = redeem_link_code(data.get('code'), data.get('chat_id'))
    except ValidationError as exc:
        return JsonResponse({'ok': False, 'error': exc.messages[0]}, status=400)
    return JsonResponse({'ok': True, 'role': role, 'user': {
        'id': target.pk, 'name': target.name,
    }})


# ─── 3. O'quvchi profili, dars jadvali, baholari va qarzdorligi ───────
@csrf_exempt
@require_GET
@require_api_key
def api_bot_student_info(request):
    role, student = verified_target(request.GET.get('chat_id'), role='student')
    if student is None:
        return JsonResponse({'ok': False, 'error': 'Tasdiqlangan ulanish topilmadi'}, status=403)

    group = student.group
    debt_amount = student.get_debt_amount()
    debt_months = student.get_debt_months()

    # Oxirgi 5 ta baho
    recent_grades = [
        {
            'date': g.date.strftime('%d.%m.%Y'),
            'type': g.get_grade_type_display(),
            'score': g.score,
            'note': g.note or '',
        }
        for g in student.grades.order_by('-date')[:5]
    ]

    # Davomat statistikasi
    att_qs = student.attendances.all()
    total_att = att_qs.count()
    present_att = att_qs.filter(status='present').count()

    return JsonResponse({
        'ok': True,
        'student': {
            'id': student.pk,
            'name': student.name,
            'phone': student.phone,
            'status': student.get_status_display(),
            'group': {
                'name': group.name,
                'room': group.room or '—',
                'days': group.get_days_display_human(),
                'start_time': group.start_time.strftime('%H:%M') if group.start_time else '',
                'end_time': group.end_time.strftime('%H:%M') if group.end_time else '',
                'monthly_fee': float(student.get_effective_fee()),
            } if group else None,
            'teacher': student.teacher.name if student.teacher else None,
            'finance': {
                'debt_amount': float(debt_amount),
                'debt_months': debt_months,
                'has_debt': debt_amount > 0,
            },
            'grades': recent_grades,
            'attendance': {
                'total': total_att,
                'present': present_att,
                'percentage': round(present_att / total_att * 100, 1) if total_att else 100.0,
            }
        }
    })


# ─── 4. Xodimlar va Boshliq uchun tezkor hisobot ───────────────────────
@csrf_exempt
@require_GET
@require_api_key
def api_bot_staff_summary(request):
    role, target = verified_target(request.GET.get('chat_id'))
    if role not in ('teacher', 'receptionist'):
        return JsonResponse({'ok': False, 'error': 'Faol xodim ulanishi kerak'}, status=403)
    today = timezone.localdate()
    def permitted(code):
        return has_capability(target.user, code) if target.user_id else code in DEFAULT_CAPABILITIES.get(role, set())
    active_students = Student.objects.filter(status='active')
    leads = Lead.objects.none()
    groups = get_groups_for_date(today)
    if role == 'teacher':
        active_students = active_students.filter(teacher=target)
        groups = [group for group in groups if group.teacher_id == target.pk]
    else:
        active_students = active_students.filter(receptionist=target)
        leads = Lead.objects.filter(Q(assigned_to=target.user) | Q(assigned_to__isnull=True)) if target.user_id else Lead.objects.none()
        group_ids = set(active_students.values_list('group_id', flat=True))
        groups = [group for group in groups if group.pk in group_ids]
    if not permitted('students.view'):
        active_students = active_students.none()
    if not permitted('groups.view'):
        groups = []
    if not permitted('leads.manage'):
        leads = Lead.objects.none()
    total_active_students = active_students.count()
    new_leads = leads.filter(status='new').count()
    due_callbacks = leads.filter(status='callback', follow_up_at__lte=timezone.now()).count()
    active_students = active_students.select_related('group').prefetch_related('payments', 'tariffs')
    debtors_count = 0
    total_debt_sum = Decimal('0')
    for s in active_students if role == 'receptionist' and permitted('payments.view') else []:
        amount = s.get_debt_amount()
        if amount > 0:
            debtors_count += 1
            total_debt_sum += amount

    # Bugungi darslar
    today_groups = [
        {
            'name': g.name,
            'room': g.room or '—',
            'time': f"{g.start_time:%H:%M} - {g.end_time:%H:%M}",
            'teacher': g.teacher.name if g.teacher else '—',
            'students_count': g.get_student_count(),
        }
        for g in groups
    ]

    return JsonResponse({
        'ok': True,
        'summary': {
            'role': role,
            'date': today.strftime('%d.%m.%Y'),
            'total_active_students': total_active_students,
            'new_leads': new_leads,
            'due_callbacks': due_callbacks,
            'debtors_count': debtors_count if role == 'receptionist' and permitted('payments.view') else None,
            'total_debt_sum': float(total_debt_sum) if role == 'receptionist' and permitted('payments.view') else None,
            'today_groups_count': len(today_groups),
            'today_groups': today_groups,
        }
    })


# ─── 5. O'quv markazdagi faol kurslar ro'yxati (Mijozlar uchun) ────────
@csrf_exempt
@require_GET
@require_api_key
def api_bot_courses_list(request):
    return JsonResponse({
        'ok': True,
        'courses': list(Course.objects.filter(is_active=True).values_list('name', flat=True)),
    })


# --- 6. Health Check (CRM server holati) ---
@require_GET
def api_health_check(request):
    """CRM server ishlayotganini tekshirish uchun public endpoint.
    Bot bu endpointni CRM mavjudligini tekshirish uchun ishlatishi mumkin.
    """
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse({
        'ok': db_ok,
        'service': 'sarget-crm',
        'db': 'ok' if db_ok else 'error',
    }, status=200 if db_ok else 503)
