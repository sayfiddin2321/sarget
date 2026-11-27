from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date
from decimal import Decimal
from calendar import monthrange
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid


class Branch(models.Model):
    name = models.CharField(max_length=120, unique=True, verbose_name='Filial')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='teacher_profile')
    name = models.CharField(max_length=200, verbose_name="Ism")
    phone = models.CharField(max_length=20, verbose_name="Telefon")
    subject = models.CharField(max_length=100, verbose_name="Fan")
    percent = models.IntegerField(
        default=40,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Foiz"
    )
    photo = models.ImageField(upload_to='teachers/', null=True, blank=True, verbose_name="Rasm")
    is_active = models.BooleanField(default=True, verbose_name="Aktiv")
    telegram_chat_id = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="Telegram Chat ID")
    notes = models.TextField(blank=True, verbose_name="Izoh")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "O'qituvchi"
        verbose_name_plural = "O'qituvchilar"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.percent}%)"

    def get_student_count(self):
        return self.students.filter(status='active').count()

    def get_this_month_income(self):
        today = timezone.localdate()
        from .payroll import teacher_totals
        return teacher_totals(self, today.replace(day=1))[0]

    def get_this_month_salary(self):
        today = timezone.localdate()
        return Salary.objects.filter(
            teacher=self, month__year=today.year, month__month=today.month
        ).first()


class Receptionist(models.Model):
    """Qabul xodimi - o'quvchi yozib bergan uchun foiz oladi"""
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='receptionist_profile')
    name = models.CharField(max_length=200, verbose_name="Ism")
    phone = models.CharField(max_length=20, verbose_name="Telefon")
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=10,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Komissiya foizi"
    )
    is_active = models.BooleanField(default=True, verbose_name="Aktiv")
    telegram_chat_id = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="Telegram Chat ID")
    notes = models.TextField(blank=True, verbose_name="Izoh")
    photo = models.ImageField(upload_to='receptionists/', null=True, blank=True, verbose_name='Rasm')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Retsepshen"
        verbose_name_plural = "Retsepshenlar"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.commission_percent}%)"

    def get_this_month_commission(self):
        today = timezone.localdate()
        from django.db.models import Sum
        result = ReceptionistCommission.objects.filter(
            receptionist=self,
            month__year=today.year,
            month__month=today.month
        ).aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0')
        return result


class Course(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Kurs nomi")
    description = models.TextField(blank=True, verbose_name="Izoh")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Kurs"
        verbose_name_plural = "Kurslar"

    def __str__(self):
        return self.name


class Group(models.Model):
    DAYS_CHOICES = [
        ('1-3-5', 'Dushanba - Chorshanba - Juma'),
        ('2-4-6', 'Seshanba - Payshanba - Shanba'),
        ('1-2-3-4-5', 'Dushanbadan Jumagacha (har kuni)'),
        ('6', 'Faqat Shanba'),
        ('7', 'Faqat Yakshanba'),
        ('custom', "Boshqa (qo'lda kiritish)"),
    ]
    WEEKDAY_LABELS = {
        '1': 'Du', '2': 'Se', '3': 'Chor', '4': 'Pay', '5': 'Ju', '6': 'Sha', '7': 'Yak',
    }
    name = models.CharField(max_length=100, verbose_name="Guruh nomi")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, null=True, blank=True, related_name='groups', verbose_name='Kurs')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True, related_name='groups', verbose_name='Filial')
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, related_name='groups', verbose_name="O'qituvchi")
    room = models.CharField(max_length=50, blank=True, verbose_name="Xona")
    days = models.CharField(max_length=100, choices=DAYS_CHOICES, default='1-3-5', verbose_name="Dars kunlari")
    custom_days = models.CharField(max_length=100, blank=True, verbose_name="Boshqa kunlar (matn)")
    start_time = models.TimeField(verbose_name="Boshlanish vaqti")
    end_time = models.TimeField(verbose_name="Tugash vaqti")
    monthly_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Oylik to'lov")
    max_students = models.IntegerField(default=15, verbose_name="Maksimal o'quvchilar")
    is_active = models.BooleanField(default=True, verbose_name="Aktiv")
    description = models.TextField(blank=True, verbose_name="Izoh")
    created_at = models.DateTimeField(auto_now_add=True)

    def get_days_display_human(self):
        if self.days == 'custom':
            return self.custom_days or '—'
        codes = [c for c in self.days.split('-') if c]
        return ' / '.join(self.WEEKDAY_LABELS.get(c, c) for c in codes)

    class Meta:
        verbose_name = "Guruh"
        verbose_name_plural = "Guruhlar"
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_student_count(self):
        return self.enrollments.filter(status='active', starts_on__lte=timezone.localdate()).filter(models.Q(ends_on__isnull=True) | models.Q(ends_on__gte=timezone.localdate())).values('student_id').distinct().count()

    def is_full(self):
        return self.get_student_count() >= self.max_students

    @transaction.atomic
    def save(self, *args, **kwargs):
        old_fee = Group.objects.filter(pk=self.pk).values_list('monthly_fee', flat=True).first() if self.pk else None
        super().save(*args, **kwargs)
        if old_fee is not None and old_fee != self.monthly_fee:
            from .billing import record_tariff
            for student in self.student_set.select_related('group'):
                record_tariff(student)


class VisibleStudentManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Student(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    objects = VisibleStudentManager()
    all_objects = models.Manager()
    STATUS_CHOICES = [
        ('active', "O'qiyapti"),
        ('inactive', "Kelmay qo'ygan"),
        ('graduated', 'Bitirgan'),
        ('pending', 'Kutilmoqda'),
    ]
    SOURCE_CHOICES = [
        ('walk_in', 'O\'zi kelgan'),
        ('referral', 'Tavsiya'),
        ('social', 'Ijtimoiy tarmoq'),
        ('reception', 'Qabul'),
        ('other', 'Boshqa'),
        ('bot', 'Telegram bot'), ('target', 'Target reklama'), ('instagram', 'Instagram'),
    ]
    name = models.CharField(max_length=200, verbose_name="Ism")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Filial')
    payment_due_day = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)], verbose_name="To'lov kuni")
    phone = models.CharField(max_length=20, verbose_name="Telefon")
    parent_phone = models.CharField(max_length=20, blank=True, verbose_name="Ota-ona telefoni")
    photo = models.ImageField(upload_to='students/', null=True, blank=True, verbose_name="Rasm")
    birth_date = models.DateField(null=True, blank=True, verbose_name="Tug'ilgan sana")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, related_name='students', verbose_name="O'qituvchi")
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Guruh")
    receptionist = models.ForeignKey(Receptionist, on_delete=models.SET_NULL, null=True, blank=True, related_name='registered_students', verbose_name="Qabul qilgan")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_students', verbose_name="Kim qo'shdi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Holat")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='walk_in', verbose_name="Qayerdan kelgan")
    registration_date = models.DateField(default=timezone.localdate, verbose_name="Ro'yxat sanasi")
    notes = models.TextField(blank=True, verbose_name="Izoh")
    discount_percent = models.IntegerField(default=0, verbose_name="Chegirma (%)")
    telegram_chat_id = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="Telegram Chat ID")

    class Meta:
        verbose_name = "O'quvchi"
        verbose_name_plural = "O'quvchilar"
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def student_number(self):
        return f'STU-{self.pk:06d}'

    @transaction.atomic
    def save(self, *args, **kwargs):
        initial = self._state.adding
        super().save(*args, **kwargs)
        from .billing import record_tariff
        persisted = Student.objects.select_related('group').get(pk=self.pk)
        record_tariff(persisted, initial=initial)
        from .enrollments import sync_primary_enrollment
        sync_primary_enrollment(persisted)
        if persisted.status in ('inactive', 'graduated'):
            for enrollment in persisted.enrollments.filter(mirrors_student=False, status__in=['active', 'planned', 'frozen']):
                enrollment.status = 'completed' if persisted.status == 'graduated' else 'left'
                enrollment.ends_on = timezone.localdate()
                enrollment.save(update_fields=['status', 'ends_on'])
        if hasattr(self, '_prefetched_objects_cache'):
            self._prefetched_objects_cache.pop('tariffs', None)

    @property
    def avatar_url(self):
        try:
            return self.photo.url if self.photo else ''
        except Exception:
            return ''

    @property
    def avatar_initial(self):
        return (self.name[:1] if self.name else '?').upper()

    @property
    def search_label(self):
        parts = [self.name]
        if self.group and self.group.name:
            parts.append(self.group.name)
        if self.phone:
            parts.append(self.phone)
        if self.parent_phone:
            parts.append(self.parent_phone)
        return ' | '.join(parts)

    def get_debt_months(self):
        return len(self.get_debt_breakdown())

    @property
    def payment_status(self):
        from .accounts import student_accounts
        accounts = student_accounts(self)
        if any(row['balance'] > 0 for row in accounts):
            return 'unpaid'
        if any(row['paid'] > 0 for row in accounts):
            return 'paid'
        return 'unpaid'

    def get_debt_breakdown(self, today=None):
        from .accounts import student_accounts
        return [dict(row, amount=row['balance']) for row in student_accounts(self, today)
                if row['due'] <= (today or timezone.localdate()) and row['balance'] > 0]

    def get_debt_amount(self):
        return sum((item['amount'] for item in self.get_debt_breakdown()), Decimal('0'))

    def get_total_paid(self):
        from django.db.models import Sum
        return self.payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

    def get_effective_fee(self):
        from .billing import fee_for_month
        return fee_for_month(list(self.tariffs.all()), timezone.localdate().replace(day=1))


class StudentTariff(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='tariffs')
    effective_month = models.DateField()
    fee = models.DecimalField(max_digits=12, decimal_places=2)
    due_day = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(31)])
    billing_enabled = models.BooleanField(default=True)
    group_id_snapshot = models.BigIntegerField(null=True, blank=True)
    group_name = models.CharField(max_length=100, blank=True)
    is_estimated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['effective_month']
        constraints = [
            models.UniqueConstraint(fields=['student', 'effective_month'], name='unique_student_tariff_month'),
            models.CheckConstraint(condition=models.Q(fee__gte=0), name='tariff_fee_nonnegative'),
        ]


class AssignmentHistory(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='assignment_history', verbose_name="O'quvchi")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, verbose_name="O'qituvchi")
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, verbose_name="Guruh")
    assigned_date = models.DateField(verbose_name="Biriktirilgan sana")
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Kim o'zgartirdi")
    note = models.CharField(max_length=255, blank=True, verbose_name="Sabab")

    class Meta:
        ordering = ['-assigned_date']
        verbose_name = "Biriktirish tarixi"
        verbose_name_plural = "Biriktirish tarixi"

    def __str__(self):
        return f"{self.student.name} → {self.teacher.name if self.teacher else 'None'}"


class PaymentQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("To'lovni tarixsiz o'zgartirib bo'lmaydi; save() ishlating.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("To'lovni tarixsiz o'zgartirib bo'lmaydi; save() ishlating.")

    @transaction.atomic
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        if ignore_conflicts or update_conflicts:
            raise ValidationError("Moliyaviy yozuvlarda yashirin ziddiyatlarni o'tkazib yuborish mumkin emas.")
        objs = list(objs)
        for obj in objs:
            obj.save(force_insert=True, using=self.db)
        return objs

    def delete(self):
        raise ValidationError("To'lovni o'chirish mumkin emas; bekor qilish amalidan foydalaning.")


class ActivePaymentManager(models.Manager.from_queryset(PaymentQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(voided_at__isnull=True)


class Payment(models.Model):
    submission_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    PAYMENT_TYPES = [
        ('cash', 'Naqd'),
        ('card', 'Plastik'),
        ('bank', 'Bank'),
        ('transfer', "O'tkazma"),
    ]
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='payments', verbose_name="O'quvchi")
    enrollment = models.ForeignKey('Enrollment', on_delete=models.PROTECT, null=True, blank=True, related_name='payments', verbose_name='Kursga yozilish')
    group_at_payment = models.ForeignKey(Group, on_delete=models.PROTECT, null=True, blank=True, related_name='historical_payments', editable=False)
    branch_at_payment = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True, related_name='historical_payments', editable=False)
    course_at_payment = models.ForeignKey(Course, on_delete=models.PROTECT, null=True, blank=True, related_name='historical_payments', editable=False)
    teacher_at_payment = models.ForeignKey(Teacher, on_delete=models.PROTECT, null=True, blank=True, related_name='recorded_payments', editable=False)
    teacher_percent_at_payment = models.IntegerField(null=True, blank=True, editable=False)
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Summa")
    month = models.DateField(verbose_name="Oy")
    paid_date = models.DateTimeField(default=timezone.now, verbose_name="To'lov sanasi")
    teacher_salary_month = models.DateField(editable=False, db_index=True, verbose_name="O'qituvchi oyligi oyi")
    receptionist_salary_month = models.DateField(editable=False, db_index=True, verbose_name="Retsepshen oyligi oyi")
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPES, default='cash', verbose_name="To'lov turi")
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Qabul qildi")
    comment = models.TextField(blank=True, verbose_name="Izoh")
    is_partial = models.BooleanField(default=False, verbose_name="Qisman to'lov")
    voided_at = models.DateTimeField(null=True, blank=True, editable=False)
    void_reason = models.TextField(blank=True, editable=False)
    is_historical_migration = models.BooleanField(default=False, editable=False)
    objects = ActivePaymentManager()
    all_objects = models.Manager.from_queryset(PaymentQuerySet)()

    class Meta:
        base_manager_name = 'all_objects'
        ordering = ['-paid_date']
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"

    def __str__(self):
        return f"{self.student.name} – {self.month.strftime('%Y-%m')}: {self.amount:,.0f} so'm"

    @property
    def receipt_number(self):
        dt = timezone.localtime(self.paid_date) if self.paid_date else timezone.now()
        return f"CHK-{dt.strftime('%Y%m%d')}-{self.pk:05d}"

    @property
    def amount_in_words(self):
        from .utils import uzbek_amount_in_words
        return uzbek_amount_in_words(self.amount)

    @property
    def service_period_end(self):
        return self.month.replace(day=monthrange(self.month.year, self.month.month)[1])

    @property
    def earned_month(self):
        paid_day = timezone.localdate(self.paid_date) if timezone.is_aware(self.paid_date) else self.paid_date.date()
        return max(self.month.replace(day=1), paid_day.replace(day=1))

    def clean(self):
        super().clean()
        self.amount = self._meta.get_field('amount').clean(self.amount, self)
        if self.amount <= 0:
            raise ValidationError({'amount': "To'lov summasi musbat bo'lishi kerak."})

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.enrollment_id and self.enrollment.student_id != self.student_id:
            raise ValidationError("To'lov egasi va kursga yozilish mos emas.")
        if self.month:
            self.month = self.month.replace(day=1)
        self.amount = self._meta.get_field('amount').clean(self.amount, self)
        if self.amount <= 0:
            raise ValidationError("To'lov summasi musbat bo'lishi kerak.")
        financial_change = self._state.adding
        old = None
        if not self._state.adding:
            old = Payment.all_objects.select_for_update(of=('self',)).get(pk=self.pk)
            if old.voided_at:
                raise ValidationError("Bekor qilingan to'lovni o'zgartirib bo'lmaydi.")
            if old.student_id != self.student_id:
                raise ValidationError("To'lov egasini o'zgartirib bo'lmaydi. Bekor qilib, yangi to'lov kiriting.")
            payment_details_changed = any(getattr(old, field) != getattr(self, field) for field in (
                'amount', 'month', 'paid_date', 'enrollment_id',
                'teacher_at_payment_id', 'teacher_percent_at_payment',
            ))
            financial_change = payment_details_changed or old.voided_at != self.voided_at
            # Payroll month fields are maintained by the system, including legacy paid periods.
            self.teacher_salary_month = old.teacher_salary_month
            self.receptionist_salary_month = old.receptionist_salary_month
            if financial_change:
                if payment_details_changed and old.refunds.exists():
                    raise ValidationError('Qaytarimi bor to‘lovning summasi/oyi o‘zgarmaydi.')
                old.ensure_open_period()
        if financial_change:
            self.teacher_salary_month = self.earned_month
            self.receptionist_salary_month = self.earned_month
        if self.month and self.month.day != 1:
            self.month = self.month.replace(day=1)
        if (self._state.adding or old.enrollment_id != self.enrollment_id) and not self.is_historical_migration:
            group = self.enrollment.group if self.enrollment_id else self.student.group
            teacher = group.teacher if self.enrollment_id and group else self.student.teacher
            if teacher is None and group:
                teacher = group.teacher
            self.teacher_at_payment = teacher
            self.teacher_percent_at_payment = teacher.percent if teacher else None
            self.group_at_payment = group
            self.branch_at_payment = group.branch if group and group.branch_id else self.student.branch
            self.course_at_payment = group.course if group else None
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {
                    'teacher_at_payment', 'teacher_percent_at_payment', 'group_at_payment',
                    'branch_at_payment', 'course_at_payment',
                }
        if financial_change and not self.is_historical_migration:
            self.ensure_open_period()
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'teacher_salary_month', 'receptionist_salary_month'}
        super().save(*args, **kwargs)
        # Receptionist komissiyasini hisoblash
        if not self.voided_at and not self.is_historical_migration:
            self._update_receptionist_commission()
        if financial_change:
            from .payroll import refresh_unpaid_salaries
            refresh_unpaid_salaries(self, previous=old)

    @transaction.atomic
    def ensure_open_period(self):
        teacher_id = self.teacher_at_payment_id or self.student.teacher_id
        salary = Salary.objects.select_for_update().filter(teacher_id=teacher_id, month=self.teacher_salary_month).first()
        if salary and salary.is_paid:
            raise ValidationError("Bu hisob oyida o'qituvchi maoshi to'langan. O'zgartirish uchun avval oylikni to'lanmagan holatga qaytaring.")
        commission = ReceptionistCommission.all_objects.filter(payment_id=self.pk).first() if self.pk else None
        receptionist_id = commission.receptionist_id if commission else self.student.receptionist_id
        salary = ReceptionistSalary.objects.select_for_update().filter(receptionist_id=receptionist_id, month=self.receptionist_salary_month).first()
        if salary and salary.is_paid:
            raise ValidationError("Bu hisob oyida retsepshen maoshi to'langan. O'zgartirish uchun avval oylikni to'lanmagan holatga qaytaring.")

    @transaction.atomic
    def void(self, reason):
        if not reason or not reason.strip():
            raise ValidationError("Bekor qilish sababini kiriting.")
        self.voided_at = timezone.now()
        self.void_reason = reason.strip()
        self.save(update_fields=['voided_at', 'void_reason'])

    def delete(self, *args, **kwargs):
        raise ValidationError("To'lovni o'chirish mumkin emas; bekor qilish amalidan foydalaning.")

    def _update_receptionist_commission(self):
        from .payroll import payment_net_amount, percentage_share
        student = self.student
        net = payment_net_amount(self)
        existing = ReceptionistCommission.objects.filter(payment=self).first()
        if existing:
            existing.month = self.receptionist_salary_month
            existing.payment_amount = net
            existing.commission_amount = percentage_share(net, existing.commission_percent)
            existing.save(update_fields=['month', 'payment_amount', 'commission_amount'])
            return
        if student.receptionist:
            rec = student.receptionist
            commission = percentage_share(net, rec.commission_percent)
            ReceptionistCommission.objects.update_or_create(
                receptionist=rec,
                student=student,
                payment=self,
                defaults={
                    'month': self.receptionist_salary_month,
                    'payment_amount': net,
                    'commission_percent': rec.commission_percent,
                    'commission_amount': commission,
                }
            )


