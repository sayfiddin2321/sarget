from django import forms
from django.db.models import Q
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from .models import *
from .utils import group_conflict_messages, sync_user_display_name


class NotificationFilterForm(forms.Form):
    date_from = forms.DateField(label='Sanadan', required=False,
                               widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    date_to = forms.DateField(label='Sanagacha', required=False,
                             widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    status = forms.ChoiceField(label='Holati', required=False,
                              choices=[('', 'Barchasi'), ('unread', "O'qilmagan"), ('read', "O'qilgan")],
                              widget=forms.Select(attrs={'class': 'form-select'}))
    type = forms.ChoiceField(label='Turi', required=False,
                            choices=[('', 'Barcha turlar'), *Notification.TYPE_CHOICES],
                            widget=forms.Select(attrs={'class': 'form-select'}))
    q = forms.CharField(label='Xabar bo‘yicha qidirish', required=False, max_length=200,
                        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Sarlavha yoki xabar...'}))

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise forms.ValidationError('Boshlanish sanasi tugash sanasidan keyin bo‘lmasin.')
        return data

    def filter_queryset(self, queryset):
        if not self.is_valid():
            return queryset.none()
        data = self.cleaned_data
        if data.get('date_from'):
            queryset = queryset.filter(created_at__date__gte=data['date_from'])
        if data.get('date_to'):
            queryset = queryset.filter(created_at__date__lte=data['date_to'])
        if data.get('status'):
            queryset = queryset.filter(is_read=data['status'] == 'read')
        if data.get('type'):
            queryset = queryset.filter(type=data['type'])
        if data.get('q'):
            queryset = queryset.filter(Q(title__icontains=data['q']) | Q(message__icontains=data['q']))
        return queryset


class UserProfileForm(forms.ModelForm):
    username = forms.CharField(label='Login nomi', max_length=150, required=False)

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name']
        labels = {
            'email': 'Elektron pochta',
            'first_name': 'Ism',
            'last_name': 'Familiya',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'given-name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'family-name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].initial = self.instance.username
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'autocomplete': 'username'})
        self.order_fields(['first_name', 'last_name', 'username', 'email'])

    def clean_username(self):
        username = self.cleaned_data['username'].strip() or self.instance.username
        if User.objects.exclude(pk=self.instance.pk).filter(username__iexact=username).exists():
            raise forms.ValidationError('Bu login nomi band.')
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['username']
        if commit:
            user.save()
        return user


class StaffAccountProfileForm(forms.ModelForm):
    username = forms.CharField(label='Login nomi', max_length=150, required=False)

    class Meta:
        model = Teacher
        fields = ['name', 'phone', 'photo', 'notes']
        labels = {
            'name': 'Ism va familiya',
            'phone': 'Telefon',
            'photo': 'Profil rasmi',
            'notes': 'Izoh',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'tel'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['username'].initial = user.username
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'autocomplete': 'username'})

    def clean_username(self):
        username = self.cleaned_data['username'].strip() or self.user.username
        if User.objects.exclude(pk=self.user.pk).filter(username__iexact=username).exists():
            raise forms.ValidationError('Bu login nomi band.')
        return username

    def save(self, commit=True):
        profile = super().save(commit=commit)
        self.user.username = self.cleaned_data['username']
        self.user.save(update_fields=['username'])
        sync_user_display_name(self.user, profile.name)
        return profile


