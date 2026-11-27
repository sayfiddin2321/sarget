from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
import csv
from django.db.models import Sum, Q, Count, Avg
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.core.exceptions import PermissionDenied, ValidationError
from datetime import datetime, date, timedelta
from calendar import monthrange
from decimal import Decimal
from .models import *
from .forms import *
from .utils import get_groups_for_date, calendar_months, paginate, find_group_conflicts, report_query
from .admissions import receptionist_work
from .finance import monthly_income_totals, monthly_expense_totals
from .payments import accept_payment
from .permissions import (
    is_admin, is_receptionist, is_teacher, get_teacher, get_receptionist,
    capability_required, admin_required, not_receptionist_required, finance_required, no_teacher_required,
    visible_students, visible_groups, has_capability, visible_notifications, visible_certificates,
    RECEPTIONIST_OWN_SALARY, TEACHER_OWN_SALARY,
)


def _money_text(value):
    try:
        return f"{Decimal(value):,.0f} so'm"
    except Exception:
        return "0 so'm"


def _parse_search_date(query):
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(query, fmt).date()
        except ValueError:
            continue
    return None


def _parse_search_decimal(query):
    try:
        return Decimal(query.replace(' ', '').replace(',', ''))
    except Exception:
        return None


def _student_avatar_url(student):
    try:
        return student.photo.url if student.photo else ''
    except Exception:
        return ''


def _teacher_student_qs(user):
    """O'qituvchi uchun faqat o'z guruhidagi o'quvchilar."""
    teacher = get_teacher(user)
    if teacher:
        return Student.objects.filter(teacher=teacher)
    return Student.objects.all()


# ─── Auth ────────────────────────────────────────────────────────
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            if user.is_active:
                login(request, user)
                messages.success(request, f'Xush kelibsiz, {user.get_full_name() or user.username}!')
                target = request.GET.get('next', '')
                if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                    target = 'dashboard'
                return redirect(target)
            messages.error(request, 'Hisobingiz faollashtirilmagan. Boshliqqa murojaat qiling.')
        else:
            messages.error(request, 'Login yoki parol noto\'g\'ri!')
    return render(request, 'core/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# ─── Dashboard ───────────────────────────────────────────────────
@login_required
def dashboard(request):
    today = timezone.localdate()
    user = request.user

    if is_teacher(user):
        return _teacher_dashboard(request)
    if is_receptionist(user):
        return _receptionist_dashboard(request)

    total_students = Student.objects.filter(status='active').count()
    total_teachers = Teacher.objects.filter(is_active=True).count()
    total_groups = Group.objects.filter(is_active=True).count()
    total_receptionists = Receptionist.objects.filter(is_active=True).count()

    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    monthly_income = monthly_income_totals(month_start, month_end).get(month_start, Decimal(0))
    monthly_expenses = monthly_expense_totals(month_start, month_end).get(month_start, Decimal(0))

    net_income = monthly_income - monthly_expenses

    active_students = Student.objects.filter(status='active').select_related('teacher', 'group').prefetch_related('payments', 'tariffs')
    debtors = [s for s in active_students if s.get_debt_months() > 0]

    month_attendance_total = Attendance.objects.filter(date__year=today.year, date__month=today.month).count()
    today_attendance = Attendance.objects.filter(date=today).count()
    today_present = Attendance.objects.filter(date=today, status='present').count()
    today_late = Attendance.objects.filter(date=today, status='late').count()
    today_absent = Attendance.objects.filter(date=today, status='absent').count()
    today_excused = Attendance.objects.filter(date=today, status='excused').count()
    today_groups = get_groups_for_date(today, request.user)

    top_salary = Salary.objects.filter(
        month__year=today.year, month__month=today.month
    ).order_by('-salary_amount').select_related('teacher').first()

    recent_payments = Payment.objects.select_related('student', 'student__teacher').order_by('-paid_date')[:8]

    months_range = calendar_months(today, 6)
    start_month = months_range[0]
    payments_by_month = monthly_income_totals(start_month, month_end)
    expenses_by_month = monthly_expense_totals(start_month, month_end)
    chart_data = []
    for m in months_range:
        chart_data.append({
            'month': m.strftime('%b %Y'),
            'income': float(payments_by_month.get(m, 0)),
            'expense': float(expenses_by_month.get(m, 0)),
        })

    birthdays = Student.objects.filter(
        status='active',
        birth_date__month=today.month,
        birth_date__day=today.day
    )

    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).count()

    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_groups': total_groups,
        'total_receptionists': total_receptionists,
        'monthly_income': monthly_income,
        'monthly_expenses': monthly_expenses,
        'net_income': net_income,
        'month_attendance_total': month_attendance_total,
        'debt_count': len(debtors),
        'debtors': debtors[:5],
        'today_attendance': today_attendance,
        'today_present': today_present,
        'today_late': today_late,
        'today_absent': today_absent,
        'today_excused': today_excused,
        'today_groups': today_groups,
        'top_teacher': top_salary.teacher.name if top_salary else '—',
        'top_teacher_amount': top_salary.salary_amount if top_salary else 0,
        'recent_payments': recent_payments,
        'chart_data': chart_data,
        'birthdays': birthdays,
        'unread_notifications': unread_notifications,
    }
    return render(request, 'core/dashboard.html', context)


def _teacher_dashboard(request):
    """O'qituvchi uchun maxsus dashboard: faqat o'z guruhlari/o'quvchilari/oyligi."""
    today = timezone.localdate()
    teacher = get_teacher(request.user)
    if not teacher:
        messages.error(request, "Sizning o'qituvchi profilingiz topilmadi. Boshliqqa murojaat qiling.")
        return render(request, 'core/teacher_dashboard.html', {'teacher': None})

    my_groups = visible_groups(request.user).filter(is_active=True)
    my_students = visible_students(request.user).filter(status='active')
    today_groups = get_groups_for_date(today, request.user) if has_capability(request.user, 'groups.view') else []

    today_attendance = Attendance.objects.filter(group__teacher=teacher, date=today)
    if not has_capability(request.user, 'attendance.view'):
        today_attendance = Attendance.objects.none()
    salary_visible = has_capability(request.user, TEACHER_OWN_SALARY)
    month_salary = Salary.objects.filter(
        teacher=teacher, month__year=today.year, month__month=today.month
    ).first() if salary_visible else None
    salary_history = Salary.objects.filter(teacher=teacher).order_by('-month')[:6] if salary_visible else ()

    birthdays = my_students.filter(birth_date__month=today.month, birth_date__day=today.day)
    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).count()

    context = {
        'teacher': teacher,
        'my_groups': my_groups,
        'my_students_count': my_students.count(),
        'today_groups': today_groups,
        'today_present': today_attendance.filter(status='present').count(),
        'today_absent': today_attendance.filter(status='absent').count(),
        'today_late': today_attendance.filter(status='late').count(),
        'today_excused': today_attendance.filter(status='excused').count(),
        'month_salary': month_salary,
        'salary_history': salary_history,
        'birthdays': birthdays,
        'unread_notifications': unread_notifications,
    }
    return render(request, 'core/teacher_dashboard.html', context)


def _receptionist_dashboard(request):
    """Retsepshen uchun maxsus dashboard: summasiz, faqat operatsion ma'lumotlar."""
    today = timezone.localdate()
    rec = get_receptionist(request.user)

    my_students_today = Student.objects.filter(
        receptionist=rec, registration_date=today
    ) if rec and has_capability(request.user, 'students.view') else Student.objects.none()
    my_students_month = Student.objects.filter(
        receptionist=rec, registration_date__year=today.year, registration_date__month=today.month
    ) if rec and has_capability(request.user, 'students.view') else Student.objects.none()
    my_students_total = visible_students(request.user).filter(receptionist=rec) if rec else Student.objects.none()

    recent_students = my_students_total.order_by('-registration_date')[:8]
    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).count()

    context = {
        'receptionist': rec,
        'today_count': my_students_today.count(),
        'month_count': my_students_month.count(),
        'total_count': my_students_total.count(),
        'recent_students': recent_students,
        'unread_notifications': unread_notifications,
    }
    if has_capability(request.user, 'leads.manage'):
        context.update(receptionist_work(request.user))
    return render(request, 'core/receptionist_dashboard.html', context)


# ─── AJAX ────────────────────────────────────────────────────────
@login_required
def api_students_search(request):
    q = request.GET.get('q', '').strip()
    students = visible_students(request.user).filter(status='active').select_related('group')
    if q:
        students = students.filter(
            Q(name__icontains=q) |
            Q(phone__icontains=q) |
            Q(parent_phone__icontains=q) |
            Q(group__name__icontains=q)
        )
    data = [{
        'id': s.id,
        'text': s.search_label,
        'group': s.group.name if s.group else '',
        'phone': s.phone,
        'parent_phone': s.parent_phone,
        'photo_url': _student_avatar_url(s),
    } for s in students[:20]]
    return JsonResponse({'results': data})


@login_required
def api_group_students(request, group_id):
    if not visible_groups(request.user).filter(pk=group_id).exists():
        return JsonResponse({'error': 'Guruh topilmadi'}, status=404)
    students = visible_students(request.user).filter(enrollments__group_id=group_id, enrollments__status='active', status='active').values('id', 'name').distinct()
    return JsonResponse({'students': list(students)})


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(visible_notifications(request.user), pk=pk)
    Notification.objects.filter(pk=pk, recipient=request.user).update(is_read=True)
    unread_count = visible_notifications(request.user).filter(is_read=False).count()
    return JsonResponse({'ok': True, 'unread_count': unread_count, 'url': notification.target_url})


@login_required
@require_POST
def mark_all_notifications_read(request):
    form = NotificationFilterForm(request.POST)
    notifications = form.filter_queryset(visible_notifications(request.user))
    if not form.is_valid():
        messages.error(request, 'Bildirishnoma filtri noto‘g‘ri. Sanalarni tekshiring.')
        return redirect('notification_list')
    marked_count = notifications.filter(is_read=False).update(is_read=True)
    if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json':
        unread_count = visible_notifications(request.user).filter(is_read=False).count()
        return JsonResponse({'ok': True, 'unread_count': unread_count, 'marked_count': marked_count})
    messages.success(request, f"✓ {marked_count} ta bildirishnoma o'qilgan deb belgilandi. Tarix saqlandi.")
    return redirect(_notification_return_url(request))


def _notification_return_url(request):
    target = request.POST.get('next', '')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return reverse('notification_list')


@login_required
@require_POST
def clear_all_notifications(request):
    marked_count = visible_notifications(request.user).filter(is_read=False).update(is_read=True)
    if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json':
        return JsonResponse({'ok': True, 'unread_count': 0, 'marked_count': marked_count, 'deleted_count': 0})
    messages.success(request, "✓ Qo'ng'iroqcha tozalandi. Bildirishnomalar tarixda saqlandi.")
    return redirect(_notification_return_url(request))


@login_required
@require_POST
def notification_delete(request, pk):
    notification = get_object_or_404(visible_notifications(request.user), pk=pk)
    Notification.objects.filter(pk=notification.pk, recipient=request.user).update(is_read=True)
    if request.headers.get('Accept') == 'application/json':
        unread_count = visible_notifications(request.user).filter(is_read=False).count()
        return JsonResponse({'ok': True, 'unread_count': unread_count})
    messages.success(request, "Bildirishnoma qo'ng'iroqchadan olib tashlandi. Tarix saqlandi.")
    return redirect(_notification_return_url(request))


@login_required
@require_GET
def notification_list(request):
    history = visible_notifications(request.user).select_related('lead', 'student').order_by('-created_at', '-pk')
    params = request.GET.copy()
    if params.get('unread') == '1' and not params.get('status'):
        params['status'] = 'unread'
    form = NotificationFilterForm(params)
    qs = form.filter_queryset(history)
    counts = history.aggregate(total=Count('pk'), unread=Count('pk', filter=Q(is_read=False)))
    return render(request, 'core/notification_list.html', {
        'notifications': paginate(request, qs), 'filter_form': form,
        'history_count': counts['total'], 'history_unread_count': counts['unread'],
        'unread_only': form.is_valid() and form.cleaned_data.get('status') == 'unread',
    })


@login_required
@require_POST
def notification_open(request, pk):
    notification = get_object_or_404(visible_notifications(request.user), pk=pk)
    Notification.objects.filter(pk=pk, recipient=request.user).update(is_read=True)
    if request.POST.get('history') == '1':
        return redirect(_notification_return_url(request))
    return redirect(notification.target_url or 'notification_list')