class AuditedFinancialModel(models.Model):
    class Meta:
        abstract = True

    @transaction.atomic
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        return super().delete(*args, **kwargs)


class ActiveCommissionManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(payment__voided_at__isnull=True)


class ReceptionistCommission(AuditedFinancialModel):
    """Har bir to'lovdan retsepshenga hisoblangan komissiya"""
    receptionist = models.ForeignKey(Receptionist, on_delete=models.CASCADE, related_name='commissions', verbose_name="Retsepshen")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name="O'quvchi")
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, verbose_name="To'lov")
    month = models.DateField(verbose_name="Oy")
    payment_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="To'lov summasi")
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Foiz")
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Komissiya summasi")
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ActiveCommissionManager()
    all_objects = models.Manager()

    class Meta:
        base_manager_name = 'all_objects'
        ordering = ['-month']
        verbose_name = "Retsepshen komissiyasi"
        verbose_name_plural = "Retsepshen komissiyalari"

    def __str__(self):
        return f"{self.receptionist.name} – {self.student.name}: {self.commission_amount:,.0f} so'm"


class ReceptionistSalary(AuditedFinancialModel):
    """Oylik hisoblangan retsepshen maoshi"""
    receptionist = models.ForeignKey(Receptionist, on_delete=models.CASCADE, related_name='salaries', verbose_name="Retsepshen")
    month = models.DateField(verbose_name="Oy")
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Asosiy maosh")
    total_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Jami komissiya")
    total_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Jami maosh")
    is_paid = models.BooleanField(default=False, verbose_name="To'langanmi")
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['receptionist', 'month']
        ordering = ['-month']
        verbose_name = "Retsepshen oyligi"
        verbose_name_plural = "Retsepshen oyliklar"

    def __str__(self):
        return f"{self.receptionist.name} – {self.month.strftime('%Y-%m')}: {self.total_salary:,.0f}"


