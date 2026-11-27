"""
SargetCRM rol va ruxsatlar tizimi.

Uch xil rol:
  ADMIN        - is_superuser=True | Teacher/Receptionist bog'liq emas va is_staff
  TEACHER      - Teacher modelida user = bu user
  RECEPTIONIST - Receptionist modelida user = bu user
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from datetime import datetime

ADMIN = 'admin'
RECEPTIONIST = 'receptionist'
TEACHER = 'teacher'
UNKNOWN = 'unknown'
TEACHER_OWN_SALARY = 'salary.teacher_self.view'
RECEPTIONIST_OWN_SALARY = 'salary.receptionist_self.view'


def get_role(user):
    if not user or not user.is_authenticated or not user.is_active:
        return UNKNOWN
    if user.is_superuser:
        return ADMIN
    # OneToOne related: Django uses lowercase model name as accessor
    try:
        return TEACHER if user.teacher_profile.is_active else UNKNOWN
    except ObjectDoesNotExist:
        pass
    try:
        return RECEPTIONIST if user.receptionist_profile.is_active else UNKNOWN
    except ObjectDoesNotExist:
        pass
    return UNKNOWN


def get_teacher(user):
    try:
        return user.teacher_profile
    except Exception:
        return None


def get_receptionist(user):
    try:
        return user.receptionist_profile
    except Exception:
        return None


def is_admin(user):
    return get_role(user) == ADMIN


def is_receptionist(user):
    return get_role(user) == RECEPTIONIST


def is_teacher(user):
    return get_role(user) == TEACHER


def role_context(user):
    role = get_role(user)
    return {
        'user_role': role,
        'is_admin_role': role == ADMIN,
        'is_receptionist_role': role == RECEPTIONIST,
        'is_teacher_role': role == TEACHER,
    }


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_admin(request.user):
            messages.error(request, "Bu sahifaga faqat Boshliq kirishi mumkin!")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def capability_required(code):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not has_capability(request.user, code):
                return HttpResponseForbidden("Bu amal uchun sizga ruxsat berilmagan.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def finance_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_admin(request.user):
            messages.error(request, "Moliyaviy ma'lumotlar faqat Boshliqqa ko'rinadi!")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def not_receptionist_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if get_role(request.user) not in (ADMIN, TEACHER):
            messages.error(request, "Bu bo'limga retsepshen kira olmaydi!")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def no_teacher_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if get_role(request.user) not in (ADMIN, RECEPTIONIST):
            messages.error(request, "Bu bo'limga o'qituvchi kira olmaydi!")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def visible_students(user):
    from .models import Student
    from django.db.models import Q
    qs = Student.objects.all()
    if not has_capability(user, 'students.view'):
        return qs.none()
    if is_admin(user):
        return qs
    if is_teacher(user):
        teacher = get_teacher(user)
        return qs.filter(Q(teacher=teacher) | Q(enrollments__group__teacher=teacher, enrollments__status='active', enrollments__mirrors_student=False)).distinct()
    if is_receptionist(user):
        return qs
    return qs.none()


class BusinessRoleMiddleware:
    """A logged-in account without an active business role gets no CRM access."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.user.is_authenticated and get_role(request.user) == UNKNOWN
                and request.path not in ('/login/', '/logout/')
                and not (
                    request.user.is_staff
                    and (request.path == '/admin' or request.path.startswith('/admin/'))
                )
                and not request.path.startswith('/certificate/verify/')
                and not request.path.startswith('/c/')
                and not request.path.startswith('/receipt/verify/')):
            return HttpResponseForbidden("Hisobingizga faol rol biriktirilmagan. Administratorga murojaat qiling.")
        if request.user.is_authenticated and request.path != '/integrations/telegram/webhook/':
            for field in ('teacher', 'group', 'student'):
                value = request.GET.get(field, '')
                if value and (not value.isascii() or not value.isdigit() or len(value) > 18):
                    return HttpResponseBadRequest("Filtr uchun to'g'ri identifikator kiriting.")
            month = request.GET.get('month', '')
            if month:
                try:
                    datetime.strptime(month, '%Y-%m')
                except ValueError:
                    return HttpResponseBadRequest("Oy YYYY-MM shaklida bo'lishi kerak.")
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None
        name = request.resolver_match.url_name or ''
        capability = capability_for_view(name)
        if capability and not any(has_capability(request.user, code) for code in (capability if isinstance(capability, tuple) else (capability,))):
            return HttpResponseForbidden("Bu amal uchun sizga ruxsat berilmagan.")


