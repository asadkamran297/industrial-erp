from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DATE_DISPLAY_FORMAT = "%d-%m-%Y"

QTY_DECIMALS = 2

AMOUNT_DECIMALS = 2


def format_qty(value):
    """Format a quantity value to the app-wide fixed decimal precision.

    Returns the original value untouched when it is not numeric so template
    rendering never breaks on empty/None cells.
    """
    if value is None or value == "":
        return value
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:.{QTY_DECIMALS}f}"


def format_amount(value):
    """Format an amount with thousands separators and fixed decimal precision.

    Returns the original value untouched when it is not numeric so template
    rendering never breaks on empty/None cells.
    """
    if value is None or value == "":
        return value
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:,.{AMOUNT_DECIMALS}f}"


def format_date(value, fmt=DATE_DISPLAY_FORMAT):
    """Format a date, datetime or ISO date string for display.

    Anything that is not a recognisable date is returned untouched, so a blank
    cell or a free-text value never breaks rendering.
    """
    if not value:
        return value
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        try:
            value = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return value
    return value.strftime(fmt)