class Salary(AuditedFinancialModel):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='salaries', verbose_name="O'qituvchi")
    month = models.DateField(verbose_name="Oy")
    total_income = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Jami tushum")
    percent = models.IntegerField(verbose_name="Foiz")
    salary_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Oylik summasi")
    is_paid = models.BooleanField(default=False, verbose_name="To'langanmi")
    calculated_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, verbose_name="Izoh")

    class Meta:
        unique_together = ['teacher', 'month']
        ordering = ['-month']
        verbose_name = "Oylik"
        verbose_name_plural = "Oyliklar"

    def __str__(self):
        return f"{self.teacher.name} – {self.month.strftime('%Y-%m')}: {self.salary_amount:,.0f}"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Keldi'),
        ('absent', 'Kelmadi'),
        ('late', 'Kechikdi'),
        ('excused', 'Sababli'),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances', verbose_name="O'quvchi")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name="Guruh")
    date = models.DateField(verbose_name="Sana")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='present', verbose_name="Holat")
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Belgilagan")
    marked_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=200, blank=True, verbose_name="Izoh")

    class Meta:
        unique_together = ['student', 'date', 'group']
        ordering = ['-date']
        verbose_name = "Davomat"
        verbose_name_plural = "Davomatlar"

    def __str__(self):
        return f"{self.student.name} – {self.date}: {self.get_status_display()}"


class Grade(models.Model):
    GRADE_TYPES = [
        ('classwork', 'Darsdagi faollik'),
        ('homework', 'Uy vazifasi'),
        ('exam', 'Imtihon / Test'),
        ('monthly', 'Oylik nazorat'),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='grades', verbose_name="O'quvchi")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='grades', verbose_name="Guruh")
    date = models.DateField(default=date.today, verbose_name="Sana")
    grade_type = models.CharField(max_length=20, choices=GRADE_TYPES, default='classwork', verbose_name="Baho turi")
    score = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        verbose_name="Baho / Ball"
    )
    note = models.CharField(max_length=255, blank=True, verbose_name="Izoh")
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Baholagan")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [models.UniqueConstraint(fields=['student', 'group', 'date', 'grade_type'], name='unique_student_grade_per_day_type')]
        verbose_name = "Baho"
        verbose_name_plural = "Baholar"

    def __str__(self):
        return f"{self.student.name} – {self.score} ({self.get_grade_type_display()})"


class Expense(AuditedFinancialModel):
    CATEGORY_CHOICES = [
        ('rent', 'Ijara'),
        ('salary', 'Maosh'),
        ('utility', 'Kommunal'),
        ('supplies', 'Jihozlar'),
        ('marketing', 'Reklama'),
        ('other', 'Boshqa'),
    ]
    title = models.CharField(max_length=200, verbose_name="Nomi")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name="Kategoriya")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Summa")
    date = models.DateField(verbose_name="Sana")
    description = models.TextField(blank=True, verbose_name="Izoh")
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Qo'shdi")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        self.amount = self._meta.get_field('amount').clean(self.amount, self)
        if self.amount <= 0:
            raise ValidationError({'amount': "Xarajat summasi musbat bo'lishi kerak."})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ['-date']
        verbose_name = "Xarajat"
        verbose_name_plural = "Xarajatlar"

    def __str__(self):
        return f"{self.title}: {self.amount:,.0f} so'm ({self.date})"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('debt', 'Qarz'),
        ('payment', "To'lov"),
        ('birthday', "Tug'ilgan kun"),
        ('info', 'Ma\'lumot'),
    ]
    title = models.CharField(max_length=200, verbose_name="Sarlavha")
    message = models.TextField(verbose_name="Xabar")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info', verbose_name="Tur")
    is_read = models.BooleanField(default=False, verbose_name="O'qildi")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', verbose_name="Qabul qiluvchi")
    lead = models.ForeignKey('Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Xabarnoma"
        verbose_name_plural = "Xabarnomalar"

    def __str__(self):
        return self.title

    @property
    def target_url(self):
        from django.urls import reverse
        if self.lead_id and not self.lead.archived_at:
            return reverse('lead_edit', args=[self.lead_id])
        if self.student_id:
            return reverse('student_detail', args=[self.student_id])
        return ''


class ActiveLeadManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)