CAPABILITIES = {
    'students.view': "O'quvchilarni ko'rish", 'students.create': "O'quvchi qabul qilish",
    'students.edit': "O'quvchini tahrirlash", 'students.assign': 'Guruhga biriktirish',
    'students.archive': "O'quvchini arxivlash/tiklash", 'groups.view': "Guruhlarni ko'rish",
    'attendance.view': "Davomatni ko'rish", 'attendance.write': 'Davomat belgilash',
    'grades.view': "Baholarni ko'rish", 'grades.write': "Baho qo'yish", 'grades.delete': "Bahoni o'chirish",
    'payments.view': "To'lovlarni ko'rish", 'payments.accept': "To'lov qabul qilish",
    'reports.view': "Hisobotlarni ko'rish", 'reports.export': 'XLSX/DOCX eksport',
    'imports.students': "O'quvchi XLSX importi", 'imports.academic': 'Davomat/baho XLSX importi',
    'leads.manage': 'Murojaatlarni boshqarish', 'messages.send': 'Telegram orqali yuborish',
    TEACHER_OWN_SALARY: "O'qituvchi o'z oyligini ko'rish",
    RECEPTIONIST_OWN_SALARY: "Retsepshen o'z oyligini ko'rish",
    'profile.edit': "O'z profilini tahrirlash",
    'students.discount': "O'quvchi chegirmasini o'zgartirish",
    'groups.create': "Guruh qo'shish", 'groups.edit': 'Guruhni tahrirlash', 'groups.delete': "Guruhni o'chirish/arxivlash",
    'courses.view': "Kurslarni ko'rish", 'courses.create': "Kurs qo'shish",
    'courses.edit': 'Kursni tahrirlash', 'courses.delete': "Kursni o'chirish",
    'teachers.view': "O'qituvchilarni ko'rish", 'teachers.create': "O'qituvchi qo'shish",
    'teachers.edit': "O'qituvchi va uning loginini tahrirlash", 'teachers.archive': "O'qituvchini arxivlash",
    'receptionists.view': "Retsepshenlarni ko'rish", 'receptionists.create': "Retsepshen qo'shish",
    'receptionists.edit': 'Retsepshen va uning loginini tahrirlash', 'receptionists.archive': 'Retsepshenni arxivlash',
    'payments.edit': "To'lovni tahrirlash", 'payments.void': "To'lovni bekor qilish", 'payments.refund': 'Pul qaytarish',
    'salary.teacher.view': "Barcha o'qituvchilar oyligini ko'rish",
    'salary.teacher.manage': "O'qituvchi oyligini hisoblash va to'langanini belgilash",
    'salary.receptionist.view': "Barcha retsepshenlar oyligi va komissiyalarini ko'rish",
    'salary.receptionist.manage': "Retsepshen oyligini hisoblash va to'langanini belgilash",
    'expenses.view': "Xarajatlarni ko'rish", 'expenses.create': "Xarajat qo'shish", 'expenses.delete': "Xarajatni o'chirish",
    'leads.archive': 'Murojaatlarni arxivlash/tiklash',
    'certificates.view': "Sertifikatlarni ko'rish", 'certificates.create': 'Sertifikat berish',
    'certificates.edit': 'Sertifikatni tahrirlash', 'certificates.delete': "Sertifikatni o'chirish",
    'certificates.settings': 'Sertifikat sozlamalarini tahrirlash',
    'assignments.view': "Biriktirish tarixini ko'rish", 'finance.reports': "Markazning umumiy moliyaviy hisobotini ko'rish",
    'finance.history': "Moliyaviy o'zgarishlar tarixini ko'rish", 'settings.manage': 'Filial va kampaniyalarni boshqarish',
    'system.view': "Tizim holatini ko'rish",
}

