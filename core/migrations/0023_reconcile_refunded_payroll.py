from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


def reconcile_refunded_payroll(apps, schema_editor):
    Payment = apps.get_model('core', 'Payment')
    Salary = apps.get_model('core', 'Salary')
    Commission = apps.get_model('core', 'ReceptionistCommission')
    RecSalary = apps.get_model('core', 'ReceptionistSalary')
    alias = schema_editor.connection.alias

    def net(payment):
        return max(Decimal(0), payment.amount - sum((r.amount for r in payment.refunds.all()), Decimal(0)))

    def share(amount, percent):
        return (amount * Decimal(percent) / 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

    paid_rec_periods = set(RecSalary.objects.using(alias).filter(is_paid=True).values_list('receptionist_id', 'month'))
    commissions = Commission.objects.using(alias).filter(
        payment__voided_at__isnull=True, payment__is_historical_migration=False,
    ).select_related('payment').prefetch_related('payment__refunds')
    for commission in commissions.iterator(chunk_size=200):
        if (commission.receptionist_id, commission.month) in paid_rec_periods:
            continue
        commission.payment_amount = net(commission.payment)
        commission.commission_amount = share(commission.payment_amount, commission.commission_percent)
        commission.save(using=alias, update_fields=['payment_amount', 'commission_amount'])

    for salary in Salary.objects.using(alias).filter(is_paid=False).select_related('teacher').iterator():
        payments = Payment.objects.using(alias).filter(
            teacher_salary_month=salary.month, voided_at__isnull=True, is_historical_migration=False,
        ).filter(models.Q(teacher_at_payment_id=salary.teacher_id) | models.Q(
            teacher_at_payment__isnull=True, student__teacher_id=salary.teacher_id,
        )).prefetch_related('refunds')
        income = amount = Decimal(0)
        for payment in payments.iterator(chunk_size=200):
            base = net(payment)
            percent = payment.teacher_percent_at_payment
            income += base
            amount += share(base, percent if percent is not None else salary.teacher.percent)
        salary.total_income, salary.salary_amount = income, amount
        salary.save(using=alias, update_fields=['total_income', 'salary_amount'])

    for salary in RecSalary.objects.using(alias).filter(is_paid=False).iterator():
        commission = Commission.objects.using(alias).filter(
            receptionist_id=salary.receptionist_id, month=salary.month, payment__voided_at__isnull=True,
        ).aggregate(total=models.Sum('commission_amount'))['total'] or Decimal(0)
        salary.total_commission = commission
        salary.total_salary = salary.base_salary + commission
        salary.save(using=alias, update_fields=['total_commission', 'total_salary'])


class Migration(migrations.Migration):
    dependencies = [('core', '0022_backfill_teacher_payroll')]
    operations = [migrations.RunPython(reconcile_refunded_payroll, migrations.RunPython.noop)]
