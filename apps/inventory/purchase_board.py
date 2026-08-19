"""What the purchase orders screen knows about an order beyond its own row.

An order's row is mostly not on the order: how much of it has arrived lives on
the lines, what has been billed lives on the receipts, and whether it is late is
the promised date read against today. All of that is worked out here, once, so
the view stays a view and the template only prints.
"""

from decimal import Decimal

from django.utils import timezone

from apps.core.constants import (
    STATUS_CANCELLED,
    STATUS_DRAFT,
    STATUS_FULLY_RECEIVED,
    STATUS_PARTIAL_RECEIVED,
    STATUS_RAISED,
)

ZERO = Decimal("0.00")

# The four states the screen sorts orders into, and what each one means in terms
# of the statuses actually stored. "Pending approval" is the draft state: an
# order nobody has committed to yet, which is exactly what raising it does.
TAB_ALL = "all"
TAB_PENDING = "pending"
TAB_OPEN = "open"
TAB_RECEIVED = "received"
TAB_CLOSED = "closed"

TABS = (
    (TAB_ALL, "All"),
    (TAB_PENDING, "Pending approval"),
    (TAB_OPEN, "Open"),
    (TAB_RECEIVED, "Received"),
    (TAB_CLOSED, "Closed"),
)

TAB_STATUSES = {
    TAB_PENDING: (STATUS_DRAFT,),
    TAB_OPEN: (STATUS_RAISED, STATUS_PARTIAL_RECEIVED),
    TAB_RECEIVED: (STATUS_FULLY_RECEIVED,),
    TAB_CLOSED: (STATUS_CANCELLED,),
}

# An order still working its way through: committed, and not yet finished or
# abandoned. What "open" means everywhere on this screen.
LIVE_STATUSES = (STATUS_RAISED, STATUS_PARTIAL_RECEIVED)


def decorate(orders, today=None):
    """Hang everything the row needs off each order, in one pass.

    Every order handed in must already have its ``items`` and their
    ``receipts`` prefetched; nothing here goes back to the database, so a page
    of orders costs the same few queries however many rows it holds.
    """
    today = today or timezone.localdate()

    for order in orders:
        lines = list(order.items.all())
        order.line_count = len(lines)
        order.total_amount = sum((line.total_amount for line in lines), ZERO)

        ordered_qty = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
        received_qty = sum((line.total_receive_qty or Decimal("0") for line in lines), Decimal("0"))
        order.ordered_qty = ordered_qty
        order.received_qty = received_qty
        # Rounded to whole percent: this drives a bar, and half a percent of a
        # bar is not a thing anyone can see.
        order.received_percent = int(received_qty / ordered_qty * 100) if ordered_qty else 0

        # What has arrived, and under which note. The last GRN is the one worth
        # showing: it is the most recent thing that happened to this order.
        receipts = [receipt for line in lines for receipt in line.receipts.all()]
        grns = [receipt.grn_number for receipt in receipts if receipt.grn_number]
        order.grn_number = grns[-1] if grns else ""

        # Billed is read off the receipts, because that is where the supplier's
        # invoice number is captured. Some receipts carrying one and some not is
        # a part-billed order, which is worth seeing rather than rounding away.
        invoices = {receipt.invoice_num for receipt in receipts if receipt.invoice_num}
        order.invoice_numbers = sorted(invoices)
        if not receipts:
            order.billed_state = "none"
        elif not invoices:
            order.billed_state = "unbilled"
        elif any(not receipt.invoice_num for receipt in receipts):
            order.billed_state = "partial"
        else:
            order.billed_state = "billed"

        # Goods that were promised by a date that has passed and are not all in.
        order.days_late = (
            (today - order.expected_date).days
            if order.expected_date and order.status in LIVE_STATUSES and order.expected_date < today
            else 0
        )

        # One action per row: the next thing this order is actually waiting for.
        if order.status == STATUS_DRAFT:
            order.next_action = "approve"
        elif order.days_late:
            order.next_action = "chase"
        elif received_qty > 0 and order.billed_state in ("unbilled", "partial"):
            order.next_action = "bill"
        else:
            order.next_action = "view"

    return orders