CAPABILITY_DEPENDENCIES = {
    'students.create': ('students.view',), 'students.edit': ('students.view',),
    'students.assign': ('students.view', 'groups.view'), 'students.archive': ('students.view',),
    'students.discount': ('students.edit',),
    'groups.create': ('groups.view',), 'groups.edit': ('groups.view',), 'groups.delete': ('groups.view',),
    'payments.view': ('students.view',), 'payments.accept': ('payments.view',),
    'payments.edit': ('payments.view',), 'payments.void': ('payments.view',), 'payments.refund': ('payments.view',),
    'grades.view': ('students.view', 'groups.view'), 'grades.write': ('grades.view',), 'grades.delete': ('grades.view',),
    'attendance.view': ('students.view', 'groups.view'), 'attendance.write': ('attendance.view',),
    'reports.export': ('reports.view',),
    'leads.archive': ('leads.manage',),
    'certificates.view': ('students.view',), 'certificates.create': ('certificates.view', 'groups.view'),
    'certificates.edit': ('certificates.view', 'groups.view'), 'certificates.delete': ('certificates.view',),
    'salary.teacher.manage': ('salary.teacher.view',), 'salary.receptionist.manage': ('salary.receptionist.view',),
}
for _prefix in ('courses', 'teachers', 'receptionists', 'expenses'):
    for _action in ('create', 'edit', 'delete', 'archive'):
        if f'{_prefix}.{_action}' in CAPABILITIES:
            CAPABILITY_DEPENDENCIES[f'{_prefix}.{_action}'] = (f'{_prefix}.view',)


def assignable_capabilities(role):
    codes = set(CAPABILITIES) if role in (TEACHER, RECEPTIONIST) else set()
    codes.discard(RECEPTIONIST_OWN_SALARY if role == TEACHER else TEACHER_OWN_SALARY)
    return codes


def expand_capabilities(codes):
    result = set(codes)
    pending = list(result)
    while pending:
        for dependency in CAPABILITY_DEPENDENCIES.get(pending.pop(), ()):
            if dependency not in result:
                result.add(dependency)
                pending.append(dependency)
    return result
DEFAULT_CAPABILITIES = {
    TEACHER: {'students.view', 'students.edit', 'students.archive', 'groups.view',
              'attendance.view', 'attendance.write', 'grades.view', 'grades.write', 'grades.delete',
              'reports.view', 'reports.export', 'imports.students', 'imports.academic', 'messages.send', 'profile.edit', 'certificates.view'},
    RECEPTIONIST: {'students.view', 'students.create', 'students.edit', 'students.assign', 'students.archive',
                   'groups.view', 'attendance.view', 'payments.view', 'payments.accept', 'reports.view',
                   'reports.export', 'imports.students', 'leads.manage', 'messages.send', 'profile.edit',
                   'certificates.view', 'certificates.create', 'certificates.edit'},
}


def has_capability(user, code):
    role = get_role(user)
    if role == ADMIN:
        return True
    if role == UNKNOWN or code not in CAPABILITIES:
        return False
    if code == TEACHER_OWN_SALARY and role != TEACHER:
        return False
    if code == RECEPTIONIST_OWN_SALARY and role != RECEPTIONIST:
        return False
    if not hasattr(user, '_crm_capabilities'):
        user._crm_capabilities = dict(user.crm_capabilities.values_list('code', 'allowed'))
    allowed = user._crm_capabilities.get(code, code in DEFAULT_CAPABILITIES.get(role, set()))
    # Preserve existing revocations until a separate certificate permission is explicitly saved.
    legacy_certificate_permissions = {'certificates.view': 'students.view', 'certificates.create': 'students.create',
                                      'certificates.edit': 'students.edit'}
    if code not in user._crm_capabilities and code in legacy_certificate_permissions:
        allowed = allowed and has_capability(user, legacy_certificate_permissions[code])
    return allowed and all(has_capability(user, dependency) for dependency in CAPABILITY_DEPENDENCIES.get(code, ()))


def visible_groups(user):
    from .models import Group
    qs = Group.objects.all()
    if not has_capability(user, 'groups.view'):
        return qs.none()
    return qs.filter(teacher=get_teacher(user)) if is_teacher(user) else qs


def visible_notifications(user):
    from .models import Notification
    qs = Notification.objects.filter(recipient=user)
    if not has_capability(user, 'leads.manage'):
        qs = qs.filter(lead__isnull=True)
    if not has_capability(user, 'payments.view'):
        qs = qs.exclude(type__in=['debt', 'payment'])
    return qs