@login_required
@require_GET
def poll_notifications(request):
    try:
        after = int(request.GET.get('after', '0'))
    except ValueError:
        return JsonResponse({'error': 'after noto‘g‘ri'}, status=400)
    if after < 0:
        return JsonResponse({'error': 'after manfiy bo‘lishi mumkin emas'}, status=400)

    notifications = list(
        visible_notifications(request.user).filter(
            is_read=False,
            pk__gt=after,
        ).order_by('pk')[:20]
    )
    unread_count = visible_notifications(request.user).filter(is_read=False).count()
    return JsonResponse({
        'notifications': [
            {
                'id': notification.pk,
                'title': notification.title,
                'message': notification.message,
                'created_at': notification.created_at.isoformat(),
                'url': notification.target_url,
            }
            for notification in notifications
        ],
        'unread_count': unread_count,
        'cursor': max([notification.pk for notification in notifications], default=after),
    })


@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    sections = []
    total_results = 0
    user = request.user
    show_finance = is_admin(user)

    if q:
        numeric_q = ''.join(ch for ch in q if ch.isdigit())
        parsed_date = _parse_search_date(q)
        parsed_decimal = _parse_search_decimal(q)
        q_lower = q.lower()

        def add_section(title, icon, qs, builder, limit=8):
            count = qs.count()
            results = [builder(obj) for obj in qs[:limit]]
            if count:
                sections.append({
                    'title': title,
                    'icon': icon,
                    'count': count,
                    'results': results,
                    'limit': limit,
                })
            return count

        student_qs = Student.objects.select_related('teacher', 'group', 'receptionist').all()
        if is_teacher(user):
            teacher = get_teacher(user)
            student_qs = student_qs.filter(teacher=teacher) if teacher else student_qs.none()
        student_filter = (
            Q(name__icontains=q) |
            Q(phone__icontains=q) |
            Q(parent_phone__icontains=q) |
            Q(notes__icontains=q) |
            Q(teacher__name__icontains=q) |
            Q(group__name__icontains=q) |
            Q(receptionist__name__icontains=q)
        )
        if numeric_q:
            student_filter |= Q(id=int(numeric_q))
        student_qs = student_qs.filter(student_filter).distinct().order_by('name')
        total_results += add_section(
            "O'quvchilar",
            'fa-user-graduate',
            student_qs,
            lambda s: {
                'title': s.name,
                'subtitle': s.phone,
                'meta': ' • '.join(filter(None, [
                    f"Guruh: {s.group.name}" if s.group else None,
                    f"O'qituvchi: {s.teacher.name}" if s.teacher else None,
                    f"Qabul: {s.receptionist.name}" if s.receptionist else None,
                ])),
                'url': reverse('student_detail', args=[s.pk]),
                'badge': s.get_status_display(),
                'badge_class': s.status,
                'avatar_url': _student_avatar_url(s),
            },
        )

        if not is_receptionist(user):
            group_qs = Group.objects.select_related('teacher').all()
            if is_teacher(user):
                teacher = get_teacher(user)
                group_qs = group_qs.filter(teacher=teacher) if teacher else group_qs.none()
            group_filter = (
                Q(name__icontains=q) |
                Q(room__icontains=q) |
                Q(days__icontains=q) |
                Q(description__icontains=q) |
                Q(teacher__name__icontains=q)
            )
            if numeric_q:
                group_filter |= Q(id=int(numeric_q))
            group_qs = group_qs.filter(group_filter).distinct().order_by('name')
            total_results += add_section(
                'Guruhlar',
                'fa-layer-group',
                group_qs,
                lambda g: {
                    'title': g.name,
                    'subtitle': g.teacher.name if g.teacher else "O'qituvchi biriktirilmagan",
                    'meta': ' • '.join(filter(None, [
                        f"Xona: {g.room}" if g.room else None,
                        f"Kunlar: {g.get_days_display_human()}",
                        f"{g.start_time.strftime('%H:%M')} - {g.end_time.strftime('%H:%M')}" if g.start_time and g.end_time else None,
                    ])),
                    'url': reverse('group_edit', args=[g.pk]) if is_admin(user) else '#',
                    'badge': 'Faol' if g.is_active else 'Nofaol',
                    'badge_class': 'active' if g.is_active else 'inactive',
                },
            )

        if is_admin(user):
            teacher_qs = Teacher.objects.all()
            teacher_filter = (
                Q(name__icontains=q) |
                Q(phone__icontains=q) |
                Q(subject__icontains=q) |
                Q(notes__icontains=q)
            )
            if numeric_q:
                teacher_filter |= Q(id=int(numeric_q))
            teacher_qs = teacher_qs.filter(teacher_filter).distinct().order_by('name')
            total_results += add_section(
                "O'qituvchilar",
                'fa-chalkboard-user',
                teacher_qs,
                lambda t: {
                    'title': t.name,
                    'subtitle': t.phone,
                    'meta': ' • '.join(filter(None, [
                        f"Fan: {t.subject}" if t.subject else None,
                        f"Faollik: {'Faol' if t.is_active else 'Nofaol'}",
                    ])),
                    'url': reverse('teacher_edit', args=[t.pk]),
                    'badge': f"{t.percent}%",
                    'badge_class': 'accent',
                },
            )

            receptionist_qs = Receptionist.objects.all()
            receptionist_filter = (
                Q(name__icontains=q) |
                Q(phone__icontains=q) |
                Q(notes__icontains=q)
            )
            if numeric_q:
                receptionist_filter |= Q(id=int(numeric_q))
            receptionist_qs = receptionist_qs.filter(receptionist_filter).distinct().order_by('name')
            total_results += add_section(
                'Retsepshenlar',
                'fa-headset',
                receptionist_qs,
                lambda r: {
                    'title': r.name,
                    'subtitle': r.phone,
                    'meta': f"Komissiya: {r.commission_percent}%",
                    'url': reverse('receptionist_edit', args=[r.pk]),
                    'badge': 'Faol' if r.is_active else 'Nofaol',
                    'badge_class': 'active' if r.is_active else 'inactive',
                },
            )

        if show_finance:
            payment_qs = Payment.objects.select_related('student', 'student__group').all()
            payment_filter = (
                Q(student__name__icontains=q) |
                Q(student__phone__icontains=q) |
                Q(student__parent_phone__icontains=q) |
                Q(student__group__name__icontains=q) |
                Q(comment__icontains=q) |
                Q(payment_type__icontains=q)
            )
            if parsed_decimal is not None:
                payment_filter |= Q(amount=parsed_decimal)
            if parsed_date is not None:
                payment_filter |= Q(month=parsed_date)
            payment_qs = payment_qs.filter(payment_filter).distinct().order_by('-paid_date')
            total_results += add_section(
                "To'lovlar",
                'fa-money-bill-wave',
                payment_qs,
                lambda p: {
                    'title': p.student.name,
                    'subtitle': _money_text(p.amount),
                    'meta': ' • '.join(filter(None, [
                        p.month.strftime('%B %Y') if p.month else None,
                        p.student.group.name if p.student.group else None,
                        p.get_payment_type_display(),
                    ])),
                    'url': reverse('payment_edit', args=[p.pk]),
                    'badge': p.get_payment_type_display(),
                    'badge_class': p.payment_type,
                    'avatar_url': _student_avatar_url(p.student),
                },
            )

        attendance_qs = Attendance.objects.select_related('student', 'group').all()
        if is_teacher(user):
            teacher = get_teacher(user)
            attendance_qs = attendance_qs.filter(group__teacher=teacher) if teacher else attendance_qs.none()
        attendance_filter = (
            Q(student__name__icontains=q) |
            Q(student__phone__icontains=q) |
            Q(student__parent_phone__icontains=q) |
            Q(group__name__icontains=q) |
            Q(note__icontains=q) |
            Q(status__icontains=q)
        )
        if numeric_q:
            attendance_filter |= Q(student__phone__icontains=numeric_q)
        if parsed_date is not None:
            attendance_filter |= Q(date=parsed_date)

        status_map = {
            'keldi': 'present',
            'kelmadi': 'absent',
            'kechikdi': 'late',
            'sababli': 'excused',
            'present': 'present',
            'absent': 'absent',
            'late': 'late',
            'excused': 'excused',
        }
        if q_lower in status_map:
            attendance_filter |= Q(status=status_map[q_lower])

        attendance_qs = attendance_qs.filter(attendance_filter).distinct().order_by('-date', 'student__name')
        total_results += add_section(
            'Davomat',
            'fa-calendar-check',
            attendance_qs,
            lambda a: {
                'title': a.student.name,
                'subtitle': a.group.name,
                'meta': ' • '.join(filter(None, [
                    a.date.strftime('%d.%m.%Y'),
                    a.note if a.note else None,
                ])),
                'url': f"{reverse('attendance_list')}?date={a.date.isoformat()}&group={a.group_id}",
                'badge': a.get_status_display(),
                'badge_class': a.status,
                'avatar_url': _student_avatar_url(a.student),
            },
        )

    return render(request, 'core/search.html', {
        'q': q,
        'sections': sections,
        'total_results': total_results,
        'search_date': _parse_search_date(q) if q else None,
    })


# ─── Students ────────────────────────────────────────────────────
@login_required
def student_list(request):
    user = request.user
    base_students = visible_students(user).select_related('teacher', 'group', 'receptionist').prefetch_related('payments', 'tariffs', 'enrollments__group', 'payments__refunds')

    # Pre-calculate tab counts before applying user filters
    count_all = base_students.count()
    count_active = base_students.filter(status='active').count()
    count_graduated = base_students.filter(status='graduated').count()
    count_inactive = base_students.filter(status='inactive').count()
    count_pending = base_students.filter(status='pending').count()

    students = base_students

    q = request.GET.get('q', '').strip()
    teacher_id = request.GET.get('teacher', '')
    group_id = request.GET.get('group', '')
    status_filter = request.GET.get('status', '')
    source_filter = request.GET.get('source', '')
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if q:
        students = students.filter(
            Q(name__icontains=q) |
            Q(phone__icontains=q) |
            Q(parent_phone__icontains=q) |
            Q(group__name__icontains=q) |
            Q(teacher__name__icontains=q)
        )
    if teacher_id:
        students = students.filter(teacher_id=teacher_id)
    if group_id:
        students = students.filter(group_id=group_id)
    if status_filter:
        students = students.filter(status=status_filter)
    if source_filter:
        students = students.filter(source=source_filter)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            students = students.filter(registration_date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            students = students.filter(registration_date__lte=d_to)
        except ValueError:
            pass

    context = {
        'students': students,
        'teachers': Teacher.objects.filter(is_active=True).order_by('name'),
        'groups': Group.objects.filter(is_active=True).order_by('name'),
        'selected_teacher': teacher_id,
        'selected_group': group_id,
        'selected_status': status_filter,
        'selected_source': source_filter,
        'selected_date_from': date_from,
        'selected_date_to': date_to,
        'q': q,
        'status_choices': Student.STATUS_CHOICES,
        'source_choices': Student.SOURCE_CHOICES,
        'count_all': count_all,
        'count_active': count_active,
        'count_graduated': count_graduated,
        'count_inactive': count_inactive,
        'count_pending': count_pending,
    }
    context['students'] = paginate(request, students.order_by('name', 'pk'))
    context['report_query'] = report_query(request, 'students', {'source': 'student_source', 'date_from': 'registered_from', 'date_to': 'registered_to'})
    return render(request, 'core/student_list.html', context)


@login_required
@require_POST
def student_status_update(request, pk):
    user = request.user
    if not has_capability(user, 'students.edit'):
        return HttpResponseForbidden("Ruxsat yo'q")
    student = get_object_or_404(visible_students(request.user), pk=pk)
    new_status = request.POST.get('status', '').strip()
    if new_status in dict(Student.STATUS_CHOICES):
        student.status = new_status
        student.save(update_fields=['status'])
        messages.success(request, f"✓ {student.name} holati \"{student.get_status_display()}\" ga o'zgartirildi.")
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = reverse('student_detail', args=[student.pk])
    return redirect(next_url)


@login_required
def student_export(request):
    user = request.user
    students = visible_students(user).select_related('teacher', 'group', 'receptionist').prefetch_related('payments', 'tariffs', 'enrollments__group', 'payments__refunds')

    q = request.GET.get('q', '').strip()
    teacher_id = request.GET.get('teacher', '')
    group_id = request.GET.get('group', '')
    status_filter = request.GET.get('status', '')
    source_filter = request.GET.get('source', '')
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if q:
        students = students.filter(
            Q(name__icontains=q) | Q(phone__icontains=q) |
            Q(parent_phone__icontains=q) | Q(group__name__icontains=q) |
            Q(teacher__name__icontains=q)
        )
    if teacher_id:
        students = students.filter(teacher_id=teacher_id)
    if group_id:
        students = students.filter(group_id=group_id)
    if status_filter:
        students = students.filter(status=status_filter)
    if source_filter:
        students = students.filter(source=source_filter)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            students = students.filter(registration_date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            students = students.filter(registration_date__lte=d_to)
        except ValueError:
            pass

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="oquvchilar_{timezone.localdate().strftime("%Y%m%d")}.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow([
        'ID',
        'F.I.Sh (Ism)',
        'Telefon',
        'Ota-ona telefoni',
        'Tug\'ilgan sana',
        'Holat',
        'Guruh',
        'O\'qituvchi',
        'Qabul qilgan',
        'Ro\'yxat sanasi',
        'Chegirma (%)',
        'Jami to\'langan (so\'m)',
        'Qarz (so\'m)',
        'Qarz oylari',
        'Manba',
        'Izoh',
    ])

    def safe_cell(val):
        val = str(val if val is not None else '')
        if val.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
            return "'" + val
        return val

    for s in students.order_by('name', 'pk').iterator(chunk_size=200):
        debt = s.get_debt_amount()
        months = s.get_debt_months()
        total_paid = s.get_total_paid()
        writer.writerow([
            safe_cell(s.pk),
            safe_cell(s.name),
            safe_cell(s.phone),
            safe_cell(s.parent_phone),
            safe_cell(s.birth_date.strftime('%d.%m.%Y') if s.birth_date else ''),
            safe_cell(s.get_status_display()),
            safe_cell(s.group.name if s.group else ''),
            safe_cell(s.teacher.name if s.teacher else ''),
            safe_cell(s.receptionist.name if s.receptionist else ''),
            safe_cell(s.registration_date.strftime('%d.%m.%Y') if s.registration_date else ''),
            safe_cell(s.discount_percent or 0),
            safe_cell(f"{total_paid:,.0f}"),
            safe_cell(f"{debt:,.0f}" if debt else 0),
            safe_cell(f"{months} oy" if months else "Yo'q"),
            safe_cell(s.get_source_display()),
            safe_cell(s.notes),
        ])

    return response


