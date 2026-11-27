from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0020_payment_salary_months')]
    operations = [migrations.AddField(
        model_name='student', name='deleted_at',
        field=models.DateTimeField(null=True, blank=True, editable=False, db_index=True),
    )]