class ReceptionistAccountProfileForm(StaffAccountProfileForm):
    class Meta(StaffAccountProfileForm.Meta):
        model = Receptionist


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'photo',
            'name',
            'phone',
            'parent_phone',
            'birth_date',
            'registration_date',
            'teacher',
            'group',
            'receptionist',
            'status',
            'source',
            'discount_percent',
            'notes',
            'branch',
            'payment_due_day',
        ]
        widgets = {
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*', 'capture': 'user'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ism familiya'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998 XX XXX XX XX'}),
            'parent_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998 XX XXX XX XX'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'registration_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'teacher': forms.Select(attrs={'class': 'form-select select2'}),
            'group': forms.Select(attrs={'class': 'form-select select2'}),
            'receptionist': forms.Select(attrs={'class': 'form-select select2'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'source': forms.Select(attrs={'class': 'form-select'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': "Qo'shimcha ma'lumot..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and 'registration_date' not in self.initial:
            self.initial['registration_date'] = timezone.localdate()
        self.fields['photo'].widget.attrs.update({'accept': 'image/*'})
        self.fields['photo'].required = False
        self.fields['branch'].widget.attrs['class'] = 'form-select'
        self.fields['payment_due_day'].widget = forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31})
        self.fields['payment_due_day'].help_text = "Kelishilgan to'lov kuni (1–31). O'zgarish keyingi oydan."
        self.fields['teacher'].queryset = Teacher.objects.filter(is_active=True).order_by('name')
        self.fields['group'].queryset = Group.objects.filter(is_active=True).order_by('name')
        self.fields['receptionist'].queryset = Receptionist.objects.filter(is_active=True).order_by('name')
        self.fields['receptionist'].required = False
        self.fields['teacher'].required = False
        self.fields['group'].required = False
        self.fields['registration_date'].required = False
        self.fields['teacher'].empty_label = "— O'qituvchi tanlang —"
        self.fields['group'].empty_label = "— Guruh tanlang —"
        self.fields['receptionist'].empty_label = "— Retsepshen tanlang —"
        self.fields['photo'].help_text = "O'quvchi rasmi ixtiyoriy."
        self.fields['group'].required = False
        self.fields['teacher'].empty_label = "— O'qituvchi tanlang —"
        self.fields['group'].empty_label = "— Guruh tanlang —"
        self.fields['receptionist'].empty_label = "— Retsepshen tanlang —"
        self.fields['photo'].help_text = "O'quvchi rasmi ixtiyoriy."

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) < 9:
            raise forms.ValidationError("Telefon raqam kamida 9 ta raqamdan iborat bo'lishi kerak")
        return phone

    def clean(self):
        cleaned = super().clean()
        group = cleaned.get('group')
        teacher = cleaned.get('teacher')
        if group:
            if teacher and group.teacher_id != teacher.pk:
                self.add_error('teacher', "O'qituvchi tanlangan guruhga mos emas.")
            elif not teacher:
                cleaned['teacher'] = group.teacher
            changing_group = not self.instance.pk or self.instance.group_id != group.pk or self.instance.status != 'active'
            if cleaned.get('status') == 'active' and changing_group and group.is_full():
                self.add_error('group', "Guruhda bo'sh joy yo'q.")
        if self.errors.get('photo'):
            return cleaned
        photo = cleaned.get('photo')
        if self.instance and self.instance.pk and self.instance.photo:
            if photo in (None, ''):
                cleaned['photo'] = self.instance.photo
                return cleaned
            if photo is False:
                self.add_error('photo', "Rasmni o'chirib bo'lmaydi. Yangi rasm yuklang.")
        return cleaned

    def clean_discount_percent(self):
        dp = self.cleaned_data.get('discount_percent', 0)
        if dp < 0 or dp > 100:
            raise forms.ValidationError("Chegirma 0-100 oralig'ida bo'lishi kerak")
        return dp


class ReceptionistStudentForm(forms.ModelForm):
    """Retsepshen uchun: yangi o'quvchi qabul qilish formasi.
    Faqat asosiy ma'lumotlar — guruh/o'qituvchi/chegirma/status admin tomonidan beriladi."""
    class Meta:
        model = Student
        fields = ['photo', 'name', 'phone', 'parent_phone', 'birth_date', 'registration_date', 'source', 'notes']
        widgets = {
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*', 'capture': 'user'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ism familiya'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998 XX XXX XX XX'}),
            'parent_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998 XX XXX XX XX'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'registration_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'source': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': "Qo'shimcha ma'lumot..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and 'registration_date' not in self.initial:
            self.initial['registration_date'] = timezone.localdate()
        self.fields['photo'].required = False
        self.fields['registration_date'].required = False
        self.fields['source'].initial = 'reception'

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) < 9:
            raise forms.ValidationError("Telefon raqam kamida 9 ta raqamdan iborat bo'lishi kerak")
        return phone


class TeacherForm(forms.ModelForm):
    username = forms.CharField(
        required=False, label="Login (tizimga kirish uchun)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'masalan: aziz_teacher', 'autocomplete': 'off'})
    )
    password = forms.CharField(
        required=False, label="Parol",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': "Kamida 6 ta belgi", 'autocomplete': 'new-password'})
    )

    class Meta:
        model = Teacher
        fields = ['name', 'phone', 'subject', 'percent', 'photo', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ism familiya'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998 XX XXX XX XX'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Fan nomi'}),
            'percent': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user_id:
            self.fields['username'].initial = self.instance.user.username
            self.fields['password'].help_text = "Bo'sh qoldirsangiz, parol o'zgarmaydi"

    def clean_percent(self):
        p = self.cleaned_data.get('percent')
        if p is None or p < 0 or p > 100:
            raise forms.ValidationError("Foiz 0-100 oralig'ida bo'lishi kerak")
        return p

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            return username
        qs = User.objects.filter(username=username)
        if self.instance and self.instance.pk and self.instance.user_id:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("Bu login band. Boshqasini tanlang.")
        return username

    def clean_password(self):
        pwd = self.cleaned_data.get('password', '')
        if pwd:
            validate_password(pwd, self.instance.user if self.instance.user_id else None)
        elif self.cleaned_data.get('username') and not self.instance.user_id:
            raise forms.ValidationError("Yangi login uchun parol kiriting.")
        return pwd

    @transaction.atomic
    def save(self, commit=True):
        teacher = super().save(commit=False)
        username = self.cleaned_data.get('username', '').strip()
        password = self.cleaned_data.get('password', '')

        if username:
            if teacher.user_id:
                user = teacher.user
                user.username = username
                if password:
                    user.set_password(password)
                user.save()
            else:
                user = User.objects.create_user(username=username, password=password)
                user.save()
                teacher.user = user

        if commit:
            teacher.save()
        if teacher.user_id:
            sync_user_display_name(teacher.user, teacher.name)
        return teacher


class ReceptionistForm(forms.ModelForm):
    username = forms.CharField(
        required=False, label="Login (tizimga kirish uchun)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'masalan: nigora_reception', 'autocomplete': 'off'})
    )
    password = forms.CharField(
        required=False, label="Parol",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': "Kamida 6 ta belgi", 'autocomplete': 'new-password'})
    )

    class Meta:
        model = Receptionist
        fields = ['name', 'phone', 'commission_percent', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ism familiya'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998 XX XXX XX XX'}),
            'commission_percent': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100, 'step': '0.5'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user_id:
            self.fields['username'].initial = self.instance.user.username
            self.fields['password'].help_text = "Bo'sh qoldirsangiz, parol o'zgarmaydi"

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            return username
        qs = User.objects.filter(username=username)
        if self.instance and self.instance.pk and self.instance.user_id:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("Bu login band. Boshqasini tanlang.")
        return username

    def clean_password(self):
        pwd = self.cleaned_data.get('password', '')
        if pwd:
            validate_password(pwd, self.instance.user if self.instance.user_id else None)
        elif self.cleaned_data.get('username') and not self.instance.user_id:
            raise forms.ValidationError("Yangi login uchun parol kiriting.")
        return pwd

    @transaction.atomic
    def save(self, commit=True):
        rec = super().save(commit=False)
        username = self.cleaned_data.get('username', '').strip()
        password = self.cleaned_data.get('password', '')

        if username:
            if rec.user_id:
                user = rec.user
                user.username = username
                if password:
                    user.set_password(password)
                user.save()
            else:
                user = User.objects.create_user(username=username, password=password)
                user.save()
                rec.user = user

        if commit:
            rec.save()
        if rec.user_id:
            sync_user_display_name(rec.user, rec.name)
        return rec


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Masalan: Python dasturlash',
                'maxlength': 100,
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Kurs haqida qisqacha ma’lumot (ixtiyoriy)',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        duplicate = Course.objects.filter(name__iexact=name)
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("Bu kurs nomi allaqachon qo‘shilgan.")
        return name


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'course', 'branch', 'teacher', 'room', 'days', 'custom_days', 'start_time', 'end_time',
                  'monthly_fee', 'max_students', 'is_active', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IELTS-1, Frontend-A ...'}),
            'teacher': forms.Select(attrs={'class': 'form-select select2'}),
            'room': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '101, 202 ...'}),
            'days': forms.Select(attrs={'class': 'form-select', 'id': 'id_days'}),
            'custom_days': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Masalan: Har kuni 18:00 da'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'monthly_fee': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '500000'}),
            'max_students': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 500}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = Teacher.objects.filter(is_active=True).order_by('name')
        self.fields['teacher'].empty_label = "— O'qituvchi tanlang —"
        self.fields['custom_days'].required = False
        self.fields['monthly_fee'].help_text = "Narx o'zgarishi keyingi oydan amal qiladi. O'tgan oylar saqlanadi."
        self.conflict_warnings = []

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('days') == 'custom' and not cleaned.get('custom_days'):
            self.add_error('custom_days', "Boshqa kunlarni tanlasangiz, matn kiriting")
        if cleaned.get('end_time') and cleaned.get('start_time') and cleaned['end_time'] <= cleaned['start_time']:
            self.add_error('end_time', "Tugash vaqti boshlanish vaqtidan keyin bo'lishi kerak")
        if cleaned.get('max_students') is not None and cleaned['max_students'] > 500:
            self.add_error('max_students', "Guruhga eng ko'pi bilan 500 o'quvchi sig'adi")
        if self.errors:
            return cleaned
        if cleaned.get('is_active', True):
            self._check_conflicts(cleaned)
        return cleaned

    def _check_conflicts(self, cleaned):
        """Faol guruhni saqlashdan oldin xona/o'qituvchi to'qnashuvini tekshiradi.

        Jadval sahifasidagi bilan bir xil qoida (`group_conflict_messages`) ishlatiladi,
        natija `conflict_warnings`ga yoziladi va forma sahifasida ko'rsatiladi.
        """
        candidate = Group(
            pk=self.instance.pk,
            teacher_id=cleaned.get('teacher').pk if cleaned.get('teacher') else None,
            room=cleaned.get('room') or '',
            days=cleaned.get('days') or '',
            start_time=cleaned.get('start_time'),
            end_time=cleaned.get('end_time'),
        )
        against = Group.objects.filter(is_active=True)
        if self.instance.pk:
            against = against.exclude(pk=self.instance.pk)
        against = list(against)
        # To'qnashuv yangi guruhni saqlashga to'sqinlik qilmaydi: jadval sahifasi
        # bu holatni qizil belgi bilan ko'rsatadi. Guruhni bu yerda rad etish
        # jadvalni keyin tuzatishga yo'l qo'ymas edi.
        messages = group_conflict_messages(candidate, against)
        if messages:
            self.conflict_warnings = messages