@login_required
def student_import_template(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="oquvchilar_shablon.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow([
        'Ism',
        'Telefon',
        'Ota-ona telefoni',
        'Holat',
        'Guruh',
        'O\'qituvchi',
        'Ro\'yxat sanasi',
        'Tug\'ilgan sana',
        'Chegirma',
        'Izoh',
    ])
    writer.writerow([
        'Ali Valiyev',
        '+998901234567',
        '+998912345678',
        'O\'qiyapti',
        'Python Backend',
        'Aziz Rahimov',
        '2026-10-01',
        '2005-04-12',
        '0',
        'Faol o\'quvchi',
    ])
    writer.writerow([
        'Madina Karimova',
        '+998935554433',
        '+998946665544',
        'Bitirgan',
        'Frontend React',
        'Bobur Usmonov',
        '2024-03-10',
        '2004-08-20',
        '10',
        'Kursni muvaffaqiyatli tamomlagan (eski o\'quvchi)',
    ])
    writer.writerow([
        'Sardor Toshpo\'latov',
        '+998971112233',
        '+998909998877',
        'Kelmay qo\'ygan',
        '',
        '',
        '2025-01-15',
        '2006-11-05',
        '0',
        'Darslarni to\'xtatgan',
    ])
    return response


@login_required
def student_import(request):
    user = request.user
    if not (is_admin(user) or is_receptionist(user)):
        return HttpResponseForbidden("Ruxsat yo'q")

    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, "Iltimos, CSV faylni tanlang.")
            return render(request, 'core/student_import.html')

        if not csv_file.name.endswith(('.csv', '.txt')):
            messages.error(request, "Faqat .csv formatidagi fayllar qabul qilinadi.")
            return render(request, 'core/student_import.html')

        try:
            raw_bytes = csv_file.read()
            text = None
            for encoding in ('utf-8-sig', 'utf-8', 'cp1251', 'windows-1251', 'latin1'):
                try:
                    text = raw_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                messages.error(request, "Fayl kodirovkasini aniqlab bo'lmadi. UTF-8 formatida saqlang.")
                return render(request, 'core/student_import.html')

            import io
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            if not rows:
                messages.error(request, "Fayl bo'sh.")
                return render(request, 'core/student_import.html')

            headers = [h.strip().lower() for h in rows[0]]

            def find_col(candidates):
                for c in candidates:
                    for idx, h in enumerate(headers):
                        if c in h:
                            return idx
                return None

            name_idx = find_col(['ism', 'name', 'f.i.sh', 'fish', 'familiya', 'talaba', "o'quvchi"])
            phone_idx = find_col(['telefon', 'phone', 'tel', 'aloqa'])
            parent_phone_idx = find_col(['ota-ona', 'parent', 'ota ona', 'onasi', 'otasi'])
            birth_idx = find_col(['tug\'ilgan', 'birth', 'tugilgan'])
            reg_date_idx = find_col(['ro\'yxat', 'sana', 'date', 'qo\'shilgan', 'registration'])
            status_idx = find_col(['holat', 'status'])
            group_idx = find_col(['guruh', 'group'])
            teacher_idx = find_col(['o\'qituvchi', 'teacher', 'ustoz'])
            discount_idx = find_col(['chegirma', 'discount'])
            notes_idx = find_col(['izoh', 'note', 'comment'])

            if name_idx is None:
                messages.error(request, "Faylda 'Ism' yoki 'F.I.Sh' ustuni topilmadi.")
                return render(request, 'core/student_import.html')

            status_map = {
                'active': 'active', 'aktiv': 'active', 'faol': 'active', "o'qiyapti": 'active', "o‘qiyapti": 'active',
                'inactive': 'inactive', 'arxiv': 'inactive', "kelmay qo'ygan": 'inactive', "kelmay qoygan": 'inactive', "to'xtatgan": 'inactive',
                'graduated': 'graduated', 'bitirgan': 'graduated', 'tamomlagan': 'graduated',
                'pending': 'pending', 'kutilmoqda': 'pending', 'sinov': 'pending', 'kutmoqda': 'pending',
            }

            def parse_import_date(raw_value, field_name):
                for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%Y.%m.%d'):
                    try:
                        return datetime.strptime(raw_value, fmt).date()
                    except ValueError:
                        continue
                raise ValueError(f"{field_name} noto'g'ri: {raw_value}")

            created_count = 0
            updated_count = 0
            error_rows = []
            default_rec = get_receptionist(user) if is_receptionist(user) else None

            with transaction.atomic():
                for line_no, row in enumerate(rows[1:], start=2):
                    if not any(row):
                        continue
                    try:
                        name = row[name_idx].strip() if len(row) > name_idx else ''
                        if not name:
                            continue

                        phone = row[phone_idx].strip() if (phone_idx is not None and len(row) > phone_idx) else ''
                        parent_phone = row[parent_phone_idx].strip() if (parent_phone_idx is not None and len(row) > parent_phone_idx) else ''

                        status_val = 'active'
                        if status_idx is not None and len(row) > status_idx:
                            raw_s = row[status_idx].strip().lower()
                            if raw_s:
                                status_val = status_map.get(raw_s)
                                if status_val is None:
                                    raise ValueError(f"O'quvchi holati noto'g'ri: {raw_s}")

                        reg_date = timezone.localdate()
                        if reg_date_idx is not None and len(row) > reg_date_idx:
                            raw_d = row[reg_date_idx].strip()
                            if raw_d:
                                reg_date = parse_import_date(raw_d, "Ro'yxat sanasi")

                        birth_date = None
                        if birth_idx is not None and len(row) > birth_idx:
                            raw_b = row[birth_idx].strip()
                            if raw_b:
                                birth_date = parse_import_date(raw_b, "Tug'ilgan sana")

                        group_obj = None
                        if group_idx is not None and len(row) > group_idx:
                            g_name = row[group_idx].strip()
                            if g_name:
                                group_obj = Group.objects.filter(name__iexact=g_name).first()

                        teacher_obj = group_obj.teacher if (group_obj and group_obj.teacher) else None
                        if not teacher_obj and teacher_idx is not None and len(row) > teacher_idx:
                            t_name = row[teacher_idx].strip()
                            if t_name:
                                teacher_obj = Teacher.objects.filter(name__icontains=t_name).first()

                        discount = 0
                        if discount_idx is not None and len(row) > discount_idx:
                            raw_discount = row[discount_idx].strip()
                            if raw_discount.endswith('%'):
                                raw_discount = raw_discount[:-1].strip()
                            if raw_discount:
                                discount = int(raw_discount)
                                if not 0 <= discount <= 100:
                                    raise ValueError("Chegirma 0-100 oralig'ida bo'lishi kerak")

                        notes = row[notes_idx].strip() if (notes_idx is not None and len(row) > notes_idx) else ''

                        student = None
                        if phone and len(''.join(filter(str.isdigit, phone))) >= 7:
                            student = Student.objects.filter(phone=phone).first()

                        if student:
                            student.name = name
                            if parent_phone:
                                student.parent_phone = parent_phone
                            student.status = status_val
                            if group_obj:
                                student.group = group_obj
                            if teacher_obj:
                                student.teacher = teacher_obj
                            if birth_date:
                                student.birth_date = birth_date
                            if notes:
                                student.notes = (student.notes + ' ' + notes).strip()
                            student.save()
                            updated_count += 1
                        else:
                            Student.objects.create(
                                name=name,
                                phone=phone,
                                parent_phone=parent_phone,
                                status=status_val,
                                registration_date=reg_date,
                                birth_date=birth_date,
                                group=group_obj,
                                teacher=teacher_obj,
                                receptionist=default_rec,
                                created_by=user,
                                discount_percent=discount,
                                notes=notes,
                            )
                            created_count += 1
                    except Exception as ex:
                        error_rows.append(f"{line_no}-qator: {str(ex)}")

            if created_count or updated_count:
                msg = f"✓ Import muvaffaqiyatli: {created_count} ta yangi o'quvchi qo'shildi"
                if updated_count:
                    msg += f", {updated_count} ta o'quvchi ma'lumotlari yangilandi."
                messages.success(request, msg)
            if error_rows:
                messages.warning(request, f"Ayrim qatorlarda xatolik: {', '.join(error_rows[:5])}")
            return redirect('student_list')
        except Exception as e:
            messages.error(request, f"Faylni o'qishda xatolik yuz berdi: {str(e)}")
            return render(request, 'core/student_import.html')

    return render(request, 'core/student_import.html')


def _configure_student_permissions(form, user):
    can_assign = has_capability(user, 'students.assign')
    for field in ('teacher', 'group'):
        form.fields[field].disabled = not can_assign
    form.fields['discount_percent'].disabled = not has_capability(user, 'students.discount')
    if is_teacher(user):
        teacher = get_teacher(user)
        if not form.instance.pk:
            form.instance.teacher = teacher
            form.initial['teacher'] = teacher.pk
        if can_assign:
            form.fields['group'].queryset = visible_groups(user).filter(is_active=True)
            form.fields['teacher'].queryset = Teacher.objects.filter(pk=teacher.pk)
            form.initial['teacher'] = teacher.pk
        form.fields['teacher'].disabled = True
        form.fields['receptionist'].disabled = True
        for field in ('branch', 'payment_due_day', 'registration_date', 'status'):
            form.fields[field].disabled = not can_assign


def _configure_group_permissions(form, user):
    if is_teacher(user):
        teacher = get_teacher(user)
        form.fields['teacher'].queryset = Teacher.objects.filter(pk=teacher.pk)
        form.initial['teacher'] = teacher.pk
        form.fields['teacher'].disabled = True


