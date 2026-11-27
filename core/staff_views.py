from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Branch, Campaign, Enrollment, Refund, Payment, Student, StaffCapability, Teacher, Receptionist, AssignmentHistory
from .forms import (
    ReceptionistAccountProfileForm,
    StaffAccountProfileForm,
    UserProfileForm,
)
from .permissions import (CAPABILITIES, CAPABILITY_DEPENDENCIES, DEFAULT_CAPABILITIES, assignable_capabilities, expand_capabilities, capability_required,
                          get_role, has_capability, is_admin,
                          get_teacher, get_receptionist, visible_students, visible_groups, admin_required)
from .utils import sync_user_display_name


@login_required
@admin_required
@transaction.atomic
def staff_permissions(request):
    users = get_user_model().objects.filter(Q(teacher_profile__isnull=False) | Q(receptionist_profile__isnull=False)).filter(is_superuser=False).distinct()
    target = None
    if request.GET.get('user', '').isdigit():
        target = get_object_or_404(users, pk=request.GET['user'])
    if request.method == 'POST':
        target = get_object_or_404(users, pk=request.POST.get('user'))
        role = get_role(target)
        assignable = assignable_capabilities(role)
        requested = expand_capabilities(set(request.POST.getlist('capabilities')) & assignable)
        for code in CAPABILITIES:
            allowed = code in requested and code in assignable
            StaffCapability.objects.update_or_create(user=target, code=code, defaults={'allowed': allowed})
        messages.success(request, 'Xodim huquqlari saqlandi. Keyingi so‘rovdan kuchga kiradi.')
        return redirect(request.path + f'?user={target.pk}')
    if target:
        role = get_role(target)
        visible_capabilities = assignable_capabilities(role)
        rows = [
            {'code': code, 'label': label,
             'allowed': has_capability(target, code),
             'dependencies': ' '.join(CAPABILITY_DEPENDENCIES.get(code, ())),
             'group': code.split('.')[0]}
            for code, label in CAPABILITIES.items() if code in visible_capabilities
        ]
    else:
        rows = []
    labels = {'students': "O'quvchilar", 'groups': 'Guruhlar', 'courses': 'Kurslar', 'teachers': "O'qituvchilar",
              'receptionists': 'Retsepshenlar', 'payments': "To'lovlar", 'salary': 'Oyliklar', 'expenses': 'Xarajatlar',
              'attendance': 'Davomat', 'grades': 'Baholar', 'reports': 'Hisobotlar', 'imports': 'Excel import',
              'leads': 'Murojaatlar', 'messages': 'Telegram xabarlari', 'profile': 'Shaxsiy profil',
              'certificates': 'Sertifikatlar', 'assignments': 'Biriktirish tarixi', 'finance': 'Umumiy moliya',
              'settings': 'Filial va kampaniyalar', 'system': 'Tizim holati'}
    groups = [{'label': label, 'rows': [row for row in rows if row['group'] == key]} for key, label in labels.items()]
    return render(request, 'core/staff_permissions.html', {'staff_users': users, 'target': target, 'permission_rows': rows,
                  'permission_groups': [group for group in groups if group['rows']]})


@login_required
@transaction.atomic
def profile_edit(request):
    profile = get_teacher(request.user) or get_receptionist(request.user)
    is_admin_account = profile is None and is_admin(request.user)
    if profile is None and not is_admin_account:
        raise PermissionDenied('Xodim profili topilmadi.')

    password_form = PasswordChangeForm(request.user, request.POST if request.POST.get('form_type') == 'password' else None)
    for field in password_form.fields.values():
        field.widget.attrs['class'] = 'form-control'
    password_form.fields['old_password'].label = 'Amaldagi parol'
    password_form.fields['new_password1'].label = 'Yangi parol'
    password_form.fields['new_password2'].label = 'Yangi parolni tasdiqlang'
    profile_form = None

    if request.method == 'POST' and request.POST.get('form_type') == 'password':
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Parolingiz yangilandi.')
            return redirect('profile_edit')
    elif profile:
        profile_form_class = (
            ReceptionistAccountProfileForm if isinstance(profile, Receptionist)
            else StaffAccountProfileForm
        )
        profile_form = profile_form_class(
            request.POST or None, request.FILES or None,
            instance=profile, user=request.user,
        )
        if profile_form.is_valid():
            photo = profile_form.cleaned_data.get('photo')
            if photo and getattr(photo, 'size', 0) > 5 * 1024 * 1024:
                profile_form.add_error('photo', 'Rasm 5 MBdan oshmasin.')
            else:
                profile_form.save()
                messages.success(request, 'Profilingiz yangilandi.')
                return redirect('profile_edit')
    else:
        profile_form = UserProfileForm(request.POST or None, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, 'Profilingiz yangilandi.')
            return redirect('profile_edit')

    if profile_form is None:
        if profile:
            profile_form_class = ReceptionistAccountProfileForm if isinstance(profile, Receptionist) else StaffAccountProfileForm
            profile_form = profile_form_class(instance=profile, user=request.user)
        else:
            profile_form = UserProfileForm(instance=request.user)
    work_details = []
    if isinstance(profile, Teacher):
        work_details = [
            ('Lavozim', "O'qituvchi"),
            ('Fan', profile.subject),
            ('Ustoz ulushi', f'{profile.percent}%'),
            ('Faol holati', 'Faol' if profile.is_active else 'Faol emas'),
        ]
    elif isinstance(profile, Receptionist):
        work_details = [
            ('Lavozim', 'Retsepshen'),
            ('Komissiya', f'{profile.commission_percent}%'),
            ('Faol holati', 'Faol' if profile.is_active else 'Faol emas'),
        ]
    return render(request, 'core/profile_edit.html', {
        'form': profile_form,
        'password_form': password_form,
        'profile': profile,
        'work_details': work_details,
        'title': 'Mening profilim',
        'is_admin_account': is_admin_account,
    })


