"""Telegram registration; conversation and update deduplication survive restarts."""
import json
import re
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import (
    Campaign, Course, GuardianBinding, Lead, LeadActivity, Student,
    TelegramBinding, TelegramSession, TelegramUpdate,
)
from .reminders import notify_lead_staff


def linked_account_reply(chat_id):
    binding = TelegramBinding.objects.filter(chat_id=chat_id).first()
    student_name = None
    staff_role = None
    if binding and binding.role == 'student':
        student_name = Student.objects.filter(
            pk=binding.target_id,
        ).exclude(status='inactive').values_list('name', flat=True).first()
    elif binding and binding.role in ('teacher', 'receptionist'):
        staff_role = binding.role
    guardian_names = list(
        Student.objects.filter(guardian_bindings__chat_id=chat_id)
        .exclude(status='inactive')
        .values_list('name', flat=True)[:5]
    )
    if not student_name and not staff_role and not guardian_names:
        return None

    if student_name and guardian_names:
        linked_to = f"{student_name} va {', '.join(guardian_names)}"
    elif student_name:
        linked_to = student_name
    elif guardian_names:
        linked_to = ', '.join(guardian_names)
    else:
        linked_to = 'CRM xodim akkaunti'
    return (
        f"Telegram hisobingiz CRMga ulangan: {linked_to}.\n"
        "Davomat, baho va to‘lov hisobotlarini CRM xodimi yuboradi."
    )


