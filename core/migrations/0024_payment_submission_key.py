from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0023_reconcile_refunded_payroll')]
    operations = [
        migrations.AddField(
            model_name='payment', name='submission_key',
            field=models.UUIDField(blank=True, editable=False, null=True, unique=True),
        ),
    ]
