from decimal import Decimal, InvalidOperation

from django import template

from apps.access_control.selectors import user_has_permission
from apps.core.formatting import format_amount, format_date, format_qty

register = template.Library()


@register.filter(name="qty")
def qty(value):
    """Render a quantity with the app-wide fixed decimal precision."""
    return format_qty(value)


@register.filter(name="amount")
def amount(value):
    """Render an amount with thousands separators and fixed decimal precision."""
    return format_amount(value)


@register.filter(name="short_amount")
def short_amount(value):
    """An amount sized for a glance rather than for a ledger.

    A headline figure is read for its order of magnitude -- 28.5 M says what
    28,547,037.00 makes the reader count digits to work out. Anything under a
    lakh is left alone, because shortening it would lose more than it saves.
    """
    try:
        number = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return format_amount(value)

    sign = "-" if number < 0 else ""
    number = abs(number)
    for size, suffix in ((Decimal("10000000"), " Cr"), (Decimal("100000"), " Lac")):
        if number >= size:
            scaled = (number / size).quantize(Decimal("0.01"))
            # 3.00 Cr says nothing 3 Cr does not, so the zeros come off.
            text = f"{scaled:f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    return f"{sign}{format_amount(number)}"


@register.filter(name="dmy")
def dmy(value):
    """Render a date the way the business writes it: DD-MM-YYYY."""
    return format_date(value)


@register.simple_tag(takes_context=True)
def has_perm(context, code):
    """True when the current user holds ``code`` (or the ``*`` wildcard).

    Usage: ``{% has_perm "inventory.items.add" as can_add %}``.
    """
    request = context.get("request")
    if request is None:
        return False
    return user_has_permission(request.user, code)
