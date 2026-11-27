"""Shared entry points for related pages; existing actions keep their own permissions."""
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.urls import reverse

from .permissions import has_capability


CENTERS = {
    'academic_center': {
        'label': 'Davomat va baholar', 'icon': 'fa-clipboard-check',
        'tabs': (
            ('attendance', 'Davomat', 'attendance_list', ('attendance.view',)),
            ('grades', 'Baholar', 'grade_list', ('grades.view',)),
        ),
        'prefixes': ('attendance_', 'take_attendance', 'grade_', 'take_grades'),
    },
    'staff_center': {
        'label': 'Xodimlar', 'icon': 'fa-users',
        'tabs': (
            ('teachers', "O'qituvchilar", 'teacher_list', ('teachers.view',)),
            ('receptionists', 'Retsepshen', 'receptionist_list', ('receptionists.view',)),
        ),
        'prefixes': ('teacher_', 'receptionist_list', 'receptionist_create', 'receptionist_edit', 'receptionist_delete'),
    },
    'learning_center': {
        'label': 'Kurslar va guruhlar', 'icon': 'fa-layer-group',
        'tabs': (
            ('groups', 'Guruhlar', 'group_list', ('groups.view',)),
            ('courses', 'Kurslar', 'course_list', ('courses.view',)),
        ),
        'prefixes': ('group_', 'course_'),
    },
    'salary_center': {
        'label': 'Oyliklar', 'icon': 'fa-wallet',
        'tabs': (
            ('teachers', "O'qituvchilar", 'salary_list', ('salary.teacher.view', 'salary.teacher_self.view')),
            ('receptionists', 'Retsepshen', 'receptionist_salary_list', ('salary.receptionist.view', 'salary.receptionist_self.view')),
        ),
        'prefixes': ('salary_list', 'receptionist_salary_list', 'calculate_salaries', 'update_salary_status',
                     'calculate_receptionist_salaries', 'receptionist_salary_toggle', 'receptionist_commissions'),
    },
}


def available_tabs(user, center):
    return [tab for tab in CENTERS[center]['tabs'] if any(has_capability(user, code) for code in tab[3])]


@login_required
def center_view(request, center):
    from . import views
    tabs = available_tabs(request.user, center)
    if not tabs:
        raise PermissionDenied('Bu bo‘lim uchun sizga ruxsat berilmagan.')
    selected = request.GET.get('tab', tabs[0][0])
    if selected not in {tab[0] for tab in CENTERS[center]['tabs']}:
        return HttpResponseBadRequest('Bo‘lim noto‘g‘ri tanlangan.')
    for key, label, view_name, capabilities in tabs:
        if key == selected:
            return getattr(views, view_name)(request)
    raise PermissionDenied('Bu bo‘lim uchun sizga ruxsat berilmagan.')


def center_context(request):
    match = getattr(request, 'resolver_match', None)
    name = (match.url_name or '') if match else ''
    # Match salary pages before receptionist prefixes.
    for center in ('academic_center', 'salary_center', 'staff_center', 'learning_center'):
        config = CENTERS[center]
        if name != center and not any(name.startswith(prefix) for prefix in config['prefixes']):
            continue
        tabs = available_tabs(request.user, center)
        if not tabs:
            return {}
        if name == center:
            selected = request.GET.get('tab', tabs[0][0])
        elif center == 'salary_center':
            selected = 'receptionists' if 'receptionist' in name else 'teachers'
        elif center == 'staff_center':
            selected = 'receptionists' if name.startswith('receptionist') else 'teachers'
        elif center == 'academic_center':
            selected = 'attendance' if 'attendance' in name else 'grades'
        else:
            selected = 'courses' if name.startswith('course') else 'groups'
        links = []
        for key, label, view_name, capabilities in tabs:
            query = {'tab': key}
            if center == 'salary_center' and request.GET.get('month'):
                query['month'] = request.GET['month']
            if center == 'academic_center':
                for field in ('group', 'teacher', 'date'):
                    if request.GET.get(field):
                        query[field] = request.GET[field]
            links.append({'label': label, 'active': key == selected, 'url': reverse(center) + '?' + urlencode(query)})
        return {'navigation_section': center, 'center_label': config['label'], 'center_icon': config['icon'], 'center_tabs': links}
    return {}