@login_required
def student_create(request):
    user = request.user

    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES)
        _configure_student_permissions(form, user)
        if form.is_valid():
            student = form.save(commit=False)
            student.created_by = user
            if is_receptionist(user):
                student.receptionist = get_receptionist(user)
            if not student.group_id:
                student.status = 'pending'
            student.save()
            AssignmentHistory.objects.create(
                student=student,
                teacher=student.teacher,
                group=student.group,
                assigned_date=timezone.localdate(),
                changed_by=request.user,
                note="Yangi o'quvchi"
            )
            messages.success(request, f'✓ {student.name} muvaffaqiyatli qo\'shildi')
            return redirect('student_list')
    else:
        form = StudentForm()
        _configure_student_permissions(form, user)
    return render(request, 'core/student_form.html', {'form': form, 'title': "O'quvchi qo'shish", 'action': 'create'})


@login_required
def student_edit(request, pk):
    user = request.user
    student = get_object_or_404(visible_students(request.user), pk=pk)

    old_teacher = student.teacher
    old_group = student.group
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES, instance=student)
        _configure_student_permissions(form, user)
        if form.is_valid():
            student = form.save()
            if old_teacher != student.teacher or old_group != student.group:
                AssignmentHistory.objects.create(
                    student=student,
                    teacher=student.teacher,
                    group=student.group,
                    assigned_date=timezone.localdate(),
                    changed_by=request.user,
                    note="Guruh/o'qituvchi o'zgartirildi"
                )
            messages.success(request, f'✓ {student.name} yangilandi')
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)
        _configure_student_permissions(form, user)
    return render(request, 'core/student_form.html', {'form': form, 'title': "O'quvchi tahrirlash", 'student': student, 'action': 'edit'})


@login_required
def student_detail(request, pk):
    user = request.user
    student = get_object_or_404(visible_students(user).select_related('teacher', 'group', 'receptionist'), pk=pk)

    if is_teacher(user):
        teacher = get_teacher(user)
        if not teacher or not visible_students(user).filter(pk=student.pk).exists():
            messages.error(request, "Siz faqat o'z guruhingizdagi o'quvchilarni ko'ra olasiz.")
            return redirect('student_list')
    can_view_finance = has_capability(user, 'payments.view')
    payments = student.payments.order_by('-month') if can_view_finance else Payment.objects.none()
    attendance_qs = student.attendances.filter(group__in=visible_groups(user)) if has_capability(user, 'attendance.view') else Attendance.objects.none()
    grade_qs = student.grades.filter(group__in=visible_groups(user)) if has_capability(user, 'grades.view') else Grade.objects.none()
    attendances = attendance_qs.order_by('-date')[:30]
    grades = grade_qs.select_related('group', 'graded_by').order_by('-date')[:30]
    avg_score = grade_qs.aggregate(Avg('score'))['score__avg']
    history = student.assignment_history.select_related('teacher', 'group', 'changed_by').all()
    context = {
        'student': student,
        'visible_enrollments': student.enrollments.filter(group__in=visible_groups(user)).select_related('group__course'),
        'payments': payments,
        'attendances': attendances,
        'certificates': visible_certificates(user).filter(student=student),
        'grades': grades,
        'avg_score': round(avg_score, 1) if avg_score else None,
        'grades_count': grade_qs.count(),
        'history': history,
        'can_view_finance': can_view_finance,
        'total_paid': student.get_total_paid() if can_view_finance else None,
        'debt_amount': student.get_debt_amount() if can_view_finance else None,
        'debt_months': student.get_debt_months() if can_view_finance else None,
        'debt_breakdown': student.get_debt_breakdown() if can_view_finance else [],
        'attendance_total': attendance_qs.count(),
        'attendance_present': attendance_qs.filter(status='present').count(),
        'attendance_late': attendance_qs.filter(status='late').count(),
        'attendance_absent': attendance_qs.filter(status='absent').count(),
        'attendance_excused': attendance_qs.filter(status='excused').count(),
    }
    if has_capability(user, 'messages.send'):
        from .messaging import student_recipients
        context['telegram_recipients'] = student_recipients(student)
        context['telegram_deliveries'] = TelegramDelivery.objects.filter(
            student=student,
            owner=user,
            recipient__in=[row['key'] for row in context['telegram_recipients']],
            report_job__isnull=True,
        ).order_by('-created_at')[:5]
    return render(request, 'core/student_detail.html', context)


@login_required
def student_delete(request, pk):
    student = get_object_or_404(visible_students(request.user), pk=pk)
    if request.method == 'POST':
        name = student.name
        student.status = 'inactive'
        student.save(update_fields=['status'])
        messages.success(request, f'✓ {name} arxivlandi. To\'lov tarixi saqlandi.')
        return redirect('student_list')
    return render(request, 'core/student_confirm_delete.html', {'student': student})


@login_required
def student_remove(request, pk):
    from .models import ReportSubscription, GuardianBinding, TelegramDelivery, TelegramBinding, TelegramLinkToken
    if not request.user.is_superuser:
        raise PermissionDenied("Faqat superadmin o'quvchini o'chira oladi.")
    student = get_object_or_404(Student.objects, pk=pk)
    if request.method == 'POST':
        from django.db import transaction
        with transaction.atomic():
            student = Student.objects.select_for_update().get(pk=pk)
            student.status = 'inactive'
            student.telegram_chat_id = None
            student.save(update_fields=['status', 'telegram_chat_id'])
            ReportSubscription.objects.filter(student=student).update(enabled=False)
            GuardianBinding.objects.filter(student=student).update(reports_enabled=False)
            TelegramBinding.objects.filter(role='student', target_id=pk).delete()
            TelegramLinkToken.objects.filter(role__in=['student', 'guardian'], target_id=pk, used_at__isnull=True).update(used_at=timezone.now())
            TelegramDelivery.objects.filter(student=student, status__in=['pending', 'retry']).update(status='cancelled', error='Student removed')
            Student.objects.filter(pk=pk).update(deleted_at=timezone.now())
        messages.success(request, "O'quvchi o'chirildi. Moliyaviy tarix saqlandi.")
        return redirect('student_list')
    return render(request, 'core/student_remove.html', {'student': student})


# ─── Teachers (faqat Boshliq) ──────────────────────────────────────
@login_required
@capability_required('teachers.view')
def teacher_list(request):
    teachers = Teacher.objects.all().annotate(student_count=Count('students', filter=Q(students__status='active')))
    return render(request, 'core/teacher_list.html', {'teachers': teachers})


@login_required
@capability_required('teachers.create')
def teacher_create(request):
    form = TeacherForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        t = form.save()
        messages.success(request, f'✓ {t.name} qo\'shildi')
        return redirect('teacher_list')
    return render(request, 'core/teacher_form.html', {'form': form, 'title': "O'qituvchi qo'shish"})