@login_required
@capability_required('settings.manage')
def report_settings(request):
    BranchForm = forms.modelform_factory(Branch, fields=['name', 'is_active'])
    CampaignForm = forms.modelform_factory(Campaign, fields=['name', 'start_parameter', 'advertising_source', 'is_active'])
    kind = request.POST.get('kind')
    branch_form = BranchForm(request.POST if kind == 'branch' else None, prefix='branch')
    campaign_form = CampaignForm(request.POST if kind == 'campaign' else None, prefix='campaign')
    for field, label in {'name': 'Filial nomi', 'is_active': 'Faol'}.items():
        branch_form.fields[field].label = label
    for field, label in {'name': 'Kampaniya nomi', 'start_parameter': 'Bot havolasidagi start kodi', 'advertising_source': 'Reklama manbasi', 'is_active': 'Faol'}.items():
        campaign_form.fields[field].label = label
    form = branch_form if kind == 'branch' else campaign_form
    if request.method == 'POST' and kind in ('branch', 'campaign') and form.is_valid():
        form.save()
        messages.success(request, 'Sozlama saqlandi.')
        return redirect('report_settings')
    return render(request, 'core/report_settings.html', {'branch_form': branch_form, 'campaign_form': campaign_form,
                  'branches': Branch.objects.all(), 'campaigns': Campaign.objects.all()})


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ['group', 'status', 'starts_on', 'ends_on', 'monthly_fee', 'due_day']
        labels = {'group': 'Guruh', 'status': 'Holat', 'starts_on': 'Boshlanish sanasi', 'ends_on': 'Tugash / to‘xtash sanasi', 'monthly_fee': 'Kelishilgan oylik narx (UZS)', 'due_day': 'To‘lov kuni (1–31)'}
        widgets = {'starts_on': forms.DateInput(attrs={'type': 'date'}), 'ends_on': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].queryset = visible_groups(user).filter(is_active=True)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        if self.instance.pk:
            # An enrollment carries its own history. Transfer uses a new enrollment.
            for field in ('group', 'starts_on', 'monthly_fee', 'due_day'):
                self.fields[field].disabled = True

    def clean(self):
        values = super().clean()
        group = values.get('group')
        if group and values.get('status') == 'active' and not self.instance.pk and group.is_full():
            self.add_error('group', 'Guruhda bo‘sh joy yo‘q.')
        if values.get('ends_on') and values.get('starts_on') and values['ends_on'] < values['starts_on']:
            self.add_error('ends_on', 'Tugash sanasi boshlanishdan oldin bo‘lmasin.')
        if self.instance.pk and values.get('status') in ('frozen', 'completed', 'left') and not values.get('ends_on'):
            self.add_error('ends_on', 'Hisoblash to‘xtaydigan sanani kiriting.')
        return values


@login_required
@transaction.atomic
def enrollment_edit(request, student_id, pk=None):
    student = get_object_or_404(visible_students(request.user), pk=student_id)
    instance = get_object_or_404(Enrollment, pk=pk, student=student) if pk else Enrollment(student=student)
    if instance.pk and instance.mirrors_student:
        messages.info(request, 'Asosiy guruhni o‘quvchi kartasidan tahrirlang.')
        return redirect('student_edit', pk=student.pk)
    form = EnrollmentForm(request.POST or None, instance=instance, user=request.user)
    if form.is_valid():
        group = form.cleaned_data['group']
        if not pk and Enrollment.objects.filter(student=student, group=group, status__in=['active', 'planned']).exists():
            form.add_error('group', 'Bu o‘quvchi ushbu guruhga allaqachon yozilgan.')
        else:
            enrollment = form.save()
            if enrollment.status == 'active' and student.status == 'pending':
                student.status = 'active'
                student.save(update_fields=['status'])
            messages.success(request, 'Kursga yozilish saqlandi.')
            return redirect('student_detail', pk=student.pk)
    return render(request, 'core/simple_form.html', {'form': form, 'title': f'{student.name}: kursga yozilish'})


@login_required
@require_POST
def student_restore(request, pk):
    student = get_object_or_404(visible_students(request.user), pk=pk)
    if student.group and student.group.is_full():
        messages.error(request, 'Guruh to‘la. Avval bo‘sh guruhga biriktiring.')
    else:
        student.status = 'active' if student.group_id else 'pending'
        student.save(update_fields=['status'])
        messages.success(request, 'O‘quvchi tiklandi.')
    return redirect('student_detail', pk=pk)


@login_required
@capability_required('payments.refund')
def refund_create(request, pk):
    payment = get_object_or_404(Payment.objects.filter(student__in=visible_students(request.user)), pk=pk)
    RefundForm = forms.modelform_factory(Refund, fields=['amount', 'reason'])
    refund = Refund(payment=payment, created_by=request.user)
    form = RefundForm(request.POST or None, instance=refund)
    form.fields['amount'].label = 'Qaytarilayotgan summa (UZS)'
    form.fields['reason'].label = 'Qaytarish sababi'
    if form.is_valid():
        try:
            form.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Pul qaytarish yozuvi saqlandi.')
            return redirect('payment_receipt', pk=pk)
    return render(request, 'core/simple_form.html', {'form': form, 'title': f'{payment.receipt_number}: pul qaytarish'})
