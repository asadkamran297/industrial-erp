from decimal import Decimal, InvalidOperation

# Application-wide quantity display precision. Change here to change everywhere.
QTY_DECIMALS = 2

# Application-wide amount display precision. Change here to change everywhere.
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
