"""Monthly tariff snapshots. Changes apply from the next calendar month."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone


def next_month(value):
    return date(value.year + (value.month == 12), value.month % 12 + 1, 1)


def record_tariff(student, *, initial=False):
    from .models import StudentTariff

    # Read persisted values: ModelForms and related-object caches may be stale.
    group = student.group if student.group_id else None
    enabled = bool(group and group.is_active and student.status == 'active')
    fee = (group.monthly_fee * (100 - Decimal(student.discount_percent)) / 100
           if enabled else Decimal('0'))
    fee = fee.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    previous = StudentTariff.objects.filter(student=student).order_by('-effective_month').first()
    due_day = student.payment_due_day or student.registration_date.day
    if previous and (previous.fee, previous.group_id_snapshot, previous.billing_enabled, previous.due_day) == (fee, student.group_id, enabled, due_day):
        return
    current = timezone.localdate().replace(day=1)
    if initial or previous is None:
        effective = student.registration_date.replace(day=1)
    elif enabled and not StudentTariff.objects.filter(student=student, billing_enabled=True).exists():
        # A pending admission starts learning now, not at the original lead date.
        effective = max(current, student.registration_date.replace(day=1))
    else:
        effective = max(next_month(current), student.registration_date.replace(day=1))
    StudentTariff.objects.update_or_create(
        student=student, effective_month=effective,
        defaults={'fee': fee, 'billing_enabled': enabled,
                  'due_day': due_day,
                  'group_id_snapshot': student.group_id,
                  'group_name': group.name if group else '', 'is_estimated': False},
    )


def fee_for_month(tariffs, month):
    applicable = [tariff for tariff in tariffs if tariff.effective_month <= month]
    if not applicable:
        return Decimal('0')
    tariff = max(applicable, key=lambda value: value.effective_month)
    return tariff.fee if tariff.billing_enabled else Decimal('0')


def stop_deleted_group_tariffs(sender, instance, **kwargs):
    # SET_NULL uses a bulk update, so schedule the stop before Django detaches students.
    for student in instance.student_set.all():
        student.group = None
        record_tariff(student)