class PaymentForm(forms.ModelForm):
    submission_key = forms.UUIDField(required=False, initial=uuid.uuid4, widget=forms.HiddenInput)
    paid_date = forms.DateTimeField(
        label="Pul tushgan sana va vaqt", required=False,
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'}),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S'],
    )
    month = forms.DateField(
        label="Qaysi oy darslari uchun",
        widget=forms.DateInput(attrs={'type': 'month', 'class': 'form-control'}),
        input_formats=['%Y-%m'],
        required=True,
    )

    class Meta:
        model = Payment
        fields = ['student', 'enrollment', 'amount', 'month', 'paid_date', 'payment_type', 'comment']
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select select2', 'data-placeholder': "O'quvchi tanlang..."}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '1000', 'placeholder': '500000'}),
            'month': forms.DateInput(attrs={'type': 'month', 'class': 'form-control'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Izoh (ixtiyoriy)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['student'].disabled = True
            self.fields['student'].help_text = "To'lov egasi o'zgarmaydi. Xato bo'lsa to'lovni bekor qilib, yangisini kiriting."
        student_qs = Student.objects.select_related('group', 'teacher')
        self.fields['student'].queryset = student_qs.order_by('group__name', 'name')
        self.fields['student'].empty_label = "— O'quvchi tanlang —"
        def _student_label(student):
            label = student.search_label
            if student.status != 'active':
                label += f" [{student.get_status_display()}]"
            return label
        self.fields['student'].label_from_instance = _student_label
        self.fields['student'].widget.attrs.update({
            'data-placeholder': "Ism, guruh, telefon yoki ota-ona telefoni...",
        })
        self.fields['enrollment'].queryset = Enrollment.objects.select_related('student', 'group').filter(status__in=['active', 'planned'])
        self.fields['enrollment'].widget.attrs['class'] = 'form-select select2'

    def clean(self):
        values = super().clean()
        enrollment, student = values.get('enrollment'), values.get('student')
        if enrollment and student and enrollment.student_id != student.pk:
            self.add_error('enrollment', 'Kursga yozilish tanlangan o‘quvchiga tegishli emas.')
        return values

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise forms.ValidationError("Summa musbat bo'lishi kerak")
        return amount

    def clean_month(self):
        month = self.cleaned_data.get('month')
        if month and month.day != 1:
            month = month.replace(day=1)
        return month

    def clean_paid_date(self):
        value = self.cleaned_data.get('paid_date') or self.instance.paid_date or timezone.now()
        if self.instance.pk and value.replace(second=0, microsecond=0) == self.instance.paid_date.replace(second=0, microsecond=0):
            return self.instance.paid_date
        return value


class ExpenseForm(forms.ModelForm):
    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Xarajat musbat bo'lishi kerak.")
        return amount

    class Meta:
        model = Expense
        fields = ['title', 'category', 'amount', 'date', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Xarajat nomi'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '1000', 'placeholder': '0'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Izoh...'}),
        }


class AttendanceFilterForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )
    group = forms.ModelChoiceField(
        queryset=Group.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select select2'}),
        required=False,
        empty_label="— Guruh tanlang —"
    )


class AttendanceChoiceForm(forms.Form):
    group = forms.ModelChoiceField(
        label='Guruh',
        queryset=Group.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select select2', 'data-placeholder': 'Guruh tanlang'}),
        empty_label='Guruh tanlang'
    )

    def __init__(self, *args, **kwargs):
        teacher = kwargs.pop('teacher', None)
        super().__init__(*args, **kwargs)
        if teacher:
            self.fields['group'].queryset = teacher.groups.filter(is_active=True).order_by('name')


class GradeChoiceForm(forms.Form):
    group = forms.ModelChoiceField(
        label='Guruh',
        queryset=Group.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select select2', 'data-placeholder': 'Guruh tanlang'}),
        empty_label='Guruh tanlang'
    )

    def __init__(self, *args, **kwargs):
        teacher = kwargs.pop('teacher', None)
        super().__init__(*args, **kwargs)
        if teacher:
            self.fields['group'].queryset = teacher.groups.filter(is_active=True).order_by('name')



class CertificateForm(forms.ModelForm):
    class Meta:
        model = Certificate
        fields = [
            'student',
            'certificate_number',
            'course_name',
            'group',
            'teacher_name',
            'grade_text',
            'start_date',
            'end_date',
            'issue_date',
            'status',
            'description',
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select select2', 'data-placeholder': "O'quvchi tanlang..."}),
            'certificate_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SAR-2026-00001'}),
            'course_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: Python Backend Dasturlash"}),
            'group': forms.Select(attrs={'class': 'form-select select2'}),
            'teacher_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "O'qituvchi F.I.Sh."}),
            'grade_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: Muvaffaqiyatli tamomladi / A'lo (95 ball)"}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': "Kurs davomida o'zlashtirilgan bilim va ko'nikmalar (ixtiyoriy)..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = Student.objects.select_related('group', 'teacher').order_by('name')
        self.fields['student'].empty_label = "— O'quvchini tanlang —"
        self.fields['group'].queryset = Group.objects.filter(is_active=True).order_by('name')
        self.fields['group'].empty_label = "— Guruh (ixtiyoriy) —"
        self.fields['group'].required = False
        self.fields['teacher_name'].required = False
        self.fields['grade_text'].required = False
        self.fields['start_date'].required = False
        self.fields['end_date'].required = False
        self.fields['description'].required = False

        def _student_label(s):
            parts = [s.name]
            if s.group:
                parts.append(s.group.name)
            if s.phone:
                parts.append(s.phone)
            if s.status != 'active':
                parts.append(f"[{s.get_status_display()}]")
            return " | ".join(parts)
        self.fields['student'].label_from_instance = _student_label

        if not self.instance.pk:
            if not self.initial.get('certificate_number'):
                self.initial['certificate_number'] = generate_unique_certificate_number()
            if not self.initial.get('issue_date'):
                self.initial['issue_date'] = timezone.localdate()

    def clean_certificate_number(self):
        num = self.cleaned_data.get('certificate_number', '').strip()
        if not num:
            raise forms.ValidationError("Sertifikat raqami kiritilishi shart.")
        qs = Certificate.objects.filter(certificate_number__iexact=num)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Bu raqamdagi ({num}) sertifikat allaqachon mavjud! Boshqa raqam kiriting.")
        return num

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', "O'qish tugagan sana boshlanish sanasidan oldin bo'lishi mumkin emas.")
        return cleaned_data


