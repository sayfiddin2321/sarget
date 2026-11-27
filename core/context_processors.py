from .permissions import role_context, get_teacher, get_receptionist, CAPABILITIES, has_capability, visible_notifications
from .models import Notification, Branch
from .identity import staff_display_name


def role(request):
    ctx = role_context(getattr(request, 'user', None))
    user = getattr(request, 'user', None)
    ctx['account_display_name'] = staff_display_name(user)
    ctx['current_teacher'] = get_teacher(user)
    ctx['current_receptionist'] = get_receptionist(user)
    ctx['capabilities'] = {code.replace('.', '_'): has_capability(user, code) for code in CAPABILITIES}
    ctx['lead_branches'] = Branch.objects.all() if has_capability(user, 'leads.manage') else ()
    if user and user.is_authenticated:
        notifications = visible_notifications(user)
        ctx['unread_notifications'] = notifications.filter(is_read=False).count()
        ctx['recent_notifications'] = notifications.filter(is_read=False)[:10]
        ctx['notification_cursor'] = notifications.order_by('-pk').values_list('pk', flat=True).first() or 0
    else:
        ctx['unread_notifications'] = 0
        ctx['recent_notifications'] = ()
        ctx['notification_cursor'] = 0
    if user and user.is_authenticated:
        from .centers import center_context
        ctx.update(center_context(request))
    return ctx
