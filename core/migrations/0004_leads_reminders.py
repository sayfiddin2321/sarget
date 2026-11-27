from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('core','0003_group_custom_days_student_created_by_and_more'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='Lead', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name',models.CharField(max_length=200)),('phone',models.CharField(blank=True,max_length=30)),('course',models.CharField(max_length=150)),
            ('source',models.CharField(choices=[('bot','Telegram bot'),('target','Target reklama'),('walk_in',"O'zi kelgan"),('referral','Tavsiya'),('instagram','Instagram'),('other','Boshqa')],default='bot',max_length=20)),
            ('status',models.CharField(choices=[('new','Yangi'),('contacted',"Bog'landik"),('callback',"Qayta qo'ng'iroq"),('coming','Keladi'),('arrived','Keldi'),('enrolled',"O'qishga yozildi"),('not_interested','Qiziqmadi'),('invalid','Adashib tushgan')],db_index=True,default='new',max_length=20)),
            ('telegram_chat_id',models.BigIntegerField(blank=True,null=True)),('telegram_user_id',models.BigIntegerField(blank=True,null=True)),('campaign',models.CharField(blank=True,max_length=180)),('notes',models.TextField(blank=True)),('follow_up_at',models.DateTimeField(blank=True,db_index=True,null=True)),('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),('updated_at',models.DateTimeField(auto_now=True)),
            ('assigned_to',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='assigned_leads',to=settings.AUTH_USER_MODEL)),
            ('student',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='leads',to='core.student'))],options={'ordering':['-created_at']}),
        migrations.CreateModel(name='LeadActivity',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('status',models.CharField(blank=True,max_length=20)),('note',models.TextField(blank=True)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('lead',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='activities',to='core.lead')),
            ('user',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL))],options={'ordering':['-created_at']}),
        migrations.CreateModel(name='ReminderDispatch',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('key',models.CharField(max_length=160,unique=True)),('created_at',models.DateTimeField(auto_now_add=True))]),
    ]
