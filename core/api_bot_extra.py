"""Alohida serverdagi bot uchun qo'shimcha REST endpointlar.

Bot CRM bazasiga to'g'ridan-to'g'ri tegmaydi: hamma narsa shu API orqali.
Autentifikatsiya: mavjud `require_api_key` (X-CRM-API-Key sarlavhasi).
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .api import require_api_key, _parse_json
from .models import GuardianBinding, Lead, LeadActivity, Student, TelegramBinding
from .reminders import notify_lead_staff


def _valid_chat_id(value):
    return type(value) is int and 0 < value < 2**63


# 1. Telegram hisob CRMga ulanganmi? (/start va /help javobi uchun)
@csrf_exempt
@require_GET
@require_api_key
def api_bot_account(request):
    try:
        chat_id = int(request.GET.get('chat_id', ''))
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'chat_id noto‘g‘ri'}, status=400)
    if not _valid_chat_id(chat_id):
        return JsonResponse({'ok': False, 'error': 'chat_id noto‘g‘ri'}, status=400)

    binding = TelegramBinding.objects.filter(chat_id=chat_id).first()
    student_name, staff_role = None, None
    if binding and binding.role == 'student':
        student_name = Student.objects.filter(pk=binding.target_id).exclude(
            status='inactive').values_list('name', flat=True).first()
    elif binding and binding.role in ('teacher', 'receptionist'):
        staff_role = binding.role
    guardian_names = list(
        Student.objects.filter(guardian_bindings__chat_id=chat_id)
        .exclude(status='inactive').values_list('name', flat=True)[:5]
    )
    return JsonResponse({
        'ok': True,
        'linked': bool(student_name or staff_role or guardian_names),
        'student_name': student_name,
        'staff_role': staff_role,
        'guardian_of': guardian_names,
    })


# 2. Ariza egasi (lead) bot orqali yozgan xabarni CRMga saqlash
@csrf_exempt
@require_POST
@require_api_key
def api_bot_lead_message(request):
    data = _parse_json(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Noto‘g‘ri JSON'}, status=400)
    chat_id, user_id, text = data.get('chat_id'), data.get('user_id'), data.get('text')
    if not _valid_chat_id(chat_id) or not _valid_chat_id(user_id) or not isinstance(text, str):
        return JsonResponse({'ok': False, 'error': 'chat_id, user_id yoki text noto‘g‘ri'}, status=400)
    text = text.strip()[:4000]
    if not text:
        return JsonResponse({'ok': False, 'error': 'Matn bo‘sh'}, status=400)

    lead = Lead.objects.filter(telegram_chat_id=chat_id, telegram_user_id=user_id).first()
    if not lead:
        return JsonResponse({'ok': True, 'saved': False})
    activity = LeadActivity.objects.create(lead=lead, status=lead.status, kind='incoming', note=text)
    try:
        notify_lead_staff(lead, 'Murojaat egasidan yangi xabar', event_key=f'lead-message:{activity.pk}')
    except Exception:
        pass
    return JsonResponse({'ok': True, 'saved': True, 'lead_id': lead.pk})