@login_required
@capability_required('teachers.edit')
def teacher_edit(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if not is_admin(request.user) and teacher.user_id and teacher.user.is_superuser:
        raise PermissionDenied('Boshliq hisobini tahrirlash mumkin emas.')
    form = TeacherForm(request.POST or None, request.FILES or None, instance=teacher)
    if form.is_valid():
        form.save()
        messages.success(request, f'✓ {teacher.name} yangilandi')
        return redirect('teacher_list')
    return render(request, 'core/teacher_form.html', {'form': form, 'title': "O'qituvchi tahrirlash", 'teacher': teacher})


@login_required
@capability_required('teachers.archive')
def teacher_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if not is_admin(request.user) and teacher.user_id and teacher.user.is_superuser:
        raise PermissionDenied('Boshliq hisobini arxivlash mumkin emas.')
    if request.method == 'POST':
        name = teacher.name
        teacher.is_active = False
        teacher.save(update_fields=['is_active'])
        if teacher.user_id:
            teacher.user.is_active = False
            teacher.user.save(update_fields=['is_active'])
        messages.success(request, f'✓ {name} arxivlandi')
        return redirect('teacher_list')
    return render(request, 'core/teacher_confirm_delete.html', {'teacher': teacher})


# ─── Receptionists (faqat Boshliq) ─────────────────────────────────
@login_required
@capability_required('receptionists.view')
def receptionist_list(request):
    receptionists = Receptionist.objects.all().annotate(
        student_count=Count('registered_students', filter=Q(registered_students__status='active'))
    )
    return render(request, 'core/receptionist_list.html', {'receptionists': receptionists})


@login_required
@capability_required('receptionists.create')
def receptionist_create(request):
    form = ReceptionistForm(request.POST or None)
    if form.is_valid():
        r = form.save()
        messages.success(request, f'✓ {r.name} qo\'shildi')
        return redirect('receptionist_list')
    return render(request, 'core/receptionist_form.html', {'form': form, 'title': "Retsepshen qo'shish"})


@login_required
@capability_required('receptionists.edit')
def receptionist_edit(request, pk):
    rec = get_object_or_404(Receptionist, pk=pk)
    if not is_admin(request.user) and rec.user_id and rec.user.is_superuser:
        raise PermissionDenied('Boshliq hisobini tahrirlash mumkin emas.')
    form = ReceptionistForm(request.POST or None, instance=rec)
    if form.is_valid():
        form.save()
        messages.success(request, f'✓ {rec.name} yangilandi')
        return redirect('receptionist_list')
    return render(request, 'core/receptionist_form.html', {'form': form, 'title': "Retsepshen tahrirlash", 'receptionist': rec})


@login_required
@capability_required('receptionists.archive')
def receptionist_delete(request, pk):
    rec = get_object_or_404(Receptionist, pk=pk)
    if not is_admin(request.user) and rec.user_id and rec.user.is_superuser:
        raise PermissionDenied('Boshliq hisobini arxivlash mumkin emas.')
    if request.method == 'POST':
        name = rec.name
        rec.is_active = False
        rec.save(update_fields=['is_active'])
        if rec.user_id:
            rec.user.is_active = False
            rec.user.save(update_fields=['is_active'])
        messages.success(request, f'✓ {name} arxivlandi')
        return redirect('receptionist_list')
    return render(request, 'core/receptionist_confirm_delete.html', {'receptionist': rec})


@login_required
def receptionist_salary_list(request):
    user = request.user
    can_view_all = has_capability(user, 'salary.receptionist.view')
    own_salary = not can_view_all
    if can_view_all:
        salaries = ReceptionistSalary.objects.select_related('receptionist').all()
    elif is_receptionist(user) and has_capability(user, RECEPTIONIST_OWN_SALARY):
        receptionist = get_receptionist(user)
        if not receptionist:
            raise PermissionDenied('Retsepshen profili topilmadi.')
        salaries = ReceptionistSalary.objects.select_related('receptionist').filter(receptionist=receptionist)
    else:
        raise PermissionDenied('Retsepshen oyligini ko‘rish huquqi yo‘q.')
    month = request.GET.get('month', '')
    if month and '-' in month:
        y, m = month.split('-')[:2]
        salaries = salaries.filter(month__year=y, month__month=m)
    return render(request, 'core/receptionist_salary_list.html', {
        'salaries': salaries, 'selected_month': month, 'own_salary': own_salary,
        'can_manage_salaries': has_capability(user, 'salary.receptionist.manage'),
    })


@login_required
@capability_required('salary.receptionist.manage')
@transaction.atomic
def calculate_receptionist_salaries(request):
    from .payroll import receptionist_total
    if request.method == 'POST':
        month_str = request.POST.get('month', '')
        try:
            base_salary = ReceptionistSalary._meta.get_field('base_salary').clean(
                request.POST.get('base_salary', '0') or '0', None,
            )
            if not base_salary.is_finite() or base_salary < 0:
                raise ValueError
            y, m = map(int, month_str.split('-')[:2])
            month_date = date(y, m, 1)
        except (ValueError, AttributeError, ArithmeticError, ValidationError):
            messages.error(request, 'Oy noto\'g\'ri kiritildi')
            return redirect('receptionist_salary_list')

        count = 0
        for rec in Receptionist.objects.filter(is_active=True):
            salary, _ = ReceptionistSalary.objects.select_for_update().get_or_create(receptionist=rec, month=month_date)
            if salary.is_paid:
                continue
            total_commission = receptionist_total(rec.pk, month_date)

            total_salary = base_salary + total_commission
            salary.base_salary = base_salary
            salary.total_commission = total_commission
            salary.total_salary = total_salary
            salary.save(update_fields=['base_salary', 'total_commission', 'total_salary'])
            count += 1
        messages.success(request, f'✓ {count} ta retsepshen oyligi hisoblandi')
        return redirect('receptionist_salary_list')

    return render(request, 'core/calculate_receptionist_salary.html', {'current_month': timezone.localdate().replace(day=1)})


@require_POST
@login_required
@capability_required('salary.receptionist.manage')
@transaction.atomic
def receptionist_salary_toggle(request, pk):
    salary = get_object_or_404(ReceptionistSalary.objects.select_for_update(), pk=pk)
    salary.is_paid = not salary.is_paid
    salary.save(update_fields=['is_paid'])
    status = "to'landi" if salary.is_paid else "to'lanmadi"
    messages.success(request, f'✓ {salary.receptionist.name} oyligi {status}')
    return redirect('receptionist_salary_list')


@login_required
@capability_required('salary.receptionist.view')
def receptionist_commissions(request, pk):
    rec = get_object_or_404(Receptionist, pk=pk)
    month = request.GET.get('month', '')
    commissions = ReceptionistCommission.objects.filter(receptionist=rec).select_related('student', 'payment')
    if month and '-' in month:
        y, m = month.split('-')[:2]
        commissions = commissions.filter(month__year=y, month__month=m)
    total = commissions.aggregate(Sum('commission_amount'))['commission_amount__sum'] or 0
    return render(request, 'core/receptionist_commissions.html', {
        'receptionist': rec,
        'commissions': commissions,
        'total': total,
        'selected_month': month,
    })


# ─── Groups (faqat Boshliq) ──────────────────────────────────────
@login_required
@capability_required('courses.view')
def course_list(request):
    return render(request, 'core/course_list.html', {
        'courses': Course.objects.all(),
    })


@login_required
@capability_required('courses.create')
def course_create(request):
    form = CourseForm(request.POST or None)
    if form.is_valid():
        course = form.save()
        messages.success(request, f'✓ {course.name} kursi qo‘shildi')
        return redirect('course_list')
    return render(request, 'core/course_form.html', {
        'form': form,
        'title': 'Kurs qo‘shish',
    })


@login_required
@capability_required('courses.edit')
def course_edit(request, pk):
    course = get_object_or_404(Course, pk=pk)
    form = CourseForm(request.POST or None, instance=course)
    if form.is_valid():
        form.save()
        messages.success(request, f'✓ {course.name} kursi yangilandi')
        return redirect('course_list')
    return render(request, 'core/course_form.html', {
        'form': form,
        'title': 'Kursni tahrirlash',
        'course': course,
    })


@login_required
@capability_required('courses.delete')
@require_POST
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    try:
        course.delete()
    except ProtectedError:
        messages.error(request, "Bu kursga guruhlar yoki to'lovlar bog'langan. Kursni tahrirlab, faol holatini o'chiring.")
        return redirect('course_list')
    messages.success(request, f'✓ {course.name} kursi o‘chirildi')
    return redirect('course_list')


# ─── Groups (faqat Boshliq) ──────────────────────────────────────
@login_required
def group_list(request):
    groups = visible_groups(request.user).select_related('teacher', 'branch', 'course').annotate(
        student_count=Count('enrollments__student', filter=Q(enrollments__status='active'), distinct=True)
    )
    return render(request, 'core/group_list.html', {'groups': groups})


@login_required
@capability_required('groups.create')
def group_create(request):
    form = GroupForm(request.POST or None)
    _configure_group_permissions(form, request.user)
    if form.is_valid():
        g = form.save()
        messages.success(request, f'✓ {g.name} qo\'shildi')
        if form.conflict_warnings:
            messages.warning(request, "Jadvalda to'qnashuv: " + '; '.join(form.conflict_warnings))
        return redirect('group_list')
    return render(request, 'core/group_form.html', {'form': form, 'title': "Guruh qo'shish"})


@login_required
@capability_required('groups.edit')
def group_edit(request, pk):
    group = get_object_or_404(visible_groups(request.user), pk=pk)
    form = GroupForm(request.POST or None, instance=group)
    _configure_group_permissions(form, request.user)
    if form.is_valid():
        form.save()
        messages.success(request, f'✓ {group.name} yangilandi')
        if form.conflict_warnings:
            messages.warning(request, "Jadvalda to'qnashuv: " + '; '.join(form.conflict_warnings))
        return redirect('group_list')
    return render(request, 'core/group_form.html', {'form': form, 'title': "Guruh tahrirlash", 'group': group})


@login_required
@capability_required('groups.delete')
def group_delete(request, pk):
    group = get_object_or_404(visible_groups(request.user), pk=pk)
    if request.method == 'POST':
        name = group.name
        if group.enrollments.exists():
            group.is_active = False
            group.save(update_fields=['is_active'])
            for enrollment in group.enrollments.filter(status__in=['active', 'planned', 'frozen']):
                enrollment.status, enrollment.ends_on = 'completed', timezone.localdate()
                enrollment.save(update_fields=['status', 'ends_on'])
            for student in group.student_set.select_related('group'):
                if not student.enrollments.exclude(group=group).filter(status='active').exists():
                    student.status = 'graduated'
                student.save()
        else:
            group.delete()
        messages.success(request, f'✓ {name} o\'chirildi')
        return redirect('group_list')
    return render(request, 'core/group_confirm_delete.html', {'group': group})


# ─── Schedule (Dars jadvali) ─────────────────────────────────────
@login_required
def schedule_view(request):
    user = request.user
    selected_day = request.GET.get('day', '')
    selected_teacher = request.GET.get('teacher', '')
    selected_room = request.GET.get('room', '')

    groups_qs = Group.objects.filter(is_active=True).select_related('teacher').annotate(
        active_student_count=Count('student', filter=Q(student__status='active'))
    ).order_by('start_time', 'name')

    if is_teacher(user):
        teacher = get_teacher(user)
        if not selected_teacher and teacher:
            selected_teacher = str(teacher.id)

    if selected_day:
        groups_qs = groups_qs.filter(days=selected_day)
    if selected_teacher:
        groups_qs = groups_qs.filter(teacher_id=selected_teacher)
    if selected_room:
        groups_qs = groups_qs.filter(room=selected_room)

    groups_list = list(groups_qs)

    # To'qnashuvlar barcha faol guruhlar bo'yicha hisoblanadi, keyin ko'rsatilgan
    # kartochkalarga biriktiriladi (filtr qo'llanilganda ham boshqa guruh bilan
    # to'qnashuv ko'rinib qoladi).
    active_groups = Group.objects.filter(is_active=True).select_related('teacher')
    conflicts = find_group_conflicts(active_groups)

    for g in groups_list:
        g.conflict_list = conflicts.get(g.id, [])

    rooms = sorted({r for r in active_groups.exclude(room='').values_list('room', flat=True) if r.strip()},
                   key=str.lower)
    teachers = Teacher.objects.filter(is_active=True).order_by('name')

    context = {
        'groups': groups_list,
        'rooms': rooms,
        'teachers': teachers,
        'days_choices': Group.DAYS_CHOICES,
        'selected_day': selected_day,
        'selected_teacher': selected_teacher,
        'selected_room': selected_room,
        'total_conflicts': sum(1 for g in groups_list if g.conflict_list),
    }
    return render(request, 'core/schedule.html', context)


# ─── Payments ────────────────────────────────────────────────────
@login_required
@capability_required('payments.view')
def payment_list(request):
    user = request.user
    payments = Payment.objects.filter(student__in=visible_students(user)).select_related('student', 'student__teacher', 'student__receptionist', 'student__group', 'received_by')

    q = request.GET.get('q', '').strip()
    month = request.GET.get('month', '')
    paid_from = request.GET.get('paid_from', '').strip()
    paid_to = request.GET.get('paid_to', '').strip()
    student_id = request.GET.get('student', '')
    group_id = request.GET.get('group', '')
    teacher_id = request.GET.get('teacher', '')
    ptype = request.GET.get('type', '')

    if q:
        payments = payments.filter(
            Q(student__name__icontains=q) |
            Q(student__phone__icontains=q) |
            Q(student__parent_phone__icontains=q) |
            Q(student__group__name__icontains=q)
        )
    if month and '-' in month:
        y, m = month.split('-')[:2]
        payments = payments.filter(month__year=y, month__month=m)
    if paid_from:
        try:
            d_from = datetime.strptime(paid_from, '%Y-%m-%d').date()
            payments = payments.filter(paid_date__date__gte=d_from)
        except ValueError:
            pass
    if paid_to:
        try:
            d_to = datetime.strptime(paid_to, '%Y-%m-%d').date()
            payments = payments.filter(paid_date__date__lte=d_to)
        except ValueError:
            pass
    if student_id and student_id.isdigit():
        payments = payments.filter(student_id=student_id)
    if group_id and group_id.isdigit():
        payments = payments.filter(student__group_id=group_id)
    if teacher_id:
        payments = payments.filter(student__teacher_id=teacher_id)
    if ptype:
        payments = payments.filter(payment_type=ptype)

    total = payments.aggregate(Sum('amount'))['amount__sum'] or 0

    context = {
        'payments': payments,
        'students': visible_students(user).select_related('group').order_by('name'),
        'groups': visible_groups(user).filter(is_active=True).order_by('name'),
        'teachers': Teacher.objects.filter(pk__in=visible_students(user).values('teacher_id')).order_by('name'),
        'selected_month': month,
        'selected_paid_from': paid_from,
        'selected_paid_to': paid_to,
        'student_count': payments.order_by().values('student_id').distinct().count(),
        'payment_count': payments.count(),
        'selected_student': student_id,
        'selected_group': group_id,
        'selected_teacher': teacher_id,
        'selected_type': ptype,
        'q': q,
        'total': total,
        'payment_types': Payment.PAYMENT_TYPES,
    }
    context['payments'] = paginate(request, payments.order_by('-paid_date', '-pk'))
    context['report_query'] = report_query(request, 'payments', {'month': 'service_month', 'paid_from': 'date_from', 'paid_to': 'date_to', 'type': 'payment_type'})
    return render(request, 'core/payment_list.html', context)


@login_required
@capability_required('payments.accept')
def payment_create(request):
    """Admin va Retsepshen to'lov qabul qila oladi. Chek darhol shakllanadi."""
    initial = {}
    student_id = request.GET.get('student', '')
    if student_id.isdigit():
        initial['student'] = student_id
    form = PaymentForm(request.POST or None, initial=initial)
    form.fields['student'].queryset = form.fields['student'].queryset.filter(pk__in=visible_students(request.user).values('pk'))
    form.fields['enrollment'].queryset = form.fields['enrollment'].queryset.filter(student__in=visible_students(request.user))
    if form.is_valid():
        payment = form.save(commit=False)
        payment.received_by = request.user
        try:
            payment = accept_payment(payment, form.cleaned_data.get('submission_key'),
                                     compare_paid_date=bool(request.POST.get('paid_date')))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f'✓ To\'lov qabul qilindi: {payment.student.name}')
            return redirect(reverse('payment_receipt', args=[payment.pk]) + '?created=1')
    return render(request, 'core/payment_form.html', {'form': form, 'title': "To'lov qo'shish"})


@login_required
@capability_required('payments.view')
def payment_receipt(request, pk):
    queryset = Payment.all_objects.select_related('student', 'student__group__course', 'student__teacher', 'received_by')
    if not is_admin(request.user):
        queryset = queryset.filter(student__in=visible_students(request.user))
    payment = get_object_or_404(
        queryset,
        pk=pk
    )
    is_new = request.GET.get('created') == '1' and not payment.voided_at
    from .payment_verification import qr_image_url, verification_url, qr_image_data_uri, receipt_amount_text
    verify_url = verification_url(request, payment)
    qr_data_uri = qr_image_data_uri(verify_url)
    return render(request, 'core/payment_receipt.html', {
        'verification_url': verify_url,
        'receipt_qr_url': qr_image_url(payment),
        'receipt_qr_data_uri': qr_data_uri,
        'payment': payment,
        'student': payment.student,
        'is_new': is_new,
        'amount_in_words': payment.amount_in_words,
        'receipt_amount': receipt_amount_text(payment.amount),
    })