class Lead(models.Model):
    """Qabul voronkasi: ariza hech qachon status almashganda yo'qolmaydi."""
    STATUS = [('new','Yangi'),('contacted','Bog\'landik'),('callback','Qayta qo\'ng\'iroq'),('coming','Keladi'),('arrived','Keldi'),('enrolled','O\'qishga yozildi'),('not_interested','Qiziqmadi'),('invalid','Adashib tushgan')]
    SOURCE = [('bot','Telegram bot'),('target','Target reklama'),('walk_in','O\'zi kelgan'),('referral','Tavsiya'),('instagram','Instagram'),('other','Boshqa')]
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    course = models.CharField(max_length=150)
    source = models.CharField(max_length=20, choices=SOURCE, default='bot')
    channel = models.CharField(max_length=30, blank=True, verbose_name='Murojaat kanali')
    advertising_source = models.CharField(max_length=150, blank=True, verbose_name='Reklama manbasi')
    campaign_record = models.ForeignKey('Campaign', on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True)
    is_test = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='new', db_index=True)
    telegram_chat_id = models.BigIntegerField(null=True, blank=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    campaign = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True, db_index=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_leads')
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = ActiveLeadManager()
    all_objects = models.Manager()
    class Meta:
        ordering = ['-created_at']
        base_manager_name = 'all_objects'
    def __str__(self):
        return f'{self.name} — {self.course}'

    def delete(self, *args, **kwargs):
        self.archived_at = timezone.now()
        self.save(update_fields=['archived_at'])

class LeadActivity(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    kind = models.CharField(max_length=20, default='note', choices=[('note', 'Izoh'), ('incoming', 'Telegramdan kelgan'), ('outgoing', 'Telegramga yuborilgan')])
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']

    def get_status_display(self):
        return dict(Lead.STATUS).get(self.status, self.status)

class ReminderDispatch(models.Model):
    """Bir kun ichida takroriy bot xabarlarini oldini oladi."""
    key = models.CharField(max_length=160, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TelegramSession(models.Model):
    chat_id = models.BigIntegerField(unique=True)
    step = models.CharField(max_length=20, default='first_name')
    data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class TelegramUpdate(models.Model):
    update_id = models.BigIntegerField(unique=True)
    reply = models.JSONField(default=dict)
    delivered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class TelegramLinkToken(models.Model):
    token_hash = models.CharField(max_length=64, unique=True)
    role = models.CharField(max_length=20)
    target_id = models.PositiveBigIntegerField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class TelegramBinding(models.Model):
    role = models.CharField(max_length=20)
    target_id = models.PositiveBigIntegerField()
    chat_id = models.BigIntegerField(unique=True)
    verified_at = models.DateTimeField(default=timezone.now)
    reports_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['role', 'target_id'], name='unique_telegram_target')]


class FinancialAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Moliyaviy tarix o'zgartirilmaydi.")

    def delete(self):
        raise ValidationError("Moliyaviy tarix o'chirilmaydi.")


class FinancialAudit(models.Model):
    entity = models.CharField(max_length=40, db_index=True)
    object_id = models.PositiveBigIntegerField(db_index=True)
    action = models.CharField(max_length=20)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    actor_name = models.CharField(max_length=150, blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    objects = FinancialAuditQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at', '-pk']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Moliyaviy tarix o'zgartirilmaydi.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Moliyaviy tarix o'chirilmaydi.")

    @property
    def entity_label(self):
        return {'payment': "To'lov", 'expense': 'Xarajat', 'salary': "O'qituvchi maoshi",
                'receptionistsalary': 'Retsepshen maoshi', 'receptionistcommission': 'Komissiya',
                'studenttariff': 'Tarif'}.get(self.entity, self.entity)

    @property
    def action_label(self):
        return {'create': 'Yaratildi', 'update': "O'zgartirildi", 'void': 'Bekor qilindi',
                'delete': "O'chirildi", 'opening': "Boshlang'ich yozuv"}.get(self.action, self.action)

    @property
    def changes(self):
        labels = {'amount': 'Summa', 'month': 'Oy', 'paid_date': "To'lov sanasi",
                  'payment_type': "To'lov turi", 'comment': 'Izoh', 'student_id': "O'quvchi raqami",
                  'teacher_id': "O'qituvchi raqami", 'receptionist_id': 'Retsepshen raqami',
                  'voided_at': 'Bekor qilingan vaqt', 'void_reason': 'Bekor qilish sababi',
                  'salary_amount': 'Maosh', 'total_income': 'Tushum', 'percent': 'Foiz',
                  'is_paid': "To'langan", 'base_salary': 'Asosiy maosh', 'total_salary': 'Jami maosh',
                  'total_commission': 'Jami komissiya', 'payment_amount': "To'lov summasi",
                  'commission_percent': 'Komissiya foizi', 'commission_amount': 'Komissiya summasi',
                  'title': 'Nomi', 'category': 'Turi', 'date': 'Sana', 'description': 'Izoh',
                  'fee': 'Oylik tarif', 'effective_month': 'Amal qilish oyi', 'group_name': 'Guruh',
                  'billing_enabled': 'Hisoblash faol', 'is_estimated': 'Taxminiy boshlang‘ich tarif'}
        rows = []
        for key, label in labels.items():
            old, new = self.before.get(key), self.after.get(key)
            if old != new:
                rows.append({'label': label, 'before': old, 'after': new})
        return rows


class OperationalRun(models.Model):
    job = models.CharField(max_length=30, db_index=True)
    status = models.CharField(max_length=20, default='running')
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    details = models.JSONField(default=dict)

    class Meta:
        ordering = ['-started_at', '-pk']

    @property
    def job_label(self):
        return {'reminders': 'Eslatmalar', 'backup': 'Zaxiralash', 'report_worker': 'Hisobot va Telegram jarayoni'}.get(self.job, self.job)

    @property
    def status_label(self):
        return {'running': 'Bajarilmoqda', 'success': 'Muvaffaqiyatli',
                'degraded': 'Xabarlarning bir qismi yetkazilmadi', 'failed': 'Xatolik'}.get(self.status, self.status)

    @property
    def result_label(self):
        if self.status == 'failed':
            return 'Vazifa bajarilmadi. Server jurnalini tekshiring.'
        if self.status == 'running':
            return 'Vazifa hali tugamagan.'
        if self.job == 'backup':
            return f"{self.details.get('archive', '')}; {self.details.get('media_files', 0)} ta rasm/fayl; yaxlitligi tekshirildi."
        if self.job == 'report_worker':
            return f"Navbatdagi hisobotlar: {self.details.get('reports_pending', 0)}; kutilayotgan Telegram xabarlari: {self.details.get('telegram_pending', 0)}; yuborilmagan: {self.details.get('telegram_failed', 0)}."
        if not self.details.get('telegram_configured'):
            return 'CRM eslatmalari tekshirildi; Telegram guruhi sozlanmagan.'
        return f"Telegram: {self.details.get('telegram_sent', 0)} ta yuborildi, {self.details.get('telegram_pending', 0)} ta qayta yuborishni kutmoqda."


class StaffCapability(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='crm_capabilities')
    code = models.CharField(max_length=60)
    allowed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'code'], name='unique_staff_capability')]