def telegram_api_result(method, payload=None, timeout=8):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return None
    try:
        request = Request(
            f'https://api.telegram.org/bot{token}/{method}',
            data=json.dumps(payload or {}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
        return result.get('result') if result.get('ok') else None
    except (OSError, ValueError):
        return None


def telegram_api(method, payload):
    return telegram_api_result(method, payload) is not None


def course_keyboard():
    names = list(Course.objects.filter(is_active=True).values_list('name', flat=True))
    if not names:
        return None
    keyboard = [names[index:index + 2] for index in range(0, len(names), 2)]
    return {'keyboard': keyboard, 'resize_keyboard': True, 'one_time_keyboard': True}


def registration_reply(message):
    chat_id = message['chat']['id']
    sender = message.get('from') or {}
    text = (message.get('text') or '').strip()
    command, _, argument = text.partition(' ')
    command = command.split('@', 1)[0]
    if command in ('/stop_reports', '/start_reports'):
        return {
            'chat_id': chat_id,
            'text': "Bu buyruq mavjud emas. Telegram hisobotlarini CRM xodimi boshqaradi.",
        }
    if command == '/help':
        linked_reply = linked_account_reply(chat_id)
        return {
            'chat_id': chat_id,
            'text': linked_reply or (
                "Assalomu alaykum! Kursga ariza qoldirish uchun /start yuboring. "
                "CRMga ulangan hisob bo‘lsa, CRM xodimidan bir martalik kod olib /link KOD yuboring."
            ),
        }
    if command == '/link' or (command == '/start' and argument.startswith('link_')):
        from .telegram_linking import redeem_link_code
        code = argument[5:] if command == '/start' else argument
        try:
            role, target = redeem_link_code(code, chat_id)
            answer = f"Telegram hisobingiz muvaffaqiyatli ulandi: {target.name}."
        except ValidationError as exc:
            answer = exc.messages[0]
        return {'chat_id': chat_id, 'text': answer}
    if command == '/start':
        linked_reply = linked_account_reply(chat_id)
        if linked_reply:
            return {'chat_id': chat_id, 'text': linked_reply}
    session, _ = TelegramSession.objects.select_for_update().get_or_create(chat_id=chat_id)
    reply = {'chat_id': chat_id, 'reply_markup': {'remove_keyboard': True}}
    if text.split(' ', 1)[0] == '/start':
        session.step = 'first_name'
        session.data = {'campaign': text.partition(' ')[2][:180]}
        reply['text'] = "Assalomu alaykum! Kursga yozilish uchun ismingizni kiriting. Bekor qilish: /cancel"
    elif text == '/cancel':
        session.step, session.data = 'done', {}
        reply['text'] = "Ariza bekor qilindi. Qayta boshlash: /start"
    elif session.step == 'done':
        lead = Lead.objects.filter(telegram_chat_id=chat_id, telegram_user_id=sender.get('id')).first()
        if lead and text and not text.startswith('/'):
            activity = LeadActivity.objects.create(lead=lead, status=lead.status, kind='incoming', note=text[:4000])
            notify_lead_staff(lead, 'Murojaat egasidan yangi xabar', event_key=f'lead-message:{activity.pk}')
            reply['text'] = 'Xabaringiz mas’ul xodimga yetkazish uchun saqlandi. Yangi ariza: /start'
        else:
            reply['text'] = "Yangi ariza uchun /start ni bosing."
    elif session.step in ('first_name', 'last_name'):
        if not text or text.startswith('/') or len(text) > 90 or not any(c.isalpha() for c in text):
            reply['text'] = "Ism yoki familiyani matn bilan kiriting (90 belgigacha)."
        else:
            session.data[session.step] = text
            session.step = 'last_name' if session.step == 'first_name' else 'course'
            if session.step == 'last_name':
                reply['text'] = "Familiyangizni kiriting."
            else:
                keyboard = course_keyboard()
                if keyboard:
                    reply['text'] = "Kerakli kursni quyidagi tugmalardan tanlang."
                    reply['reply_markup'] = keyboard
                else:
                    reply['text'] = "Hozircha faol kurs mavjud emas. Keyinroq qayta urinib ko‘ring."
                    reply['reply_markup'] = {'remove_keyboard': True}
    elif session.step == 'course':
        course = Course.objects.filter(is_active=True, name__iexact=text).first() if text else None
        if course:
            session.data['course'] = course.name
            session.step = 'phone'
            reply['text'] = "Telefon raqamingizni yuboring yoki +998901234567 shaklida kiriting."
            reply['reply_markup'] = {'keyboard': [[{'text': 'Telefon raqamni yuborish', 'request_contact': True}]], 'resize_keyboard': True, 'one_time_keyboard': True}
        else:
            keyboard = course_keyboard()
            if keyboard:
                reply['text'] = "Kursni pastdagi tugmalardan tanlang. Kurs nomini yozib yubormang."
                reply['reply_markup'] = keyboard
            else:
                reply['text'] = "Hozircha faol kurs mavjud emas. Keyinroq qayta urinib ko‘ring."
                reply['reply_markup'] = {'remove_keyboard': True}
    elif session.step == 'phone':
        contact = message.get('contact') or {}
        raw = contact.get('phone_number', '') if contact else text
        if not isinstance(raw, str):
            raw = ''
        phone = re.sub(r'[\s()\-]', '', raw)
        own_contact = not contact or contact.get('user_id') == sender.get('id')
        if not own_contact or not re.fullmatch(r'\+?[0-9]{9,15}', phone):
            reply['text'] = "O'zingizning telefon raqamingizni to'g'ri kiriting. Masalan: +998901234567"
        else:
            if len(phone) == 9:
                phone = '998' + phone
            lead = Lead.objects.create(
                name=f"{session.data['first_name']} {session.data['last_name']}",
                course=session.data['course'], phone='+' + phone.lstrip('+'),
                telegram_chat_id=chat_id, telegram_user_id=sender['id'],
                campaign=session.data.get('campaign', ''), source='bot', channel='telegram',
            )
            campaign = Campaign.objects.filter(start_parameter=session.data.get('campaign', ''), is_active=True).first()
            if campaign:
                lead.campaign_record = campaign
                lead.advertising_source = campaign.advertising_source
                lead.save(update_fields=['campaign_record', 'advertising_source'])
            LeadActivity.objects.create(lead=lead, status='new', note='Telegram bot orqali ariza keldi')
            notify_lead_staff(lead, 'Yangi Telegram arizasi')
            session.step, session.data = 'done', {}
            reply['text'] = f"Arizangiz qabul qilindi! Ariza raqami: #{lead.pk}. Tez orada siz bilan bog'lanamiz."
    session.save()
    return reply


def process_update(data):
    message = data.get('message')
    if not isinstance(message, dict):
        return True
    chat, sender = message.get('chat'), message.get('from')
    if not isinstance(chat, dict) or chat.get('type') != 'private':
        return True
    if not isinstance(chat.get('id'), int) or not isinstance(sender, dict) or not isinstance(sender.get('id'), int):
        return True
    if not isinstance(message.get('text', ''), str) or not isinstance(message.get('contact', {}), dict):
        return True
    with transaction.atomic():
        update, created = TelegramUpdate.objects.select_for_update().get_or_create(update_id=data['update_id'])
        if created:
            update.reply = registration_reply(message)
            update.save(update_fields=['reply'])
        if update.delivered:
            return True
    delivered = telegram_api('sendMessage', update.reply)
    if delivered:
        TelegramUpdate.objects.filter(pk=update.pk).update(delivered=True)
    return delivered