@login_required
@capability_required('reports.export')
def payment_export(request):
    if not has_capability(request.user, 'payments.view'):
        return HttpResponseForbidden("To'lovlarni ko'rish huquqi kerak.")
    payments = Payment.objects.filter(student__in=visible_students(request.user)).select_related('student', 'student__teacher', 'student__group', 'received_by')

    q = request.GET.get('q', '').strip()
    month = request.GET.get('month', '')
    paid_from = request.GET.get('paid_from', '').strip()
    paid_to = request.GET.get('paid_to', '').strip()
    group_id = request.GET.get('group', '')
    teacher_id = request.GET.get('teacher', '')
    ptype = request.GET.get('type', '')

    if q:
        payments = payments.filter(
            Q(student__name__icontains=q) | Q(student__phone__icontains=q) |
            Q(student__parent_phone__icontains=q) | Q(student__group__name__icontains=q)
        )
    if month and '-' in month:
        y, m = month.split('-')[:2]
        payments = payments.filter(month__year=y, month__month=m)
    if paid_from:
        try:
            d_from = datetime.strptime(paid_from, '%Y-%m-%d').date()
            payments = payments.filter(paid_date__date__gte=d_from)
        except ValueError:
            pass
    if paid_to:
        try:
            d_to = datetime.strptime(paid_to, '%Y-%m-%d').date()
            payments = payments.filter(paid_date__date__lte=d_to)
        except ValueError:
            pass
    if group_id and group_id.isdigit():
        payments = payments.filter(student__group_id=group_id)
    if teacher_id:
        payments = payments.filter(student__teacher_id=teacher_id)
    if ptype:
        payments = payments.filter(payment_type=ptype)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="tolovlar_{timezone.localdate().strftime("%Y%m%d")}.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow([
        'Chek raqami',
        'To\'lov sanasi va vaqti',
        'Qaysi oy uchun',
        "O'qituvchi oyligi oyi",
        "Retsepshen oyligi oyi",
        'O\'quvchi F.I.Sh.',
        'Telefon',
        'Guruh',
        'O\'qituvchi',
        'Summa (so\'m)',
        'To\'lov turi',
        'Qabul qildi',
        'Izoh',
    ])

    def safe_cell(val):
        val = str(val if val is not None else '')
        if val.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
            return "'" + val
        return val

    for p in payments.order_by('-paid_date', '-pk').iterator():
        writer.writerow([
            safe_cell(p.receipt_number),
            safe_cell(timezone.localtime(p.paid_date).strftime('%d.%m.%Y %H:%M') if p.paid_date else ''),
            safe_cell(p.month.strftime('%Y-%m')),
            safe_cell(p.teacher_salary_month.strftime('%Y-%m')),
            safe_cell(p.receptionist_salary_month.strftime('%Y-%m')),
            safe_cell(p.student.name),
            safe_cell(p.student.phone),
            safe_cell(p.student.group.name if p.student.group else ''),
            safe_cell(p.student.teacher.name if p.student.teacher else ''),
            safe_cell(f"{p.amount:,.0f}"),
            safe_cell(p.get_payment_type_display()),
            safe_cell(p.received_by.get_full_name() or p.received_by.username if p.received_by else '—'),
            safe_cell(p.comment),
        ])

    return response


@login_required
@admin_required
def payment_import_template(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="tolovlar_shablon.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow([
        'Telefon',
        'O\'quvchi ismi',
        'Summa',
        'To\'lov oyi (YYYY-MM)',
        'To\'lov sanasi (YYYY-MM-DD)',
        'To\'lov turi (naqd/plastik/bank/o\'tkazma)',
        'Izoh',
    ])
    writer.writerow([
        '+998901234567',
        'Ali Valiyev',
        '500000',
        '2026-10',
        '2026-10-15 14:30',
        'naqd',
        'Oktyabr oyi to\'lovi',
    ])
    writer.writerow([
        '+998935554433',
        'Madina Karimova',
        '600000',
        '2024-03',
        '2024-03-05 10:15',
        'plastik',
        'Eski to\'lov (tarixiy)',
    ])
    return response


@login_required
@admin_required
def payment_import(request):
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, "Iltimos, CSV faylni tanlang.")
            return render(request, 'core/payment_import.html')

        if not csv_file.name.endswith(('.csv', '.txt')):
            messages.error(request, "Faqat .csv formatidagi fayllar qabul qilinadi.")
            return render(request, 'core/payment_import.html')

        try:
            raw_bytes = csv_file.read()
            text = None
            for encoding in ('utf-8-sig', 'utf-8', 'cp1251', 'windows-1251', 'latin1'):
                try:
                    text = raw_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                messages.error(request, "Fayl kodirovkasini aniqlab bo'lmadi. UTF-8 formatida saqlang.")
                return render(request, 'core/payment_import.html')

            import io
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            if not rows:
                messages.error(request, "Fayl bo'sh.")
                return render(request, 'core/payment_import.html')

            headers = [h.strip().lower() for h in rows[0]]

            def find_col(candidates):
                for c in candidates:
                    for idx, h in enumerate(headers):
                        if c in h:
                            return idx
                return None

            phone_idx = find_col(['telefon', 'phone', 'tel'])
            name_idx = find_col(['ism', 'name', 'f.i.sh', 'fish', "o'quvchi"])
            amount_idx = find_col(['summa', 'amount', 'qiymat'])
            month_idx = find_col(['oy', 'month'])
            date_idx = find_col(['sana', 'date', 'vaqt'])
            type_idx = find_col(['tur', 'type', 'usul'])
            comment_idx = find_col(['izoh', 'comment', 'note'])

            if amount_idx is None:
                messages.error(request, "Faylda 'Summa' ustuni topilmadi.")
                return render(request, 'core/payment_import.html')

            type_map = {
                'naqd': 'cash', 'cash': 'cash',
                'plastik': 'card', 'karta': 'card', 'card': 'card',
                'bank': 'bank',
                'o\'tkazma': 'transfer', 'otkazma': 'transfer', 'transfer': 'transfer',
            }

            created_count = 0
            error_rows = []

            with transaction.atomic():
                for line_no, row in enumerate(rows[1:], start=2):
                    if not any(row):
                        continue
                    try:
                        # Find student by phone first, then name
                        student = None
                        phone = row[phone_idx].strip() if (phone_idx is not None and len(row) > phone_idx) else ''
                        name = row[name_idx].strip() if (name_idx is not None and len(row) > name_idx) else ''
                        if phone and len(''.join(filter(str.isdigit, phone))) >= 7:
                            student = Student.objects.filter(phone=phone).first()
                        if not student and name:
                            student = Student.objects.filter(name__iexact=name).first()

                        if not student:
                            error_rows.append(f"{line_no}-qator: O'quvchi topilmadi ({phone or name})")
                            continue

                        amount_raw = ''.join(c for c in row[amount_idx] if c.isdigit() or c in '.-')
                        amount = Decimal(amount_raw)
                        if amount <= 0:
                            raise ValueError("Summa musbat bo'lishi kerak")

                        # Payment month
                        month_date = timezone.localdate().replace(day=1)
                        if month_idx is not None and len(row) > month_idx:
                            raw_m = row[month_idx].strip()
                            if raw_m:
                                parsed_month = None
                                for fmt in ('%Y-%m', '%Y.%m', '%m.%Y', '%m/%Y', '%Y-%m-%d'):
                                    try:
                                        parsed_month = datetime.strptime(raw_m, fmt).date()
                                        break
                                    except ValueError:
                                        pass
                                if parsed_month is None:
                                    raise ValueError(f"To'lov oyi noto'g'ri: {raw_m}")
                                month_date = parsed_month.replace(day=1)

                        # Payment date
                        paid_dt = timezone.now()
                        if date_idx is not None and len(row) > date_idx:
                            raw_dt = row[date_idx].strip()
                            if raw_dt:
                                parsed_paid_dt = None
                                for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d', '%d.%m.%Y %H:%M', '%d.%m.%Y'):
                                    try:
                                        parsed_paid_dt = datetime.strptime(raw_dt, fmt)
                                        break
                                    except ValueError:
                                        pass
                                if parsed_paid_dt is None:
                                    raise ValueError(f"To'lov sanasi noto'g'ri: {raw_dt}")
                                paid_dt = timezone.make_aware(parsed_paid_dt) if timezone.is_naive(parsed_paid_dt) else parsed_paid_dt

                        # Type
                        ptype = 'cash'
                        if type_idx is not None and len(row) > type_idx:
                            raw_t = row[type_idx].strip().lower()
                            if raw_t:
                                ptype = type_map.get(raw_t)
                                if ptype is None:
                                    raise ValueError(f"To'lov turi noto'g'ri: {raw_t}")

                        comment = row[comment_idx].strip() if (comment_idx is not None and len(row) > comment_idx) else ''

                        p = Payment(
                            student=student,
                            amount=amount,
                            month=month_date,
                            paid_date=paid_dt,
                            payment_type=ptype,
                            received_by=request.user,
                            comment=comment,
                        )
                        p.save()
                        created_count += 1
                    except Exception as ex:
                        error_rows.append(f"{line_no}-qator: {str(ex)}")

            if created_count:
                messages.success(request, f"✓ Import muvaffaqiyatli: {created_count} ta to'lov cheki bazaga kiritildi.")
            if error_rows:
                messages.warning(request, f"Ayrim qatorlarda xatolik: {', '.join(error_rows[:5])}")
            return redirect('payment_list')
        except Exception as e:
            messages.error(request, f"Faylni o'qishda xatolik: {str(e)}")
            return render(request, 'core/payment_import.html')

    return render(request, 'core/payment_import.html')


@login_required
@capability_required('payments.edit')
def payment_edit(request, pk):
    payment = get_object_or_404(Payment.objects.filter(student__in=visible_students(request.user)), pk=pk)
    form = PaymentForm(request.POST or None, instance=payment)
    form.fields['student'].queryset = visible_students(request.user)
    form.fields['enrollment'].queryset = form.fields['enrollment'].queryset.filter(student__in=visible_students(request.user))
    if form.is_valid():
        try:
            form.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, '✓ To\'lov yangilandi; o‘zgarish tarixga yozildi')
            return redirect('payment_list')
    return render(request, 'core/payment_form.html', {'form': form, 'title': "To'lov tahrirlash", 'payment': payment})


@login_required
@capability_required('payments.void')
def payment_delete(request, pk):
    payment = get_object_or_404(Payment.objects.filter(student__in=visible_students(request.user)), pk=pk)
    if request.method == 'POST':
        try:
            payment.void(request.POST.get('reason', ''))
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, '✓ To\'lov bekor qilindi; yozuv va sabab tarixda saqlandi')
            return redirect('payment_list')
    return render(request, 'core/payment_confirm_delete.html', {'payment': payment})


# ─── Teacher Salaries ────────────────────────────────────────────
@login_required
def salary_list(request):
    user = request.user
    salaries = Salary.objects.select_related('teacher').all()

    can_view_all = has_capability(user, 'salary.teacher.view')
    if not can_view_all and is_teacher(user):
        if not has_capability(user, TEACHER_OWN_SALARY):
            raise PermissionDenied("O'z oyligingizni ko'rish huquqi berilmagan.")
        teacher = get_teacher(user)
        if not teacher:
            raise PermissionDenied("O'qituvchi profili topilmadi.")
        salaries = salaries.filter(teacher=teacher)
    elif not can_view_all:
        raise PermissionDenied("O'qituvchi oyligini ko'rish huquqi yo'q.")

    month = request.GET.get('month', '')
    if month and '-' in month:
        y, m = month.split('-')[:2]
        if y.isdigit() and m.isdigit():
            salaries = salaries.filter(month__year=y, month__month=m)
    total_paid = salaries.filter(is_paid=True).aggregate(Sum('salary_amount'))['salary_amount__sum'] or 0
    total_unpaid = salaries.filter(is_paid=False).aggregate(Sum('salary_amount'))['salary_amount__sum'] or 0
    return render(request, 'core/salary_list.html', {
        'salaries': salaries,
        'selected_month': month,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'own_salary': not can_view_all,
        'can_manage_salaries': has_capability(user, 'salary.teacher.manage'),
    })


@login_required
@capability_required('salary.teacher.manage')
@transaction.atomic
def calculate_salaries(request):
    from .payroll import teacher_totals
    if request.method == 'POST':
        month_str = request.POST.get('month', '')
        try:
            y, m = map(int, month_str.split('-')[:2])
            month_date = date(y, m, 1)
        except (ValueError, AttributeError):
            messages.error(request, 'Oy noto\'g\'ri')
            return redirect('salary_list')

        count = 0
        for teacher in Teacher.objects.filter(is_active=True):
            salary, _ = Salary.objects.select_for_update().get_or_create(
                teacher=teacher, month=month_date,
                defaults={'total_income': 0, 'percent': teacher.percent, 'salary_amount': 0},
            )
            if salary.is_paid:
                continue
            total_income, salary_amount = teacher_totals(teacher, month_date)
            salary.total_income = total_income
            salary.percent = teacher.percent
            salary.salary_amount = salary_amount
            salary.save(update_fields=['total_income', 'percent', 'salary_amount'])
            count += 1

        messages.success(request, f'✓ {count} ta o\'qituvchi oyligi hisoblandi')
        return redirect('salary_list')

    return render(request, 'core/calculate_salary.html', {'current_month': timezone.localdate().replace(day=1)})