class Enrollment(models.Model):
    STATUSES = [('planned', 'Rejalashtirilgan'), ('active', 'Faol'), ('frozen', 'Muzlatilgan'),
                ('completed', 'Tugatgan'), ('left', 'Tark etgan'), ('cancelled', 'Bekor qilingan')]
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='enrollments')
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name='enrollments')
    status = models.CharField(max_length=20, choices=STATUSES, default='active')
    starts_on = models.DateField(default=timezone.localdate)
    ends_on = models.DateField(null=True, blank=True)
    monthly_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_day = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(31)])
    is_primary = models.BooleanField(default=False)
    mirrors_student = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student'], condition=models.Q(is_primary=True), name='unique_primary_enrollment'),
                       models.CheckConstraint(condition=models.Q(monthly_fee__gte=0), name='enrollment_fee_nonnegative')]

    def __str__(self):
        return f'{self.student.name} — {self.group.name}'


class Campaign(models.Model):
    name = models.CharField(max_length=150)
    start_parameter = models.SlugField(max_length=64, unique=True)
    advertising_source = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Refund(AuditedFinancialModel):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    paid_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='refund_amount_positive')]

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Pul qaytarish yozuvi o‘zgartirilmaydi.')
        payment = Payment.all_objects.select_for_update().get(pk=self.payment_id)
        refunded = Refund.objects.filter(payment=payment).aggregate(total=models.Sum('amount'))['total'] or Decimal(0)
        if payment.voided_at or self.amount <= 0 or refunded + self.amount > payment.amount or not self.reason.strip():
            raise ValidationError('Qaytarim summasi yoki sababi noto‘g‘ri; to‘lov qoldig‘idan oshmasin.')
        if not payment.is_historical_migration:
            payment.ensure_open_period()
        super().save(*args, **kwargs)
        if not payment.is_historical_migration:
            from .payroll import refresh_unpaid_salaries
            payment._update_receptionist_commission()
            refresh_unpaid_salaries(payment)

    def delete(self, *args, **kwargs):
        raise ValidationError('Pul qaytarish yozuvi o‘chirilmaydi.')


class ReportJob(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    kind = models.CharField(max_length=30)
    file_format = models.CharField(max_length=5, default='xlsx')
    filters = models.JSONField(default=dict)
    scope_ids = models.JSONField(default=list)
    status = models.CharField(max_length=20, default='pending', db_index=True)
    file_name = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class ImportBatch(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    kind = models.CharField(max_length=30, default='students')
    strategy = models.CharField(max_length=20, default='reject')
    student = models.ForeignKey(Student, on_delete=models.PROTECT, null=True, blank=True)
    rows = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default='preview')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)


class GuardianBinding(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='guardian_bindings')
    chat_id = models.BigIntegerField()
    verified_at = models.DateTimeField(default=timezone.now)
    reports_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'chat_id'], name='unique_guardian_student_chat')]


class ReportSubscription(models.Model):
    owner = models.ForeignKey(User, on_delete=models.PROTECT)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='report_subscriptions')
    recipient = models.CharField(max_length=100)
    file_format = models.CharField(max_length=5, default='xlsx')
    enabled = models.BooleanField(default=True)
    next_run_on = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'recipient'], name='unique_student_report_subscription')]


class TelegramDelivery(models.Model):
    key = models.CharField(max_length=200, unique=True)
    chat_id = models.BigIntegerField()
    text = models.TextField(blank=True)
    report_job = models.ForeignKey(ReportJob, on_delete=models.PROTECT, null=True, blank=True)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, null=True, blank=True)
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, null=True, blank=True)
    recipient = models.CharField(max_length=100, blank=True)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, default='pending', db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.BigIntegerField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def status_label(self):
        return {'pending': 'Navbatda', 'running': 'Yuborilmoqda', 'retry': 'Qayta urinish kutilmoqda',
                'sent': 'Yuborilgan', 'failed': 'Yuborilmadi', 'cancelled': 'Bekor qilingan'}.get(self.status, self.status)



