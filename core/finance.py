"""Expense totals shared by the dashboard and financial reports."""
from decimal import Decimal

from django.db.models import F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce, TruncMonth

from .models import Expense, Payment, ReceptionistSalary, Refund, Salary


def with_cancellation_amount(queryset):
    """Refunds remain separate cash events; cancel only the unrefunded balance."""
    refunded = Refund.objects.filter(payment_id=OuterRef('pk')).order_by().values(
        'payment_id',
    ).annotate(total=Sum('amount')).values('total')
    return queryset.annotate(
        cancellation_amount=F('amount') - Coalesce(Subquery(refunded), Decimal(0)),
    )


def monthly_income_totals(start, end):
    """Overview income follows active payments, excluding cancelled entries entirely."""
    totals = {}
    for queryset, date_field, sign in (
        (Payment.objects.all(), 'paid_date', 1),
        (Refund.objects.filter(payment__voided_at__isnull=True), 'paid_at', -1),
    ):
        rows = queryset.filter(**{f'{date_field}__date__range': (start, end)}).annotate(
            period=TruncMonth(date_field),
        ).values('period').annotate(total=Sum('amount'))
        for row in rows:
            month = row['period'].date().replace(day=1)
            totals[month] = totals.get(month, Decimal(0)) + sign * row['total']
    return totals


def monthly_cash_totals(start, end):
    """Recognize collections, cancellations and refunds in their cash-event month."""
    totals = {}
    for queryset, date_field, amount_field, sign in (
        (Payment.all_objects.all(), 'paid_date', 'amount', 1),
        (with_cancellation_amount(Payment.all_objects.filter(voided_at__isnull=False)),
         'voided_at', 'cancellation_amount', -1),
        (Refund.objects.all(), 'paid_at', 'amount', -1),
    ):
        rows = queryset.filter(**{f'{date_field}__date__range': (start, end)}).annotate(
            period=TruncMonth(date_field),
        ).values('period').annotate(total=Sum(amount_field))
        for row in rows:
            month = row['period'].date().replace(day=1)
            totals[month] = totals.get(month, Decimal(0)) + sign * row['total']
    return totals


def monthly_expense_totals(start, end):
    """Deduct calculated payroll once, regardless of its payment status."""
    totals = {}
    for model, date_field, amount_field in (
        (Expense, 'date', 'amount'),
        (Salary, 'month', 'salary_amount'),
        (ReceptionistSalary, 'month', 'total_salary'),
    ):
        rows = model.objects.filter(**{f'{date_field}__range': (start, end)}).annotate(
            period=TruncMonth(date_field),
        ).values('period').annotate(total=Sum(amount_field))
        for row in rows:
            month = row['period'].replace(day=1)
            totals[month] = totals.get(month, Decimal(0)) + row['total']
    return totals