@require_POST
@login_required
@capability_required('salary.teacher.manage')
@transaction.atomic
def update_salary_status(request, pk):
    salary = get_object_or_404(Salary.objects.select_for_update(), pk=pk)
    salary.is_paid = not salary.is_paid
    salary.save(update_fields=['is_paid'])
    status = "to'landi" if salary.is_paid else "to'lanmadi"
    messages.success(request, f'✓ {salary.teacher.name} oyligi {status}')
    return redirect('salary_list')


# ─── Attendance ───────────────────────────────────────────────────
@login_required
def attendance_list(request):
    user = request.user
    today = timezone.localdate()
    selected_date_str = request.GET.get('date', today.isoformat())
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = today

    group_id = request.GET.get('group', '')
    attendances = Attendance.objects.filter(date=selected_date).select_related('student', 'group')
    groups_qs = Group.objects.filter(is_active=True).order_by('name')

    if is_teacher(user):
        teacher = get_teacher(user)
        attendances = attendances.filter(group__teacher=teacher) if teacher else attendances.none()
        groups_qs = groups_qs.filter(teacher=teacher) if teacher else groups_qs.none()

    if group_id:
        attendances = attendances.filter(group_id=group_id)

    context = {
        'attendances': attendances,
        'groups': groups_qs,
        'selected_date': selected_date,
        'selected_group': group_id,
        'present_count': attendances.filter(status='present').count(),
        'absent_count': attendances.filter(status='absent').count(),
        'late_count': attendances.filter(status='late').count(),
        'excused_count': attendances.filter(status='excused').count(),
    }
    return render(request, 'core/attendance_list.html', context)


@login_required
@transaction.atomic
def take_attendance(request, group_id):
    user = request.user
    group = get_object_or_404(Group, pk=group_id)

    if is_teacher(user):
        teacher = get_teacher(user)
        if not teacher or group.teacher_id != teacher.id:
            messages.error(request, "Siz faqat o'z guruhingiz davomatini olasiz.")
            return redirect('attendance_list')

    today = timezone.localdate()
    students = visible_students(user).filter(enrollments__group=group, enrollments__status='active', enrollments__starts_on__lte=today, status='active').distinct().order_by('name')
    can_grade = has_capability(user, 'grades.write')
    existing = dict(Attendance.objects.filter(group=group, date=today).values_list('student_id', 'status'))
    existing_grades = {grade.student_id: grade for grade in Grade.objects.filter(group=group, date=today, grade_type='classwork', student__in=students)} if can_grade else {}
    scores = {student_id: grade.score for student_id, grade in existing_grades.items()}
    grade_errors = {}
    form_errors = []

    if request.method == 'POST':
        if not can_grade and any(key.startswith('score_') and value.strip() for key, value in request.POST.items()):
            return HttpResponseForbidden("Baho qo'yish huquqi berilmagan.")
        valid_statuses = dict(Attendance.STATUS_CHOICES)
        parsed_scores = {}
        for student in students:
            status = request.POST.get(f'attendance_{student.pk}', '')
            if len(request.POST.get(f'note_{student.pk}', '')) > Attendance._meta.get_field('note').max_length:
                form_errors.append(f"{student.name}: izoh 200 belgidan oshmasligi kerak.")
            if status not in ('', *valid_statuses):
                form_errors.append(f"{student.name}: davomat holati noto'g'ri.")
            elif status:
                existing[student.pk] = status
            if can_grade:
                raw_score = request.POST.get(f'score_{student.pk}', '').strip()
                scores[student.pk] = raw_score
                if raw_score:
                    if not (raw_score.isascii() and raw_score.isdigit() and len(raw_score) <= 3 and 1 <= int(raw_score) <= 100):
                        grade_errors[student.pk] = '1 dan 100 gacha butun son kiriting.'
                    elif status not in valid_statuses:
                        grade_errors[student.pk] = 'Baho bilan birga davomat holatini ham belgilang.'
                    else:
                        parsed_scores[student.pk] = int(raw_score)
        if grade_errors:
            form_errors.append("Baholardagi xatolarni to'g'rilang. Hozircha hech qanday ma'lumot saqlanmadi.")
        if not form_errors:
            for student in students:
                status = request.POST.get(f'attendance_{student.id}')
                if status:
                    defaults = {'status': status, 'marked_by': request.user}
                    if f'note_{student.pk}' in request.POST:
                        defaults['note'] = request.POST[f'note_{student.pk}']
                    Attendance.objects.update_or_create(student=student, group=group, date=today, defaults=defaults)
                score = parsed_scores.get(student.pk)
                previous = existing_grades.get(student.pk)
                if score is not None and (previous is None or previous.score != score):
                    Grade.objects.update_or_create(
                        student=student, group=group, date=today, grade_type='classwork',
                        defaults={'score': score, 'graded_by': user},
                    )
            text = f'✓ {group.name} davomati saqlandi'
            if parsed_scores:
                text += f'. {len(parsed_scores)} ta darsdagi faollik bahosi saqlandi'
            messages.success(request, text)
            return redirect('attendance_list')

    return render(request, 'core/attendance_form.html', {
        'group': group,
        'students': students,
        'existing': existing,
        'today': today,
        'can_grade': can_grade, 'scores': scores, 'grade_errors': grade_errors, 'form_errors': form_errors,
    })


@login_required
def take_attendance_select(request):
    user = request.user
    teacher = get_teacher(user) if is_teacher(user) else None
    form = AttendanceChoiceForm(request.POST or None, teacher=teacher)
    has_groups = form.fields['group'].queryset.exists()

    if request.method == 'POST' and form.is_valid():
        group = form.cleaned_data['group']
        return redirect('take_attendance', group_id=group.id)

    return render(request, 'core/attendance_pick.html', {
        'form': form,
        'has_groups': has_groups,
    })


# ─── Grades (Baholar) ─────────────────────────────────────────────
@login_required
def grade_list(request):
    user = request.user
    today = timezone.localdate()
    selected_date_str = request.GET.get('date', '')
    selected_date = None
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = None

    group_id = request.GET.get('group', '')
    grade_type = request.GET.get('grade_type', '')

    grades = Grade.objects.select_related('student', 'group', 'graded_by').all()
    groups_qs = Group.objects.filter(is_active=True).order_by('name')

    if is_teacher(user):
        teacher = get_teacher(user)
        grades = grades.filter(group__teacher=teacher) if teacher else grades.none()
        groups_qs = groups_qs.filter(teacher=teacher) if teacher else groups_qs.none()

    if selected_date:
        grades = grades.filter(date=selected_date)
    if group_id:
        grades = grades.filter(group_id=group_id)
    if grade_type:
        grades = grades.filter(grade_type=grade_type)

    avg_score = grades.aggregate(Avg('score'))['score__avg']

    context = {
        'grades': paginate(request, grades.order_by('-date', '-created_at', '-pk')),
        'groups': groups_qs,
        'selected_date': selected_date_str,
        'selected_group': group_id,
        'selected_grade_type': grade_type,
        'grade_types': Grade.GRADE_TYPES,
        'total_count': grades.count(),
        'avg_score': round(avg_score, 1) if avg_score else None,
        'classwork_count': grades.filter(grade_type='classwork').count(),
        'homework_count': grades.filter(grade_type='homework').count(),
        'exam_count': grades.filter(grade_type='exam').count(),
        'monthly_count': grades.filter(grade_type='monthly').count(),
    }
    return render(request, 'core/grade_list.html', context)


@login_required
def take_grades_select(request):
    user = request.user
    teacher = get_teacher(user) if is_teacher(user) else None
    form = GradeChoiceForm(request.POST or None, teacher=teacher)
    has_groups = form.fields['group'].queryset.exists()

    if request.method == 'POST' and form.is_valid():
        group = form.cleaned_data['group']
        return redirect('take_grades', group_id=group.id)

    return render(request, 'core/grade_pick.html', {
        'form': form,
        'has_groups': has_groups,
    })


@login_required
def take_grades(request, group_id):
    user = request.user
    group = get_object_or_404(Group, pk=group_id)

    if is_teacher(user):
        teacher = get_teacher(user)
        if not teacher or group.teacher_id != teacher.id:
            messages.error(request, "Siz faqat o'z guruhingizga baho qo'ya olasiz.")
            return redirect('grade_list')

    today = timezone.localdate()
    selected_date_str = request.GET.get('date', today.isoformat())
    try:
        grade_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        grade_date = today

    grade_type = request.GET.get('grade_type', 'classwork')
    if grade_type not in dict(Grade.GRADE_TYPES):
        grade_type = 'classwork'

    students = visible_students(user).filter(enrollments__group=group, enrollments__status='active', enrollments__starts_on__lte=today, status='active').distinct().order_by('name')

    if request.method == 'POST':
        post_date_str = request.POST.get('date', today.isoformat())
        try:
            grade_date = datetime.strptime(post_date_str, '%Y-%m-%d').date()
        except ValueError:
            grade_date = today

        grade_type = request.POST.get('grade_type', 'classwork')
        if grade_type not in dict(Grade.GRADE_TYPES):
            grade_type = 'classwork'

        saved_count = 0
        for student in students:
            score_val = request.POST.get(f'score_{student.id}', '').strip()
            note_val = request.POST.get(f'note_{student.id}', '').strip()
            if score_val:
                try:
                    score_int = int(score_val)
                    if 1 <= score_int <= 100:
                        Grade.objects.update_or_create(
                            student=student,
                            group=group,
                            date=grade_date,
                            grade_type=grade_type,
                            defaults={
                                'score': score_int,
                                'note': note_val,
                                'graded_by': request.user,
                            }
                        )
                        saved_count += 1
                except ValueError:
                    pass

        messages.success(request, f'✓ {group.name} guruhi uchun {saved_count} ta baho saqlandi.')
        return redirect('grade_list')

    existing = {
        g.student_id: g
        for g in Grade.objects.filter(group=group, date=grade_date, grade_type=grade_type)
    }

    return render(request, 'core/grade_form.html', {
        'group': group,
        'students': students,
        'existing': existing,
        'grade_date': grade_date,
        'grade_type': grade_type,
        'grade_types': Grade.GRADE_TYPES,
    })


@login_required
@require_POST
def grade_delete(request, pk):
    grade = get_object_or_404(Grade, pk=pk)
    user = request.user
    if is_teacher(user):
        teacher = get_teacher(user)
        if not teacher or grade.group.teacher_id != teacher.id:
            messages.error(request, "Ruxsat berilmagan!")
            return redirect('grade_list')

    grade.delete()
    messages.success(request, "Baho o'chirildi.")
    return redirect('grade_list')


@login_required
def student_card_print(request, pk):
    student = get_object_or_404(visible_students(request.user).select_related('teacher', 'group', 'receptionist'), pk=pk)
    user = request.user

    if is_teacher(user):
        teacher = get_teacher(user)
        if not teacher or not visible_students(user).filter(pk=student.pk).exists():
            messages.error(request, "Siz faqat o'z guruhingizdagi o'quvchini ko'ra olasiz.")
            return redirect('student_list')

    grade_qs = student.grades.filter(group__in=visible_groups(user)) if has_capability(user, 'grades.view') else Grade.objects.none()
    attendance_qs = student.attendances.filter(group__in=visible_groups(user)) if has_capability(user, 'attendance.view') else Attendance.objects.none()
    avg_score = grade_qs.aggregate(Avg('score'))['score__avg']

    return render(request, 'core/student_card.html', {
        'student': student,
        'avg_score': round(avg_score, 1) if avg_score else None,
        'total_attendance': attendance_qs.count(),
        'present_attendance': attendance_qs.filter(status__in=['present', 'late']).count(),
    })


