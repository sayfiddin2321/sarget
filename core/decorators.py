"""Eski decorators moduli — endi core.permissions ga yo'naltiriladi (backward-compat)."""
from .permissions import admin_required


def role_required(required_role):
    return admin_required
