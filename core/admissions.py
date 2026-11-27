"""Shared admission filters for the list, export, and receptionist work queue."""
from django.db.models import Q
from django.utils import timezone

from .models import Lead


def work_leads(user):
    return Lead.objects.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True))


def filtered_leads(user, params):
    qs = Lead.objects.select_related('assigned_to', 'student')
    from .permissions import has_capability
    if params.get('archived') == '1' and has_capability(user, 'leads.archive'):
        qs = Lead.all_objects.filter(archived_at__isnull=False).select_related('assigned_to', 'student')
    from datetime import date
    for key, lookup in [('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte')]:
        try:
            value = date.fromisoformat(params.get(key, ''))
        except ValueError:
            continue
        qs = qs.filter(**{lookup: value})
    for key in ('source', 'channel'):
        if params.get(key):
            qs = qs.filter(**{key: params[key]})
    scope = params.get('scope', '')
    if scope == 'mine':
        qs = qs.filter(assigned_to=user)
    elif scope == 'unassigned':
        qs = qs.filter(assigned_to__isnull=True)
    elif scope == 'work':
        qs = qs.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True))
    status = params.get('status', '')
    if status:
        qs = qs.filter(status=status)
    term = params.get('q', '').strip()
    if term:
        qs = qs.filter(Q(name__icontains=term) | Q(phone__icontains=term) | Q(course__icontains=term))
    if params.get('due') == '1':
        qs = qs.filter(status='callback', follow_up_at__lte=timezone.now())
    elif params.get('due') == 'today':
        now = timezone.now()
        qs = qs.filter(status='callback', follow_up_at__gt=now, follow_up_at__date=timezone.localdate(now))
    return qs.order_by('-created_at', '-pk')


def receptionist_work(user, now=None):
    now = now or timezone.now()
    today = timezone.localdate(now)
    qs = work_leads(user)
    new = qs.filter(status='new').order_by('created_at', 'pk')
    due = qs.filter(status='callback', follow_up_at__lte=now).order_by('follow_up_at', 'pk')
    upcoming = qs.filter(status='callback', follow_up_at__gt=now, follow_up_at__date=today).order_by('follow_up_at', 'pk')
    return {
        'work_new': new[:10], 'work_due': due[:10], 'work_upcoming': upcoming[:10],
        'work_new_count': new.count(), 'work_due_count': due.count(),
        'work_upcoming_count': upcoming.count(),
    }