class CertificateSettingForm(forms.ModelForm):
    class Meta:
        model = CertificateSetting
        fields = [
            'academy_name',
            'academy_subtitle',
            'title_uz',
            'title_en',
            'statement_text',
            'director_title',
            'director_name',
            'instructor_default_title',
            'seal_text_top',
            'seal_text_mid',
            'seal_text_bot',
            'certificate_prefix',
            'accent_color',
            'footer_note',
            'show_study_period',
            'show_grade',
        ]
        widgets = {
            'academy_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SARGET IT ACADEMY'}),
            'academy_subtitle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ZAMONAVIY AXBOROT TEXNOLOGIYALARI AKADEMIYASI'}),
            'title_uz': forms.TextInput(attrs={'class': 'form-control'}),
            'title_en': forms.TextInput(attrs={'class': 'form-control'}),
            'statement_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'director_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Akademiya Rahbari'}),
            'director_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Sayfiddin ...'}),
            'instructor_default_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Bosh O'qituvchi / Ustoz"}),
            'seal_text_top': forms.TextInput(attrs={'class': 'form-control'}),
            'seal_text_mid': forms.TextInput(attrs={'class': 'form-control'}),
            'seal_text_bot': forms.TextInput(attrs={'class': 'form-control'}),
            'certificate_prefix': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SAR', 'style': 'text-transform:uppercase'}),
            'accent_color': forms.Select(attrs={'class': 'form-select'}),
            'footer_note': forms.TextInput(attrs={'class': 'form-control'}),
            'show_study_period': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_grade': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
