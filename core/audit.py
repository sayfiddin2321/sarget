"""Record financial model changes from CRM, imports, commands and Django admin."""
import json
from contextvars import ContextVar
from django.core.serializers.json import DjangoJSONEncoder

actor_context = ContextVar('financial_audit_actor', default=None)


class AuditActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        actor = request.user if request.user.is_authenticated else None
        token = actor_context.set(actor)
        try:
            return self.get_response(request)
        finally:
            actor_context.reset(token)


def snapshot(instance):
    values = {field.attname: getattr(instance, field.attname) for field in instance._meta.concrete_fields}
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def capture_before(sender, instance, raw=False, **kwargs):
    if raw:
        return
    old = sender._base_manager.filter(pk=instance.pk).first() if instance.pk else None
    instance._financial_before = snapshot(old) if old else {}


def record_change(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    before = getattr(instance, '_financial_before', {})
    after = snapshot(instance)
    if before == after:
        return
    action = 'create' if created else 'update'
    if sender.__name__ == 'Payment' and after.get('voided_at') and not before.get('voided_at'):
        action = 'void'
    write_event(instance, action, before, after)


def record_delete(sender, instance, **kwargs):
    write_event(instance, 'delete', snapshot(instance), {})


def write_event(instance, action, before, after):
    from .models import FinancialAudit
    actor = actor_context.get()
    FinancialAudit.objects.create(
        entity=instance._meta.model_name, object_id=instance.pk, action=action,
        actor=actor, actor_name=actor.get_username() if actor else 'Tizim',
        before=before, after=after,
    )


def connect_signals():
    from django.db.models.signals import pre_save, post_save, pre_delete
    from .models import Payment, Expense, Salary, ReceptionistSalary, ReceptionistCommission, StudentTariff, Group, Refund, Enrollment
    from .billing import stop_deleted_group_tariffs
    pre_delete.connect(stop_deleted_group_tariffs, sender=Group, dispatch_uid='billing-group-delete')
    for model in (Payment, Expense, Salary, ReceptionistSalary, ReceptionistCommission, StudentTariff, Refund, Enrollment):
        pre_save.connect(capture_before, sender=model, dispatch_uid=f'audit-before-{model.__name__}')
        post_save.connect(record_change, sender=model, dispatch_uid=f'audit-after-{model.__name__}')
        pre_delete.connect(record_delete, sender=model, dispatch_uid=f'audit-delete-{model.__name__}')
