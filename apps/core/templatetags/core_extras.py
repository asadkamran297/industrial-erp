from django import template

from apps.core.formatting import format_qty

register = template.Library()


@register.filter(name="qty")
def qty(value):
    """Render a quantity with the app-wide fixed decimal precision."""
    return format_qty(value)
