from decimal import Decimal

from django.db import migrations


def backfill_teacher_payroll(apps, schema_editor):
    Payment = apps.get_model('core', 'Payment')
    Salary = apps.get_model('core', 'Salary')
    alias = schema_editor.connection.alias
    totals = {}
    payments = Payment.objects.using(alias).filter(
        voided_at__isnull=True, is_historical_migration=False,
    ).select_related('teacher_at_payment', 'student__teacher')
    for payment in payments.iterator():
        teacher = payment.teacher_at_payment or payment.student.teacher
        if teacher is None:
            continue
        key = (teacher.pk, payment.teacher_salary_month)
        row = totals.setdefault(key, {'income': Decimal(0), 'salary': Decimal(0), 'percent': teacher.percent})
        percent = payment.teacher_percent_at_payment
        if percent is None:
            percent = teacher.percent
        row['income'] += payment.amount
        row['salary'] += payment.amount * Decimal(percent) / 100
    for (teacher_id, month), totals_row in totals.items():
        salary, _ = Salary.objects.using(alias).get_or_create(
            teacher_id=teacher_id, month=month, defaults={'percent': totals_row['percent']},
        )
        if not salary.is_paid:
            salary.total_income = totals_row['income']
            salary.salary_amount = totals_row['salary']
            salary.save(using=alias, update_fields=['total_income', 'salary_amount'])


class Migration(migrations.Migration):
    dependencies = [('core', '0021_student_deleted_at')]
    operations = [migrations.RunPython(backfill_teacher_payroll, migrations.RunPython.noop)]
