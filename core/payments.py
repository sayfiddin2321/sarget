"""Accept a browser submission once, including concurrent retries."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Payment


@transaction.atomic
def accept_payment(payment, submission_key=None, *, compare_paid_date=True):
    if submission_key is None:
        payment.save()
        return payment
    fields = ('student_id', 'enrollment_id', 'amount', 'month', 'paid_date',
              'payment_type', 'received_by_id', 'comment')
    defaults = {field: getattr(payment, field) for field in fields}
    saved, created = Payment.all_objects.get_or_create(submission_key=submission_key, defaults=defaults)
    if not created:
        compared = fields if compare_paid_date else tuple(field for field in fields if field != 'paid_date')
        if saved.voided_at or any(getattr(saved, field) != defaults[field] for field in compared):
            raise ValidationError("Bu so'rov avval boshqa to'lov uchun ishlatilgan. Yangi to'lov uchun sahifani qayta oching.")
    return saved
