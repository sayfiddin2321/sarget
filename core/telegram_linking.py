"""One-use, short-lived codes issued by an authenticated CRM employee."""
import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.utils import timezone

from .models import Student, Teacher, Receptionist, TelegramBinding, TelegramLinkToken, GuardianBinding

TARGETS = {'student': Student, 'guardian': Student, 'teacher': Teacher, 'receptionist': Receptionist}


def active_target(role, target_id):
    model = TARGETS.get(role)
    if not model:
        return None
    qs = model.objects.filter(pk=target_id)
    if role not in ('student', 'guardian'):
        qs = qs.filter(is_active=True).filter(Q(user__isnull=True) | Q(user__is_active=True))
    else:
        qs = qs.exclude(status='inactive')
    return qs.first()


@transaction.atomic
def issue_link_code(role, target_id, actor):
    if not active_target(role, target_id):
        raise ValidationError("Faol hisob topilmadi.")
    TelegramLinkToken.objects.filter(role=role, target_id=target_id, used_at__isnull=True).update(used_at=timezone.now())
    code = secrets.token_urlsafe(24)
    TelegramLinkToken.objects.create(
        role=role, target_id=target_id, created_by=actor,
        token_hash=hashlib.sha256(code.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return code


@transaction.atomic
def redeem_link_code(code, chat_id):
    if not isinstance(code, str) or not 20 <= len(code) <= 100 or type(chat_id) is not int or not 0 < chat_id < 2**63:
        raise ValidationError("Ulash kodi yoki shaxsiy chat raqami noto'g'ri.")
    now = timezone.now()
    digest = hashlib.sha256(code.encode()).hexdigest()
    # Conditional write also prevents two consumers on SQLite from using one code.
    claimed = TelegramLinkToken.objects.filter(token_hash=digest, used_at__isnull=True, expires_at__gt=now).update(used_at=now)
    if not claimed:
        # A network retry from the same chat must return the original success.
        token = TelegramLinkToken.objects.filter(token_hash=digest, used_at__isnull=False,
                                                 expires_at__gt=now).first()
        if token:
            target = active_target(token.role, token.target_id)
            if token.role == 'guardian':
                linked = GuardianBinding.objects.filter(student_id=token.target_id, chat_id=chat_id,
                                                         verified_at__gte=token.used_at).exists()
            else:
                linked = TelegramBinding.objects.filter(role=token.role, target_id=token.target_id,
                                                         chat_id=chat_id, verified_at__gte=token.used_at).exists()
            if target is not None and linked:
                return token.role, target
        raise ValidationError("Kod noto'g'ri, ishlatilgan yoki muddati tugagan. CRMdan yangi kod oling.")
    token = TelegramLinkToken.objects.get(token_hash=digest)
    target = active_target(token.role, token.target_id)
    if target is None:
        raise ValidationError("Hisob faol emas.")
    if token.role == 'guardian':
        GuardianBinding.objects.update_or_create(student=target, chat_id=chat_id,
                                                 defaults={'verified_at': now, 'reports_enabled': True})
        return token.role, target
    occupied = TelegramBinding.objects.filter(chat_id=chat_id).exclude(role=token.role, target_id=token.target_id).exists()
    if occupied:
        raise ValidationError("Bu Telegram hisobi boshqa profilga ulangan. Avval ulanishni uzing.")
    try:
        TelegramBinding.objects.update_or_create(
            role=token.role, target_id=token.target_id,
            defaults={'chat_id': chat_id, 'verified_at': now},
        )
    except IntegrityError as exc:
        raise ValidationError("Bu chat allaqachon ulangan. Yangi kod bilan qayta urinib ko'ring.") from exc
    type(target).objects.filter(pk=target.pk).update(telegram_chat_id=chat_id)
    return token.role, target


def verified_target(chat_id, role=None):
    try:
        chat_id = int(chat_id)
    except (ValueError, TypeError):
        return None, None
    if not 0 < chat_id < 2**63:
        return None, None
    binding = TelegramBinding.objects.filter(chat_id=chat_id)
    if role:
        binding = binding.filter(role=role)
    binding = binding.first()
    if not binding:
        return None, None
    target = active_target(binding.role, binding.target_id)
    return (binding.role, target) if target else (None, None)
