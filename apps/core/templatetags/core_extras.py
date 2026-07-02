from django import template

from apps.access_control.selectors import user_has_permission
from apps.core.formatting import format_qty

register = template.Library()


@register.filter(name="qty")
def qty(value):
    """Render a quantity with the app-wide fixed decimal precision."""
    return format_qty(value)


@register.simple_tag(takes_context=True)
def has_perm(context, code):
    """True when the current user holds ``code`` (or the ``*`` wildcard).

    Usage: ``{% has_perm "inventory.items.add" as can_add %}``.
    """
    request = context.get("request")
    if request is None:
        return False
    return user_has_permission(request.user, code)
