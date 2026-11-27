"""Synchronise editable account names and linked staff names."""
from django.core.exceptions import ObjectDoesNotExist


def staff_display_name(user):
    if not user or not user.is_authenticated:
        return ''
    for relation in ('teacher_profile', 'receptionist_profile'):
        try:
            profile = getattr(user, relation)
        except ObjectDoesNotExist:
            continue
        if profile.name.strip():
            return profile.name.strip()
    return user.get_full_name().strip() or user.get_username()


def staff_name_saved(sender, instance, raw=False, update_fields=None, using='default', **kwargs):
    if raw or not instance.user_id or (update_fields is not None and not {'name', 'user', 'user_id'}.intersection(update_fields)):
        return
    from django.contrib.auth import get_user_model
    parts = instance.name.strip().split(maxsplit=1)
    first, last = (parts[0][:150] if parts else ''), (parts[1][:150] if len(parts) > 1 else '')
    get_user_model().objects.using(using).filter(pk=instance.user_id).update(first_name=first, last_name=last)
    account = instance._state.fields_cache.get('user')
    if account is not None:
        account.first_name, account.last_name = first, last


def capture_account_name(sender, instance, raw=False, update_fields=None, using='default', **kwargs):
    instance._crm_name_changed = False
    if raw or not instance.pk or (update_fields is not None and not {'first_name', 'last_name'}.intersection(update_fields)):
        return
    old = sender.objects.using(using).filter(pk=instance.pk).values('first_name', 'last_name').first()
    instance._crm_name_changed = old is not None and (old['first_name'], old['last_name']) != (instance.first_name, instance.last_name)


def account_name_saved(sender, instance, raw=False, using='default', **kwargs):
    if raw or not getattr(instance, '_crm_name_changed', False):
        return
    from .models import Teacher, Receptionist
    name = instance.get_full_name().strip()
    if not name:
        return
    for model, relation in ((Teacher, 'teacher_profile'), (Receptionist, 'receptionist_profile')):
        model.objects.using(using).filter(user_id=instance.pk).update(name=name[:200])
        profile = instance._state.fields_cache.get(relation)
        if profile is not None:
            profile.name = name[:200]


def connect_name_signals():
    from django.contrib.auth import get_user_model
    from django.db.models.signals import post_save, pre_save
    from .models import Teacher, Receptionist
    for model in (Teacher, Receptionist):
        post_save.connect(staff_name_saved, sender=model, dispatch_uid=f'crm.name.{model._meta.label_lower}')
    pre_save.connect(capture_account_name, sender=get_user_model(), dispatch_uid='crm.name.user.before')
    post_save.connect(account_name_saved, sender=get_user_model(), dispatch_uid='crm.name.user.after')