def visible_certificates(user):
    from .models import Certificate
    from django.db.models import Q
    qs = Certificate.objects.all()
    if not has_capability(user, 'certificates.view'):
        return qs.none()
    if is_admin(user):
        return qs
    return qs.filter(Q(student__in=visible_students(user)) | Q(group__in=visible_groups(user))).distinct()


VIEW_CAPABILITIES = {
    'period_payroll': 'salary.teacher.view',
    'global_search': 'students.view',
    'student_list': 'students.view', 'student_detail': 'students.view', 'student_card_print': 'students.view',
    'api_students_search': 'students.view', 'api_group_students': 'students.view',
    'student_create': 'students.create', 'student_edit': 'students.edit',
    'student_delete': 'students.archive', 'student_restore': 'students.archive', 'student_status_update': 'students.edit',
    'enrollment_create': 'students.assign', 'enrollment_edit': 'students.assign',
    'group_list': 'groups.view', 'schedule': 'groups.view',
    'attendance_list': 'attendance.view', 'take_attendance': 'attendance.write', 'take_attendance_select': 'attendance.write',
    'grade_list': 'grades.view', 'take_grades': 'grades.write', 'take_grades_select': 'grades.write', 'grade_delete': 'grades.delete',
    'payment_list': 'payments.view', 'payment_receipt': 'payments.view', 'payment_create': 'payments.accept',
    'salary_list': (TEACHER_OWN_SALARY, 'salary.teacher.view'),
    'receptionist_salary_list': (RECEPTIONIST_OWN_SALARY, 'salary.receptionist.view'),
    'student_export': 'reports.export', 'payment_export': 'reports.export', 'lead_export': 'reports.export',
    'student_import': 'imports.students', 'student_import_template': 'imports.students',
    'report_center': 'reports.view', 'student_report': 'reports.view', 'report_export': 'reports.export',
    'report_jobs': 'reports.export', 'report_job_download': 'reports.export',
    'profile_edit': 'profile.edit', 'lead_message': 'messages.send', 'student_report_send': 'messages.send',
    'student_report_link': 'messages.send',
    'student_report_subscribe': 'messages.send',
    'certificate_list': 'certificates.view', 'certificate_detail': 'certificates.view',
    'certificate_create': 'certificates.create', 'certificate_edit': 'certificates.edit',
    'certificate_delete': 'certificates.delete', 'certificate_settings': 'certificates.settings',
    'group_create': 'groups.create', 'group_edit': 'groups.edit', 'group_delete': 'groups.delete',
    'teacher_list': 'teachers.view', 'teacher_create': 'teachers.create', 'teacher_edit': 'teachers.edit', 'teacher_delete': 'teachers.archive',
    'receptionist_list': 'receptionists.view', 'receptionist_create': 'receptionists.create',
    'receptionist_edit': 'receptionists.edit', 'receptionist_delete': 'receptionists.archive',
    'course_list': 'courses.view', 'course_create': 'courses.create', 'course_edit': 'courses.edit', 'course_delete': 'courses.delete',
    'payment_edit': 'payments.edit', 'payment_delete': 'payments.void', 'refund_create': 'payments.refund',
    'calculate_salaries': 'salary.teacher.manage', 'update_salary_status': 'salary.teacher.manage',
    'calculate_receptionist_salaries': 'salary.receptionist.manage', 'receptionist_salary_toggle': 'salary.receptionist.manage',
    'receptionist_commissions': 'salary.receptionist.view',
    'expense_list': 'expenses.view', 'expense_create': 'expenses.create', 'expense_delete': 'expenses.delete',
    'lead_delete': 'leads.archive', 'lead_restore': 'leads.archive',
    'assignment_history': 'assignments.view', 'reports': 'finance.reports', 'financial_history': 'finance.history',
    'report_settings': 'settings.manage', 'system_status': 'system.view',
}


def capability_for_view(name):
    if name.startswith('lead_') and name not in ('lead_delete', 'lead_restore', 'lead_export', 'lead_message'):
        return 'leads.manage'
    return VIEW_CAPABILITIES.get(name)
