from django import template
from django.utils.safestring import mark_safe
from datetime import date
from ..utils import get_groups_for_date

register = template.Library()
from decimal import Decimal


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def div(value, arg):
    try:
        arg = float(arg)
        if arg == 0:
            return 0
        return float(value) / arg
    except (ValueError, TypeError):
        return 0


@register.filter
def percent(value, total):
    try:
        total = float(total)
        if total == 0:
            return 0
        return round(float(value) / total * 100, 1)
    except (ValueError, TypeError):
        return 0


@register.filter
def currency(value):
    try:
        return f"{float(value):,.0f} so'm"
    except (ValueError, TypeError):
        return "0 so'm"


@register.filter
def absolute(value):
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return 0


@register.filter
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


@register.simple_tag
def debt_badge(months):
    if months <= 0:
        return mark_safe('<span style="color:var(--green);font-size:0.8rem"><i class="fas fa-check"></i></span>')
    color = 'var(--orange)' if months == 1 else 'var(--red)'
    bg = 'var(--orange-dim)' if months == 1 else 'var(--red-dim)'
    return mark_safe(f'<span style="background:{bg};color:{color};padding:2px 8px;border-radius:6px;font-size:0.75rem;font-weight:700">{months} oy</span>')


@register.filter
def groups_for_today(user):
    """Return active groups scheduled for today.

    Teachers see their own groups; other users see all active groups.
    Usage: `request.user|groups_for_today` in templates.
    """
    try:
        return get_groups_for_date(date.today(), user)
    except Exception:
        return []


@register.filter
def sum_attribute(iterable, attr_name):
    """Sum numeric attribute `attr_name` over an iterable (queryset or list)."""
    try:
        total = Decimal('0')
        for obj in iterable:
            val = getattr(obj, attr_name, 0)
            if val is None:
                continue
            try:
                total += Decimal(str(val))
            except Exception:
                try:
                    total += Decimal(int(val))
                except Exception:
                    continue
        return total
    except Exception:
        return Decimal('0')


@register.filter
def format_number(value):
    """Format number with thousand separators, no decimals."""
    try:
        return f"{float(value):,.0f}"
    except Exception:
        return "0"


@register.filter
def filter_by_status(iterable, status):
    """Return items from iterable where `status` attribute equals given status."""
    try:
        # If it's a Django queryset, use .filter
        qs = iterable
        if hasattr(qs, 'filter'):
            return qs.filter(status=status)
        # Fallback to iterable filtering
        return [item for item in iterable if getattr(item, 'status', None) == status]
    except Exception:
        return []


@register.filter
def map_attribute(iterable, attr_name):
    """Map attribute values from an iterable and return a JSON-like list string.

    Useful for Chart.js data attributes in templates: returns a JSON array string.
    """
    try:
        values = []
        for obj in iterable:
            # Support dict-like items
            if isinstance(obj, dict):
                val = obj.get(attr_name)
            else:
                val = getattr(obj, attr_name, None)
            # If value is date-like, format as 'YYYY-MM'
            try:
                from datetime import date, datetime
                if isinstance(val, (date, datetime)):
                    val = val.strftime('%Y-%m')
            except Exception:
                pass
            values.append(val)
        import json
        return json.dumps(values, default=str)
    except Exception:
        return '[]'


@register.filter
def get_item(mapping, key):
    """Template filter to safely get an item from a mapping by key.

    Usage: `mapping|get_item:some_key` (works with dicts, QueryDicts, lists)
    """
    try:
        if mapping is None:
            return None
        # dict-like
        if isinstance(mapping, dict):
            return mapping.get(key)
        # QueryDict or other objects with .get
        if hasattr(mapping, 'get'):
            try:
                return mapping.get(key)
            except Exception:
                pass
        # Try __getitem__ (lists, sequences)
        try:
            return mapping[key]
        except Exception:
            # try int conversion for numeric keys
            try:
                return mapping[int(key)]
            except Exception:
                return None
    except Exception:
        return None


register.filter('dict_get', get_item)


@register.simple_tag
def macro_detail(icon, title, value):
    """Render a small info row (icon, title, value). Returns empty string if value falsy."""
    if not value:
        return ''
    try:
        html = f'''<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
            <i class="{icon}" style="color:var(--accent);width:16px;margin-top:2px"></i>
            <div><div style="font-size:0.72rem;color:var(--text-muted)">{title}</div>
            <div style="font-size:0.875rem;font-weight:500">{value}</div></div>
        </div>'''
        return mark_safe(html)
    except Exception:
        return ''