# ─── Assignment History (faqat Boshliq) ───────────────────────────
@login_required
@capability_required('assignments.view')
def assignment_history(request):
    history = AssignmentHistory.objects.select_related('student', 'teacher', 'group', 'changed_by').all()
    student_id = request.GET.get('student', '')
    if student_id:
        history = history.filter(student_id=student_id)
    return render(request, 'core/assignment_history.html', {
        'history': history,
        'students': Student.objects.all().order_by('name'),
        'selected_student': student_id,
    })


# ─── Expenses (faqat Boshliq) ──────────────────────────────────────
@login_required
@capability_required('expenses.view')
def expense_list(request):
    expenses = Expense.objects.select_related('added_by').all()
    month = request.GET.get('month', '')
    category = request.GET.get('category', '')
    if month and '-' in month:
        y, m = month.split('-')[:2]
        expenses = expenses.filter(date__year=y, date__month=m)
    if category:
        expenses = expenses.filter(category=category)
    total = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    return render(request, 'core/expense_list.html', {
        'expenses': expenses,
        'total': total,
        'selected_month': month,
        'selected_category': category,
        'category_choices': Expense.CATEGORY_CHOICES,
    })


@login_required
@capability_required('expenses.create')
def expense_create(request):
    form = ExpenseForm(request.POST or None, initial={'date': timezone.localdate()})
    if form.is_valid():
        e = form.save(commit=False)
        e.added_by = request.user
        e.save()
        messages.success(request, f'✓ {e.title} xarajat qo\'shildi')
        return redirect('expense_list')
    return render(request, 'core/expense_form.html', {'form': form, 'title': "Xarajat qo'shish"})


@login_required
@capability_required('expenses.delete')
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, '✓ Xarajat o\'chirildi')
        return redirect('expense_list')
    return render(request, 'core/expense_confirm_delete.html', {'expense': expense})


# ─── Reports (faqat Boshliq) ───────────────────────────────────────
@login_required
@capability_required('finance.reports')
def reports(request):
    today = timezone.localdate()

    months_range = calendar_months(today, 12)
    start_month = months_range[0]
    month_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
    payments_by_month = monthly_income_totals(start_month, month_end)
    expenses_by_month = monthly_expense_totals(start_month, month_end)
    year_cash = monthly_income_totals(date(today.year, 1, 1), date(today.year, 12, 31))
    year_expenses = monthly_expense_totals(date(today.year, 1, 1), date(today.year, 12, 31))
    monthly_income = []
    for m in months_range:
        inc = float(payments_by_month.get(m, 0))
        exp = float(expenses_by_month.get(m, 0))
        monthly_income.append({'month': m.strftime('%Y-%m'), 'income': inc, 'expense': exp, 'net': inc - exp})

    debtors = []
    active_students = Student.objects.filter(status='active').select_related('teacher', 'group').prefetch_related('payments', 'tariffs')
    for student in active_students:
        debt_amount = student.get_debt_amount()
        if debt_amount > 0:
            months = student.get_debt_months()
            payments = list(student.payments.all())
            payments.sort(key=lambda p: p.month, reverse=True)
            last_payment = payments[0] if payments else None
            debtors.append({
                'student': student,
                'months_debt': months,
                'debt_amount': debt_amount,
                'last_payment_month': last_payment.month.strftime('%Y-%m') if last_payment else 'Hech qachon'
            })
    debtors.sort(key=lambda x: x['debt_amount'], reverse=True)

    teacher_income = [
        {'teacher': t, 'total': float(t.year_salary or 0)}
        for t in Teacher.objects.filter(is_active=True).annotate(
            year_salary=Sum('salaries__salary_amount', filter=Q(salaries__month__year=today.year))
        ).order_by('-year_salary')
    ]

    last_30 = Attendance.objects.filter(date__gte=today - timedelta(days=30))
    total_att = last_30.count() or 1

    source_stats = Student.objects.filter(status='active').values('source').annotate(count=Count('id'))

    # Aggregate independent relations separately to avoid multiplying commissions
    # by the number of students (SUM(DISTINCT amount) would also be incorrect).
    counts = dict(Student.objects.filter(status='active').values('receptionist_id').annotate(n=Count('id')).values_list('receptionist_id', 'n'))
    commissions = {
        row['receptionist_id']: row
        for row in ReceptionistCommission.objects.values('receptionist_id').annotate(
            m_comm=Sum('commission_amount', filter=Q(month__year=today.year, month__month=today.month)),
            y_comm=Sum('commission_amount', filter=Q(month__year=today.year)),
        )
    }
    receptionist_stats = [
        {'receptionist': rec,
         'month_commission': float(commissions.get(rec.pk, {}).get('m_comm') or 0),
         'year_commission': float(commissions.get(rec.pk, {}).get('y_comm') or 0),
         'student_count': counts.get(rec.pk, 0)}
        for rec in Receptionist.objects.filter(is_active=True)
    ]

    context = {
        'monthly_income': monthly_income,
        'debtors': debtors,
        'teacher_income': teacher_income,
        'today': today,
        'attendance_stats': {
            'total': total_att,
            'present': last_30.filter(status='present').count(),
            'late': last_30.filter(status='late').count(),
            'absent': last_30.filter(status='absent').count(),
            'present_percent': round(last_30.filter(status='present').count() / total_att * 100, 1),
        },
        'source_stats': {s['source']: s['count'] for s in source_stats},
        'receptionist_stats': receptionist_stats,
        'total_income_year': sum(year_cash.values(), Decimal(0)),
        'total_expense_year': sum(year_expenses.values(), Decimal(0)),
    }
    return render(request, 'core/reports.html', context)



# ─── Certificates ────────────────────────────────────────────────
@login_required
def certificate_list(request):
    user = request.user
    certificates = visible_certificates(user).select_related('student', 'group', 'created_by')

    if is_teacher(user):
        teacher = get_teacher(user)
        certificates = certificates.filter(
            Q(student__teacher=teacher) | Q(group__teacher=teacher)
        ) if teacher else certificates.none()

    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    course_filter = request.GET.get('course', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if q:
        certificates = certificates.filter(
            Q(certificate_number__icontains=q) |
            Q(student__name__icontains=q) |
            Q(student__phone__icontains=q) |
            Q(course_name__icontains=q) |
            Q(teacher_name__icontains=q)
        )
    if status_filter:
        certificates = certificates.filter(status=status_filter)
    if course_filter:
        certificates = certificates.filter(course_name__icontains=course_filter)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            certificates = certificates.filter(issue_date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            certificates = certificates.filter(issue_date__lte=d_to)
        except ValueError:
            pass

    total_count = certificates.count()
    active_count = certificates.filter(status='active').count()
    revoked_count = certificates.filter(status='revoked').count()

    context = {
        'certificates': paginate(request, certificates.order_by('-issue_date', '-created_at', '-pk')),
        'q': q,
        'selected_status': status_filter,
        'selected_course': course_filter,
        'selected_date_from': date_from,
        'selected_date_to': date_to,
        'total_count': total_count,
        'active_count': active_count,
        'revoked_count': revoked_count,
        'status_choices': Certificate.STATUS_CHOICES,
        'cert_settings': CertificateSetting.get_settings(),
    }
    return render(request, 'core/certificate_list.html', context)


@login_required
def certificate_create(request):
    user = request.user
    initial = {}
    student_id = request.GET.get('student', '')
    if student_id.isdigit():
        student = visible_students(user).filter(pk=student_id).first()
        if student:
            initial['student'] = student.pk
            initial['start_date'] = student.registration_date
            initial['end_date'] = timezone.localdate()
            if student.group:
                initial['group'] = student.group.pk
                initial['course_name'] = student.group.name
                if student.group.teacher:
                    initial['teacher_name'] = student.group.teacher.name
            elif student.teacher:
                initial['teacher_name'] = student.teacher.name

    form = CertificateForm(request.POST or None, initial=initial)
    form.fields['student'].queryset = visible_students(user)
    form.fields['group'].queryset = visible_groups(user)
    if request.method == 'POST' and form.is_valid():
        cert = form.save(commit=False)
        cert.created_by = user
        cert.save()
        messages.success(request, f"✓ Sertifikat muvaffaqiyatli yaratildi: {cert.certificate_number} ({cert.student.name})")
        return redirect('certificate_detail', pk=cert.pk)

    return render(request, 'core/certificate_form.html', {
        'form': form,
        'title': "Yangi sertifikat berish",
        'action': 'create',
    })


@login_required
def certificate_detail(request, pk):
    cert = get_object_or_404(
        visible_certificates(request.user).select_related('student', 'group', 'created_by'),
        pk=pk
    )
    user = request.user
    if is_teacher(user):
        teacher = get_teacher(user)
        if not teacher or (cert.student.teacher_id != teacher.id and (not cert.group or cert.group.teacher_id != teacher.id)):
            messages.error(request, "Faqat o'z o'quvchilaringiz sertifikatini ko'ra olasiz.")
            return redirect('certificate_list')

    from django.conf import settings as conf_settings
    from .payment_verification import get_local_lan_ip, qr_image_data_uri

    path = reverse('certificate_verify', args=[cert.certificate_number])
    base_url = (
        getattr(conf_settings, 'QR_VERIFY_BASE_URL', '') or
        getattr(conf_settings, 'SITE_URL', '') or
        getattr(conf_settings, 'TELEGRAM_PUBLIC_URL', '')
    )
    if base_url:
        verify_url = f"{base_url.rstrip('/')}{path}"
    elif request is not None:
        host = request.get_host()
        if 'localhost' in host or '127.0.0.1' in host:
            lan_ip = get_local_lan_ip()
            if lan_ip and lan_ip != '127.0.0.1':
                port = request.get_port()
                port_str = f":{port}" if port and str(port) not in ('80', '443') else ""
                verify_url = f"{request.scheme}://{lan_ip}{port_str}{path}"
            else:
                verify_url = request.build_absolute_uri(path)
        else:
            verify_url = request.build_absolute_uri(path)
    else:
        verify_url = path

    qr_data_uri = qr_image_data_uri(verify_url)
    settings = CertificateSetting.get_settings()

    return render(request, 'core/certificate_detail.html', {
        'cert': cert,
        'student': cert.student,
        'verify_url': verify_url,
        'qr_data_uri': qr_data_uri,
        'settings': settings,
    })


@login_required
def certificate_edit(request, pk):
    user = request.user
    cert = get_object_or_404(visible_certificates(user), pk=pk)

    form = CertificateForm(request.POST or None, instance=cert)
    form.fields['student'].queryset = visible_students(user)
    form.fields['group'].queryset = visible_groups(user)
    if request.method == 'POST' and form.is_valid():
        cert = form.save()
        messages.success(request, f"✓ Sertifikat yangilandi: {cert.certificate_number}")
        return redirect('certificate_detail', pk=cert.pk)

    return render(request, 'core/certificate_form.html', {
        'form': form,
        'cert': cert,
        'title': f"Sertifikatni tahrirlash ({cert.certificate_number})",
        'action': 'edit',
    })


@login_required
def certificate_delete(request, pk):
    user = request.user
    cert = get_object_or_404(visible_certificates(user), pk=pk)
    if request.method == 'POST':
        num = cert.certificate_number
        student_name = cert.student.name
        cert.delete()
        messages.success(request, f"✓ {num} raqamli sertifikat o'chirildi ({student_name}).")
        return redirect('certificate_list')
    return render(request, 'core/certificate_confirm_delete.html', {'cert': cert})


@login_required
@capability_required('certificates.settings')
def certificate_settings(request):
    setting = CertificateSetting.get_settings()
    form = CertificateSettingForm(request.POST or None, instance=setting)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "✓ Sertifikat sozlamalari muvaffaqiyatli saqlandi!")
        return redirect('certificate_settings')
    return render(request, 'core/certificate_settings.html', {
        'form': form,
        'setting': setting,
    })


def certificate_verify(request, number_or_code):
    lookup = str(number_or_code).strip()
    cert = Certificate.objects.filter(certificate_number__iexact=lookup).select_related('student', 'group').first()
    if not cert:
        try:
            val_uuid = uuid.UUID(lookup)
            cert = Certificate.objects.filter(verification_code=val_uuid).select_related('student', 'group').first()
        except (ValueError, TypeError, AttributeError):
            pass

    settings = CertificateSetting.get_settings()

    return render(request, 'core/certificate_verify.html', {
        'cert': cert,
        'found': cert is not None,
        'lookup': lookup,
        'verified_at': timezone.now(),
        'settings': settings,
    })