def summarise(orders, today=None):
    """The five tiles across the top, over whatever set is handed in.

    Read from decorated orders rather than from the database a second time, so
    a tile can never disagree with the rows underneath it.
    """
    today = today or timezone.localdate()
    decorate(orders, today=today)

    tiles = {
        "open_count": 0, "open_value": ZERO,
        "pending_count": 0, "pending_value": ZERO,
        "awaiting_count": 0, "awaiting_value": ZERO,
        "unbilled_count": 0, "unbilled_value": ZERO,
        "overdue_count": 0,
    }

    for order in orders:
        if order.status in LIVE_STATUSES:
            tiles["open_count"] += 1
            tiles["open_value"] += order.total_amount
            # Still owed by the supplier: ordered but not yet arrived.
            if order.received_percent < 100:
                tiles["awaiting_count"] += 1
                outstanding = Decimal(100 - order.received_percent) / Decimal(100)
                tiles["awaiting_value"] += (order.total_amount * outstanding).quantize(Decimal("0.01"))
        if order.status == STATUS_DRAFT:
            tiles["pending_count"] += 1
            tiles["pending_value"] += order.total_amount
        # Goods in, supplier's invoice not yet against them: a payable the books
        # do not know about yet.
        if order.received_qty > 0 and order.billed_state in ("unbilled", "partial"):
            tiles["unbilled_count"] += 1
            tiles["unbilled_value"] += order.total_amount
        if order.days_late:
            tiles["overdue_count"] += 1

    return tiles


# ── Columns ────────────────────────────────────────────────────────────────
# Which columns the table offers, in the order they are shown. ``locked`` ones
# are not on offer: the order number is what a row *is*, and the action button
# is the only thing on the row that does anything, so a screen without them is
# not a screen. ``export`` is what the column writes into a spreadsheet cell,
# so the file and the table can never drift apart.
COLUMNS = (
    {"key": "purchase_num", "label": "PO #", "locked": True,
     "export": lambda order: order.purchase_num},
    {"key": "purchase_date", "label": "Date",
     "export": lambda order: order.purchase_date},
    {"key": "supplier", "label": "Supplier",
     "export": lambda order: order.supplier.name},
    {"key": "buyer", "label": "Buyer",
     "export": lambda order: (order.created_by.get_full_name() or order.created_by.username) if order.created_by else ""},
    {"key": "expected", "label": "Expected",
     "export": lambda order: order.expected_date or ""},
    {"key": "value", "label": "PO Value",
     "export": lambda order: order.total_amount},
    {"key": "received", "label": "Received",
     "export": lambda order: f"{order.received_qty} of {order.ordered_qty} ({order.received_percent}%)"},
    {"key": "grn", "label": "GRN",
     "export": lambda order: order.grn_number},
    {"key": "billed", "label": "Billed",
     "export": lambda order: ", ".join(order.invoice_numbers) or BILLED_LABELS[order.billed_state]},
    {"key": "status", "label": "Status",
     "export": lambda order: order.get_status_display()},
    {"key": "actions", "label": "Actions", "locked": True, "export": None},
)

BILLED_LABELS = {"none": "", "unbilled": "Not billed", "partial": "Partial", "billed": ""}

COLUMN_KEYS = [column["key"] for column in COLUMNS]
LOCKED_KEYS = {column["key"] for column in COLUMNS if column.get("locked")}
# Buyer and GRN are off to begin with: both are worth having, neither is worth
# the width on a first look.
DEFAULT_HIDDEN = {"buyer", "grn"}

SESSION_KEY = "inventory.purchase_order_columns"


def visible_columns(session):
    """The column keys on show, as a set.

    Held in the session rather than in the database: which columns one person
    wants to look at is that person's business, and it should not change what
    anybody else sees.
    """
    stored = session.get(SESSION_KEY)
    if not isinstance(stored, list):
        return {key for key in COLUMN_KEYS if key not in DEFAULT_HIDDEN}
    chosen = {key for key in stored if key in COLUMN_KEYS}
    return chosen | LOCKED_KEYS


def set_visible_columns(session, keys):
    """Remember what to show. Locked columns go back in whatever was asked."""
    chosen = [key for key in COLUMN_KEYS if key in set(keys) or key in LOCKED_KEYS]
    session[SESSION_KEY] = chosen


def column_menu(session):
    """The columns as the settings menu needs them: label, state, and locked."""
    shown = visible_columns(session)
    return [
        {"key": column["key"], "label": column["label"],
         "locked": bool(column.get("locked")), "on": column["key"] in shown}
        for column in COLUMNS
    ]


def export_columns(session):
    """The visible columns that can be written to a cell, in table order."""
    shown = visible_columns(session)
    return [column for column in COLUMNS if column["key"] in shown and column["export"]]