class CertificateSetting(models.Model):
    COLOR_CHOICES = [
        ('#b48c36', 'Klassik Tilla (Gold)'),
        ('#2563eb', 'Qirollik Moviy (Royal Blue)'),
        ('#059669', 'Zumrad Yashil (Emerald)'),
        ('#7c3aed', 'Binafsharang (Purple)'),
        ('#dc2626', 'Yoqut Qizil (Ruby)'),
        ('#0f2744', 'To‘q ko‘k (Deep Navy)'),
    ]

    academy_name = models.CharField(
        max_length=200,
        default="SARGET IT ACADEMY",
        verbose_name="Akademiya / Markaz nomi"
    )
    academy_subtitle = models.CharField(
        max_length=250,
        default="ZAMONAVIY AXBOROT TEXNOLOGIYALARI AKADEMIYASI",
        verbose_name="Akademiya shiori / tavsifi"
    )
    title_uz = models.CharField(
        max_length=100,
        default="SERTIFIKAT",
        verbose_name="Sertifikat asosiy sarlavhasi"
    )
    title_en = models.CharField(
        max_length=100,
        default="CERTIFICATE OF COMPLETION",
        verbose_name="Inglizcha kichik sarlavha"
    )
    statement_text = models.TextField(
        default="Ushbu sertifikat bilan rasman tasdiqlanadiki,",
        verbose_name="Kirish matni"
    )
    director_title = models.CharField(
        max_length=150,
        default="Akademiya Rahbari",
        verbose_name="Direktor lavozimi"
    )
    director_name = models.CharField(
        max_length=150,
        default="Sarget IT Academy",
        verbose_name="Direktor F.I.Sh."
    )
    instructor_default_title = models.CharField(
        max_length=150,
        default="Bosh O'qituvchi / Ustoz",
        verbose_name="O'qituvchi lavozimi"
    )
    seal_text_top = models.CharField(
        max_length=100,
        default="SARGET IT ACADEMY",
        verbose_name="Muhr ustki matni"
    )
    seal_text_mid = models.CharField(
        max_length=100,
        default="RASMIY",
        verbose_name="Muhr markaziy matni"
    )
    seal_text_bot = models.CharField(
        max_length=100,
        default="TASDIQLANGAN",
        verbose_name="Muhr pastki matni"
    )
    certificate_prefix = models.CharField(
        max_length=20,
        default="SAR",
        verbose_name="Sertifikat raqami prefiksi"
    )
    accent_color = models.CharField(
        max_length=20,
        default="#b48c36",
        choices=COLOR_CHOICES,
        verbose_name="Asosiy bezak rangi"
    )
    footer_note = models.CharField(
        max_length=255,
        default="Haqiqiy sertifikat • Takrorlanmas raqam bilan himoyalangan",
        verbose_name="Pastki xavfsizlik matni"
    )
    show_study_period = models.BooleanField(
        default=True,
        verbose_name="O'qish davrini sertifikatda ko'rsatish"
    )
    show_grade = models.BooleanField(
        default=True,
        verbose_name="Baho / Natijani ko'rsatish"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sertifikat sozlamalari"
        verbose_name_plural = "Sertifikat sozlamalari"

    def __str__(self):
        return f"Sertifikat sozlamalari ({self.academy_name})"

    @classmethod
    def get_settings(cls):
        try:
            setting = cls.objects.first()
            if not setting:
                setting = cls.objects.create()
            return setting
        except Exception:
            return cls()


def generate_unique_certificate_number():
    year = timezone.localdate().year
    try:
        prefix_val = CertificateSetting.get_settings().certificate_prefix.strip().upper()
    except Exception:
        prefix_val = "SAR"
    if not prefix_val:
        prefix_val = "SAR"
    prefix = f"{prefix_val}-{year}-"
    latest = Certificate.objects.filter(certificate_number__startswith=prefix).order_by('-certificate_number').first()
    seq = 1
    if latest:
        try:
            parts = latest.certificate_number.split('-')
            if len(parts) >= 3 and parts[-1].isdigit():
                seq = int(parts[-1]) + 1
        except Exception:
            seq = 1
    while True:
        candidate = f"{prefix}{seq:05d}"
        if not Certificate.objects.filter(certificate_number=candidate).exists():
            return candidate
        seq += 1


class Certificate(models.Model):
    STATUS_CHOICES = [
        ('active', 'Haqiqiy (Faol)'),
        ('revoked', 'Bekor qilingan'),
    ]

    certificate_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Sertifikat raqami"
    )
    verification_code = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        verbose_name="Tekshirish kodi (UUID)"
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='certificates',
        verbose_name="O'quvchi"
    )
    course_name = models.CharField(
        max_length=200,
        verbose_name="Kurs / Yo'nalish nomi"
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificates',
        verbose_name="Guruh"
    )
    teacher_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="O'qituvchi / Ustoz"
    )
    grade_text = models.CharField(
        max_length=120,
        blank=True,
        default="Muvaffaqiyatli tamomladi",
        verbose_name="Natija / Baho"
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="O'qish boshlangan sana"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="O'qish tugagan sana"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Qo'shimcha tavsif / Izoh"
    )
    issue_date = models.DateField(
        default=timezone.localdate,
        verbose_name="Berilgan sana"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name="Holat"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Kim tomonidan berildi"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date', '-created_at']
        verbose_name = "Sertifikat"
        verbose_name_plural = "Sertifikatlar"

    def __str__(self):
        return f"{self.certificate_number} — {self.student.name} ({self.course_name})"

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            self.certificate_number = generate_unique_certificate_number()
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return self.status == 'active'

    @property
    def study_period_display(self):
        if self.start_date and self.end_date:
            return f"{self.start_date.strftime('%d.%m.%Y')} — {self.end_date.strftime('%d.%m.%Y')}"
        elif self.start_date:
            return f"{self.start_date.strftime('%d.%m.%Y')} dan"
        elif self.end_date:
            return f"{self.end_date.strftime('%d.%m.%Y')} gacha"
        return ""

    def get_verification_url(self, request=None):
        from django.urls import reverse
        path = reverse('certificate_verify', args=[self.certificate_number])
        if request:
            return request.build_absolute_uri(path)
        return path
