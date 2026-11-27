from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Lead, Notification, ReminderDispatch, Student


def lead_staff(lead=None):
    users = get_user_model().objects.filter(is_active=True)
    from django.db.models import Q
    reception = Q(receptionist_profile__is_active=True)
    if lead and lead.assigned_to_id:
        reception &= Q(pk=lead.assigned_to_id)
    return users.filter(Q(is_superuser=True) | reception).distinct()


def notify_lead_staff(lead, title, event_key=None):
    users = list(lead_staff(lead))
    Notification.objects.bulk_create([
        Notification(recipient=user, lead=lead, title=title, type='info',
                     message=f'#{lead.pk} | {lead.name} | {lead.phone} | {lead.course}')
        for user in users
    ])
    from .messaging import queue_staff_notifications
    queue_staff_notifications(users, f'{title}\n#{lead.pk} | {lead.name} | {lead.phone} | {lead.course}',
                              event_key or f'lead-arrived:{lead.pk}', lead=lead)


def dispatch_new_lead_reminders(now=None):
    now = now or timezone.now()
    today = timezone.localdate(now)
    dispatched = []
    for pk in Lead.objects.filter(status='new', archived_at__isnull=True, created_at__date__lt=today).values_list('pk', flat=True):
        with transaction.atomic():
            lead = Lead.objects.select_for_update().get(pk=pk)
            if lead.status != 'new' or not lead_staff(lead).exists():
                continue
            _, created = ReminderDispatch.objects.get_or_create(key=f'new-lead:{pk}:{today}')
            if created:
                users = list(lead_staff(lead))
                title = "Bu ariza bilan hali bog'lanmadingiz"
                Notification.objects.bulk_create([Notification(recipient=user, lead=lead, title=title,
                    message=f'{lead.name} | {lead.phone} | {lead.course}') for user in users])
                from .messaging import queue_staff_notifications
                queue_staff_notifications(users, f'{title}\n{lead.name} | {lead.phone} | {lead.course}',
                                          f'new-lead:{pk}:{today}', lead=lead)
                dispatched.append(lead)
    return dispatched


def dispatch_due_callback_reminders(now=None):
    now = now or timezone.now()
    today = timezone.localdate(now)
    dispatched = []
    leads = Lead.objects.filter(
        status='callback',
        archived_at__isnull=True,
        follow_up_at__lte=now + timedelta(minutes=10),
    )
    for lead in leads:
        staff = list(lead_staff(lead))
        if not staff:
            continue
        key = f'callback:{lead.pk}:{lead.follow_up_at.isoformat()}:{today}'
        with transaction.atomic():
            _, created = ReminderDispatch.objects.get_or_create(key=key)
            if not created:
                continue
            Notification.objects.bulk_create([
                Notification(
                    recipient=user,
                    lead=lead,
                    title='Qayta qo‘ng‘iroq vaqti',
                    message=(
                        f'{lead.name} | {lead.phone} | {lead.course} | '
                        f'{timezone.localtime(lead.follow_up_at):%d.%m.%Y %H:%M}'
                    ),
                    type='info',
                )
                for user in staff
            ])
        dispatched.append(lead)
        from .messaging import queue_staff_notifications
        queue_staff_notifications(staff, f'Qayta qo‘ng‘iroq vaqti\n{lead.name} | {lead.phone} | {lead.course} | {timezone.localtime(lead.follow_up_at):%d.%m.%Y %H:%M}',
                                  key, lead=lead)

    return dispatched


def dispatch_student_payment_reminders(now=None):
    """Notify assigned finance staff before tuition is due and while debt remains."""
    from .accounts import student_accounts
    from .messaging import queue_staff_notifications
    from .permissions import has_capability
    from django.db.models import Q

    now = now or timezone.now()
    today = timezone.localdate(now)
    due_soon = today + timedelta(days=3)
    dispatched = []

    students = Student.objects.filter(status='active').select_related(
        'group', 'receptionist__user',
    ).prefetch_related('tariffs', 'enrollments__group')
    for student in students:
        accounts = [row for row in student_accounts(student, due_soon) if row['balance'] > 0]
        events = []
        upcoming = [row for row in accounts if row['due'] == due_soon]
        due_today = [row for row in accounts if row['due'] == today]
        overdue = [row for row in accounts if row['due'] < today]
        if upcoming:
            events.append(('upcoming', due_soon, upcoming, "To'lov muddati yaqinlashmoqda"))
        if due_today:
            events.append(('due', today, due_today, "Bugun to'lov muddati"))
        if overdue:
            events.append(('overdue', today, overdue, "To'lov muddati o'tgan"))
        if not events:
            continue

        audience = Q(is_superuser=True)
        if student.receptionist_id:
            audience |= Q(receptionist_profile__pk=student.receptionist_id)
        users = [
            user for user in get_user_model().objects.filter(is_active=True).filter(audience).distinct()
            if has_capability(user, 'payments.view')
        ]
        if not users:
            continue

        for stage, event_date, rows, title in events:
            balance = sum((row['balance'] for row in rows), start=0)
            months = ', '.join(sorted({row['month'].strftime('%Y-%m') for row in rows}))
            group_name = student.group.name if student.group_id else 'Kurslar'
            body = (
                f"{student.name} | {group_name} | {months} | "
                f"Muddat: {event_date:%d.%m.%Y} | Qoldiq: {balance:,.0f} so'm"
            )
            key = f'payment:{student.pk}:{stage}:{event_date}'
            with transaction.atomic():
                created_users = []
                for user in users:
                    _, created = ReminderDispatch.objects.get_or_create(key=f'{key}:user:{user.pk}')
                    if created:
                        Notification.objects.create(
                            recipient=user, student=student, title=title,
                            message=body, type='debt',
                        )
                        created_users.append(user)
            if created_users:
                dispatched.append(student)
            if stage in ('due', 'overdue'):
                queue_staff_notifications(users, f'{title}\n{body}', key, student=student)

    return dispatched
