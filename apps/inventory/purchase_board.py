"""What the purchase orders screen knows about an order beyond its own row.

An order's row is mostly not on the order: how much of it has arrived lives on
the lines, what has been billed lives on the receipts, and whether it is late is
the promised date read against today. All of that is worked out here, once, so
the view stays a view and the template only prints.
"""

from decimal import Decimal

from django.utils import timezone

from apps.core.table_columns import Column, ColumnSet

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
TAB_UNBILLED = "unbilled"
TAB_CLOSED = "closed"

TABS = (
    (TAB_ALL, "All"),
    (TAB_PENDING, "Awaiting approval"),
    (TAB_OPEN, "Awaiting goods"),
    (TAB_RECEIVED, "Received"),
    (TAB_UNBILLED, "Received, not billed"),
    (TAB_CLOSED, "Cancelled"),
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

        # What has arrived, and under which note. The last goods receipt is the
        # one worth showing: it is the most recent thing that happened here.
        receipts = [receipt for line in lines for receipt in line.receipts.all()]
        grns = [receipt.grn_number for receipt in receipts if receipt.grn_number]
        order.grn_number = grns[-1] if grns else ""

        # Money, split by what has actually happened to the goods rather than by
        # the order's headline total. Three separate figures, because they
        # answer three different questions and adding the wrong one to a tile is
        # how a screen ends up claiming more is owed than was ever ordered.
        still_to_come = ZERO      # ordered, not yet arrived
        arrived_unbilled = ZERO   # arrived, no supplier invoice against it
        for line in lines:
            rate = line.rate or Decimal("0")
            still_to_come += (line.pending_receive_qty * rate).quantize(Decimal("0.01"))
            for receipt in line.receipts.all():
                if not receipt.invoice_num:
                    arrived_unbilled += ((receipt.quantity or Decimal("0")) * rate).quantize(Decimal("0.01"))
        order.on_order_value = still_to_come
        order.unbilled_value = arrived_unbilled

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
        "overdue_count": 0, "pending_empty": 0,
    }

    for order in orders:
        if order.status in LIVE_STATUSES:
            tiles["open_count"] += 1
            tiles["open_value"] += order.total_amount
            # Still owed by the supplier, priced line by line off what has not
            # arrived -- not a percentage of the headline total, which charges
            # the whole order to a tile about the quarter of it still missing.
            if order.received_percent < 100:
                tiles["awaiting_count"] += 1
                tiles["awaiting_value"] += order.on_order_value
        if order.status == STATUS_DRAFT:
            tiles["pending_count"] += 1
            tiles["pending_value"] += order.total_amount
            # A draft nobody has put lines on yet has no figure to show, and a
            # tile reading Rs 0.00 looks broken rather than empty.
            if not order.line_count:
                tiles["pending_empty"] += 1
        # Goods in with no supplier invoice against them: a payable the books do
        # not know about yet. Only the receipts that are actually unbilled
        # count, so a part-received order contributes only what turned up.
        if order.unbilled_value:
            tiles["unbilled_count"] += 1
            tiles["unbilled_value"] += order.unbilled_value
        if order.days_late:
            tiles["overdue_count"] += 1

    return tiles


# ── Columns ────────────────────────────────────────────────────────────────
# Declared once; the burger menu, the table and every export read from here.
BILLED_LABELS = {"none": "", "unbilled": "Not invoiced", "partial": "Part invoiced", "billed": ""}

COLUMNS = ColumnSet("inventory.purchase_orders", (
    Column("purchase_num", "Order #", locked=True, export=lambda o: o.purchase_num),
    Column("purchase_date", "Date", export=lambda o: o.purchase_date),
    Column("supplier", "Supplier", export=lambda o: o.supplier.name),
    # Worth having, not worth the width on a first look.
    Column("buyer", "Raised by", default=False,
           export=lambda o: (o.created_by.get_full_name() or o.created_by.username) if o.created_by else ""),
    Column("expected", "Expected", export=lambda o: o.expected_date or ""),
    Column("value", "Order value", locked=True, export=lambda o: o.total_amount),
    Column("received", "Received",
           export=lambda o: f"{o.received_qty} of {o.ordered_qty} ({o.received_percent}%)"),
    Column("grn", "Goods receipt", default=False, export=lambda o: o.grn_number),
    Column("billed", "Invoiced",
           export=lambda o: ", ".join(o.invoice_numbers) or BILLED_LABELS[o.billed_state]),
    Column("status", "Status", export=lambda o: o.get_status_display()),
))


def visible_columns(session):
    return COLUMNS.visible(session)


def set_visible_columns(session, keys):
    COLUMNS.choose(session, keys)


def column_menu(session):
    return COLUMNS.menu(session)


def export_columns(session):
    return COLUMNS.exportable(session)


# ── Goods receipt screen ───────────────────────────────────────────────────
# Its own table, its own choice: the two screens list the same records but are
# read for different reasons, so what one person wants on show here is not what
# they want on the purchase orders board.
GRN_COLUMNS = ColumnSet("inventory.grn", (
    Column("purchase_num", "Order #", locked=True, export=lambda o: o.purchase_num),
    Column("supplier", "Supplier", export=lambda o: o.supplier.name),
    Column("purchase_date", "Date", export=lambda o: o.purchase_date),
    Column("expected", "Expected", default=False, export=lambda o: o.expected_date or ""),
    Column("value", "Amount", export=lambda o: o.po_total),
    # Off by default: the balance already says what is outstanding, so the
    # quantity ordered is there for whoever wants to check the arithmetic.
    Column("ordered", "Total ordered", default=False, export=lambda o: o.ordered_total),
    Column("received", "Received", export=lambda o: o.received_total),
    Column("balance", "Balance", export=lambda o: o.balance_total),
    Column("status", "Status", export=lambda o: o.get_status_display()),
))
