"""Report balances as of a date; cash period and service period are separate."""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from django.utils import timezone
from .models import Payment


def months(first, last):
    cursor = first.replace(day=1)
    while cursor <= last.replace(day=1):
        yield cursor
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)


def student_accounts(student, as_of=None):
    as_of = as_of or timezone.localdate()
    tariffs = sorted(student.tariffs.all(), key=lambda row: row.effective_month)
    enrollments = list(student.enrollments.all())
    secondary = {row.pk: row for row in enrollments if not row.mirrors_student}
    paid = {}
    payments = getattr(student, 'all_report_payments', None)
    if payments is None:
        payments = Payment.all_objects.filter(student=student).prefetch_related('refunds')
    for payment in payments:
        if payment.voided_at and timezone.localtime(payment.voided_at).date() <= as_of:
            continue
        if timezone.localtime(payment.paid_date).date() > as_of:
            continue
        enrollment_id = payment.enrollment_id if payment.enrollment_id in secondary else None
        key = (enrollment_id, payment.month.replace(day=1))
        refunds = sum((r.amount for r in payment.refunds.all() if timezone.localtime(r.paid_at).date() <= as_of), Decimal(0))
        paid[key] = paid.get(key, Decimal(0)) + payment.amount - refunds
    rows = []
    primary_months = set(months(student.registration_date, as_of))
    primary_months.update(month for (enrollment_id, month) in paid if enrollment_id is None)
    for month in sorted(primary_months):
        tariff = next((row for row in reversed(tariffs) if row.effective_month <= month), None)
        fee = tariff.fee if tariff and tariff.billing_enabled else Decimal(0)
        due_day = tariff.due_day if tariff else (student.payment_due_day or student.registration_date.day)
        due = month.replace(day=min(due_day, monthrange(month.year, month.month)[1]))
        amount = paid.get((None, month), Decimal(0))
        if fee or amount:
            rows.append(account_row(student, None, month, due, fee, amount,
                                    tariff.group_name if tariff else '', as_of,
                                    tariff.group_id_snapshot if tariff else None))
    for enrollment in secondary.values():
        last = min(enrollment.ends_on or as_of, as_of)
        enrollment_months = set(months(enrollment.starts_on, last))
        enrollment_months.update(month for eid, month in paid if eid == enrollment.pk)
        for month in sorted(enrollment_months):
            # Cancelled/planned enrollments never generate tuition obligations.
            billable = (enrollment.status not in ('planned', 'cancelled')
                        and enrollment.starts_on.replace(day=1) <= month <= last.replace(day=1))
            fee = enrollment.monthly_fee if billable else Decimal(0)
            due = month.replace(day=min(enrollment.due_day, monthrange(month.year, month.month)[1]))
            amount = paid.get((enrollment.pk, month), Decimal(0))
            rows.append(account_row(student, enrollment, month, due, fee, amount, enrollment.group.name, as_of, enrollment.group_id))
    return rows


def account_row(student, enrollment, month, due, fee, paid, group, as_of, group_id):
    return {'student': student, 'enrollment': enrollment, 'month': month, 'due': due,
            'fee': fee, 'paid': paid, 'balance': max(Decimal(0), fee - paid), 'group_id': group_id,
            'advance': (paid if month > as_of.replace(day=1) else max(Decimal(0), paid - fee)), 'group': group,
            'state': 'paid' if paid >= fee else 'partial' if paid > 0 else 'unpaid'}
