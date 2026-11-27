"""Keep the existing student card compatible with enrollment-based reports."""
from django.utils import timezone
from .models import Enrollment


def sync_primary_enrollment(student):
    current = Enrollment.objects.filter(student=student, is_primary=True).first()
    state = {'active': 'active', 'pending': 'planned', 'inactive': 'left', 'graduated': 'completed'}[student.status]
    if student.group_id and not student.group.is_active:
        state = 'completed'
    if current and current.group_id != student.group_id:
        current.is_primary = False
        current.status = 'left'
        current.ends_on = timezone.localdate()
        current.save(update_fields=['is_primary', 'status', 'ends_on'])
        current = None
    if not student.group_id:
        return
    if current is None:
        first = not Enrollment.objects.filter(student=student).exists()
        Enrollment.objects.create(
            student=student, group=student.group, is_primary=True, mirrors_student=True,
            status=state, starts_on=student.registration_date if first else timezone.localdate(),
            monthly_fee=student.group.monthly_fee * (100 - student.discount_percent) / 100,
            due_day=student.payment_due_day or student.registration_date.day,
        )
    elif current.status != state:
        current.status = state
        current.save(update_fields=['status'])
