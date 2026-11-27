from datetime import date
from django.core.paginator import Paginator


def sync_user_display_name(user, display_name):
    parts = display_name.strip().split(maxsplit=1)
    user.first_name = parts[0][:150] if parts else ''
    user.last_name = parts[1][:150] if len(parts) > 1 else ''
    user.save(update_fields=['first_name', 'last_name'])


def paginate(request, queryset, per_page=50):
    try:
        number = max(1, int(request.GET.get('page', '1')))
    except (TypeError, ValueError):
        number = 1
    return Paginator(queryset, per_page).get_page(number)


def report_query(request, kind, renames=None):
    params = request.GET.copy()
    params.pop('page', None)
    for old, new in (renames or {}).items():
        if old in params:
            params[new] = params.get(old)
            params.pop(old)
    params['kind'] = kind
    return params.urlencode()


def calendar_months(today, count):
    current = today.year * 12 + today.month - 1
    return [date(index // 12, index % 12 + 1, 1) for index in range(current - count + 1, current + 1)]


def parse_group_days(days_value):
    """'1-3-5' => ['1','3','5'] list qaytaradi."""
    if not days_value or days_value == 'custom':
        return []
    normalized = str(days_value).replace(',', '-')
    return [p.strip() for p in normalized.split('-') if p.strip().isdigit()]


def group_matches_date(group, target_date):
    """Guruh shu kunda dars bor-yo'qligini tekshiradi."""
    if not group or not getattr(group, 'days', ''):
        return False
    if group.days == 'custom':
        return False
    weekday = target_date.isoweekday()   # 1=Du, 2=Se, 3=Chor, 4=Pay, 5=Ju, 6=Sha, 7=Yak
    return str(weekday) in parse_group_days(group.days)


def get_groups_for_date(target_date, user=None):
    """O'qituvchi uchun faqat o'z guruhlari, admin uchun hammasi."""
    from .models import Group
    from .permissions import get_teacher

    teacher = get_teacher(user) if user else None
    qs = teacher.groups.filter(is_active=True) if teacher else Group.objects.filter(is_active=True)
    return [g for g in qs if group_matches_date(g, target_date)]


def find_group_conflicts(groups):
    """Faol guruhlar orasidagi xona va o'qituvchi to'qnashuvlarini topadi.

    Qaytaradi: {group_id: ["O'qituvchi to'qnashuvi: ...", ...]} — tasdiqlanmagan
    (pk=None) guruh natijadan chiqarib tashlanadi. Kunlar kodlari
    `parse_group_days` orqali solishtiriladi, shuning uchun '1-2-3-4-5' va
    '1-3-5' kabi kombinatsiyalar to'g'ri tekshiriladi. Solishtirish xona/
    o'qituvchi bo'yicha guruhlangan, ya'ni juftlar soni ikkinchi darajali.
    """
    prepared = []
    for group in groups:
        days = set(parse_group_days(group.days))
        if not days or not group.start_time or not group.end_time:
            continue
        prepared.append((
            group,
            days,
            group.start_time,
            group.end_time,
            (group.room or '').strip().lower(),
            group.teacher_id,
        ))

    # O'qituvchi/xona bo'yicha guruhlash: faqat bir xil kalitdagi juftlarni solishtiramiz.
    by_teacher = {}
    by_room = {}
    for index, (group, days, start, end, room, teacher_id) in enumerate(prepared):
        if teacher_id:
            by_teacher.setdefault(teacher_id, []).append(index)
        if room:
            by_room.setdefault(room, []).append(index)

    conflicts = {}

    def _add(left, right, kind):
        gl = prepared[left][0]
        gr = prepared[right][0]
        conflicts.setdefault(gl.id, []).append(f"{kind}: {gr.name}")
        conflicts.setdefault(gr.id, []).append(f"{kind}: {gl.name}")

    for bucket in by_teacher.values():
        for i, left in enumerate(bucket):
            g1, d1, s1, e1 = prepared[left][:4]
            for right in bucket[i + 1:]:
                g2, d2, s2, e2 = prepared[right][:4]
                if d1 & d2 and s1 < e2 and s2 < e1:
                    _add(left, right, "O'qituvchi to'qnashuvi")

    for bucket in by_room.values():
        for i, left in enumerate(bucket):
            g1, d1, s1, e1, room = prepared[left][:5]
            for right in bucket[i + 1:]:
                g2, d2, s2, e2, _room = prepared[right][:5]
                if d1 & d2 and s1 < e2 and s2 < e1:
                    _add(left, right, f"Xona to'qnashuvi ({g1.room.strip()})")

    # Bir juft guruhda ikkala to'qnashuv ham bo'lishi mumkin — takrorlarni olib tashlaymiz.
    return {group_id: list(dict.fromkeys(items))
            for group_id, items in conflicts.items() if group_id is not None}


def _conflicts_between(candidate, other):
    """Ikki guruh orasidagi to'qnashuv matnlari (saqlanmagan guruh uchun ham ishlaydi)."""
    days_a = set(parse_group_days(candidate.days))
    days_b = set(parse_group_days(other.days))
    if not days_a or not days_b or not (days_a & days_b):
        return []
    if not (candidate.start_time and candidate.end_time
            and other.start_time and other.end_time):
        return []
    if not (candidate.start_time < other.end_time and other.start_time < candidate.end_time):
        return []

    found = []
    if candidate.teacher_id and candidate.teacher_id == other.teacher_id:
        found.append(f"O'qituvchi to'qnashuvi: {other.name} "
                     f"({other.start_time:%H:%M}-{other.end_time:%H:%M}da band)")
    room_a = (candidate.room or '').strip().lower()
    room_b = (other.room or '').strip().lower()
    if room_a and room_a == room_b:
        found.append(f"Xona to'qnashuvi ({other.room.strip()}): {other.name} "
                     f"({other.start_time:%H:%M}-{other.end_time:%H:%M}da band)")
    return found


def group_conflict_messages(candidate, others):
    """Tahrirlanayotgan yangi guruhni mavjud faol guruhlar bilan solishtiradi."""
    messages = []
    for other in others:
        messages.extend(_conflicts_between(candidate, other))
    return list(dict.fromkeys(messages))


def uzbek_amount_in_words(amount):
    """Raqamli summani o'zbek tilida so'z bilan ifodalaydi.
    Masalan: 500000 -> 'Besh yuz ming so\'m'
    """
    from decimal import Decimal
    try:
        val = int(Decimal(str(amount)))
    except Exception:
        return ""
    if val <= 0:
        return "Nol so'm"

    ones = ["", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"]
    tens = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"]

    def _convert_hundreds(n):
        res = []
        h = n // 100
        t = (n % 100) // 10
        o = n % 10
        if h > 0:
            if h == 1:
                res.append("bir yuz")
            else:
                res.append(f"{ones[h]} yuz")
        if t > 0:
            res.append(tens[t])
        if o > 0:
            res.append(ones[o])
        return " ".join(res)

    chunks = [
        (1_000_000_000, "milliard"),
        (1_000_000, "million"),
        (1_000, "ming"),
        (1, ""),
    ]

    parts = []
    current = val
    for divisor, label in chunks:
        q = current // divisor
        if q > 0:
            words = _convert_hundreds(q)
            if words:
                if label:
                    parts.append(f"{words} {label}".strip())
                else:
                    parts.append(words.strip())
            current %= divisor

    result = " ".join(parts).strip()
    if not result:
        return "Nol so'm"
    return result[0].upper() + result[1:] + " so'm"
