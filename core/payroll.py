"""Shared payroll totals for calculation and payment corrections."""
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q, Sum


def payment_net_amount(payment):
    refunded = sum((refund.amount for refund in payment.refunds.all()), Decimal(0))
    return max(Decimal(0), payment.amount - refunded)


def percentage_share(amount, percent):
    return (amount * Decimal(percent) / 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def teacher_totals(teacher, month):
    from .models import Payment
    payments = Payment.objects.filter(teacher_salary_month=month, is_historical_migration=False).filter(
        Q(teacher_at_payment=teacher) | Q(teacher_at_payment__isnull=True, student__teacher=teacher),
    ).prefetch_related('refunds')
    income, salary = Decimal(0), Decimal(0)
    for payment in payments.iterator(chunk_size=200):
        percent = payment.teacher_percent_at_payment if payment.teacher_percent_at_payment is not None else teacher.percent
        net = payment_net_amount(payment)
        income += net
        salary += percentage_share(net, percent)
    return income, salary


def receptionist_total(receptionist_id, month):
    from .models import ReceptionistCommission
    return ReceptionistCommission.objects.filter(
        receptionist_id=receptionist_id, month=month,
    ).aggregate(total=Sum('commission_amount'))['total'] or Decimal(0)


def refresh_unpaid_salaries(payment, previous=None):
    """Include every collection in payroll, creating an open teacher row if needed."""
    from .models import ReceptionistCommission, ReceptionistSalary, Salary, Teacher
    teacher_periods, rec_periods = set(), set()
    for item in (previous, payment):
        if item is None or item.is_historical_migration:
            continue
        teacher_periods.add((item.teacher_at_payment_id or item.student.teacher_id, item.teacher_salary_month))
        commission = ReceptionistCommission.all_objects.filter(payment_id=item.pk).first()
        if commission:
            rec_periods.add((commission.receptionist_id, item.receptionist_salary_month))
    for teacher_id, month in teacher_periods:
        if teacher_id is None:
            continue
        teacher = Teacher.objects.get(pk=teacher_id)
        salary, _ = Salary.objects.select_for_update().get_or_create(
            teacher=teacher, month=month, defaults={'percent': teacher.percent},
        )
        if salary.is_paid:
            continue
        salary.total_income, salary.salary_amount = teacher_totals(teacher, month)
        salary.save(update_fields=['total_income', 'salary_amount'])
    for rec_id, month in rec_periods:
        salary = ReceptionistSalary.objects.select_for_update().filter(
            receptionist_id=rec_id, month=month, is_paid=False,
        ).first()
        if salary:
            salary.total_commission = receptionist_total(rec_id, month)
            salary.total_salary = salary.base_salary + salary.total_commission
            salary.save(update_fields=['total_commission', 'total_salary'])
