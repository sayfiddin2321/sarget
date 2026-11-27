from decimal import Decimal

from django.db import migrations, models
from django.utils import timezone


def backfill_salary_months(apps, schema_editor):
    Payment = apps.get_model('core', 'Payment')
    Salary = apps.get_model('core', 'Salary')
    RecSalary = apps.get_model('core', 'ReceptionistSalary')
    Commission = apps.get_model('core', 'ReceptionistCommission')
    alias = schema_editor.connection.alias
    paid_teachers = set(Salary.objects.using(alias).filter(is_paid=True).values_list('teacher_id', 'month'))
    paid_receptionists = set(RecSalary.objects.using(alias).filter(is_paid=True).values_list('receptionist_id', 'month'))
    for payment in Payment.objects.using(alias).select_related('student').iterator():
        paid_day = timezone.localdate(payment.paid_date) if timezone.is_aware(payment.paid_date) else payment.paid_date.date()
        earned = max(payment.month.replace(day=1), paid_day.replace(day=1))
        teacher_id = payment.teacher_at_payment_id or payment.student.teacher_id
        teacher_month = payment.month if (teacher_id, payment.month) in paid_teachers else earned
        commission = Commission.objects.using(alias).filter(payment_id=payment.pk).first()
        rec_month = commission.month if commission and (commission.receptionist_id, commission.month) in paid_receptionists else earned
        Payment.objects.using(alias).filter(pk=payment.pk).update(
            teacher_salary_month=teacher_month, receptionist_salary_month=rec_month,
        )
        if commission and commission.month != rec_month:
            Commission.objects.using(alias).filter(pk=commission.pk).update(month=rec_month)

    # Refresh existing unpaid calculations; paid payroll records remain unchanged.
    for salary in Salary.objects.using(alias).filter(is_paid=False).select_related('teacher').iterator():
        payments = Payment.objects.using(alias).filter(
            teacher_salary_month=salary.month, voided_at__isnull=True, is_historical_migration=False,
        ).filter(models.Q(teacher_at_payment_id=salary.teacher_id) | models.Q(
            teacher_at_payment__isnull=True, student__teacher_id=salary.teacher_id,
        ))
        income, amount = Decimal(0), Decimal(0)
        for payment in payments.iterator():
            percent = payment.teacher_percent_at_payment if payment.teacher_percent_at_payment is not None else salary.teacher.percent
            income += payment.amount
            amount += payment.amount * Decimal(percent) / 100
        Salary.objects.using(alias).filter(pk=salary.pk).update(total_income=income, salary_amount=amount)
    for salary in RecSalary.objects.using(alias).filter(is_paid=False).iterator():
        commission = Commission.objects.using(alias).filter(
            receptionist_id=salary.receptionist_id, month=salary.month, payment__voided_at__isnull=True,
        ).aggregate(total=models.Sum('commission_amount'))['total'] or Decimal(0)
        RecSalary.objects.using(alias).filter(pk=salary.pk).update(
            total_commission=commission, total_salary=salary.base_salary + commission,
        )


class Migration(migrations.Migration):
    dependencies = [('core', '0019_notification_student_link')]
    operations = [
        migrations.AddField('payment', 'teacher_salary_month', models.DateField(null=True, editable=False, db_index=True, verbose_name="O'qituvchi oyligi oyi")),
        migrations.AddField('payment', 'receptionist_salary_month', models.DateField(null=True, editable=False, db_index=True, verbose_name="Retsepshen oyligi oyi")),
        migrations.RunPython(backfill_salary_months, migrations.RunPython.noop),
        migrations.AlterField('payment', 'teacher_salary_month', models.DateField(editable=False, db_index=True, verbose_name="O'qituvchi oyligi oyi")),
        migrations.AlterField('payment', 'receptionist_salary_month', models.DateField(editable=False, db_index=True, verbose_name="Retsepshen oyligi oyi")),
    ]
