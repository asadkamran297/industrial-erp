"""What the purchase orders screen knows about an order beyond its own row.

An order's row is mostly not on the order: how much of it has arrived lives on
the lines, what has been invoiced lives on the lines too, and whether it is
late is the promised date read against today. All of that is worked out here, once, so
the view stays a view and the template only prints.
"""

from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.core.table_columns import Column, ColumnSet

from apps.core.constants import (
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_FULLY_INVOICED,
    STATUS_PARTIALLY_INVOICED,
    STATUS_REVERSED,
    STATUS_SUBMITTED,
)

ZERO = Decimal("0.00")

# The four states the screen sorts orders into, and what each one means in terms
# of the statuses actually stored. "Pending approval" is the draft state: an
# order nobody has committed to yet, which is exactly what raising it does.
TAB_ALL = "all"
TAB_PENDING = "pending"
TAB_OPEN = "open"
TAB_PARTIAL = "partial"
TAB_INVOICED = "invoiced"
TAB_CLOSED = "closed"

# Kept so anything still importing it by name does not break; the board no
# longer offers it, because there is no unbilled state left for it to mean.
TAB_UNBILLED = "unbilled"

TABS = (
    (TAB_ALL, "All"),
    (TAB_PENDING, "Awaiting approval"),
    (TAB_OPEN, "Awaiting invoice"),
    (TAB_PARTIAL, "Partly invoiced"),
    (TAB_INVOICED, "Fully invoiced"),
    (TAB_CLOSED, "Closed & cancelled"),
)

TAB_STATUSES = {
    TAB_PENDING: (STATUS_DRAFT,),
    TAB_OPEN: (STATUS_SUBMITTED,),
    TAB_PARTIAL: (STATUS_PARTIALLY_INVOICED,),
    TAB_INVOICED: (STATUS_FULLY_INVOICED,),
    # Both ways an order can stop early sit together: someone looking for an
    # order that is no longer running does not know, and should not have to
    # know, whether it was cancelled whole or given up on part way.
    TAB_CLOSED: (STATUS_CANCELLED, STATUS_CLOSED),
}

# An order still working its way through: committed, and not yet finished or
# abandoned. What "open" means everywhere on this screen.
LIVE_STATUSES = (STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED)


def outstanding_now(lines):
    """Quantity still genuinely expected across these lines.

    Reads ``qty_pending``, which is nil on a line somebody has already given
    up on, so a balance written off does not count as something left to write off.
    """
    return sum((line.qty_pending for line in lines), Decimal("0"))


def decorate(orders, today=None):
    """Hang everything the row needs off each order, in one pass.

    Every order handed in must already have its ``items`` and their
    ``items`` prefetched; nothing here goes back to the database, so a page of
    orders costs the same few queries however many rows it holds.
    """
    today = today or timezone.localdate()

    for order in orders:
        lines = list(order.items.all())
        order.line_count = len(lines)
        order.total_amount = sum((line.total_amount for line in lines), ZERO)

        ordered_qty = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
        received_qty = sum((line.qty_invoiced or Decimal("0") for line in lines), Decimal("0"))
        # Given up on rather than delivered. Shown separately because an order
        # that was closed nine tenths of the way through is not the same story
        # as one that arrived in full, and a bar at 100% would tell the second.
        order.short_closed_qty = sum(
            (line.qty_ordered - (line.qty_invoiced or Decimal("0"))
             for line in lines if line.closed), Decimal("0")
        )
        order.ordered_qty = ordered_qty
        order.received_qty = received_qty
        # Rounded to whole percent: this drives a bar, and half a percent of a
        # bar is not a thing anyone can see.
        order.received_percent = int(received_qty / ordered_qty * 100) if ordered_qty else 0

        # Which invoices drew this line down, and for how much. Held per line
        # because "how much of THIS is still to come" is the question the
        # expanded row is open to answer, and an order total cannot answer it.
        for line in lines:
            refs = []
            for invoice_line in line.invoice_lines.all():
                invoice = invoice_line.invoice
                # A withdrawn invoice drew nothing down. It is left off rather
                # than shown at zero: the quantity went back, and a row saying
                # otherwise is a row somebody has to reconcile by hand.
                if invoice.status == STATUS_REVERSED:
                    continue
                refs.append({
                    "pk": invoice.pk,
                    "number": invoice.invoice_num,
                    "supplier_ref": invoice.supplier_invoice_num,
                    "date": invoice.invoice_date,
                    "qty": invoice_line.quantity or ZERO,
                    "amount": invoice_line.amount or ZERO,
                })
            line.invoice_refs = sorted(refs, key=lambda ref: (ref["date"] or date.min, ref["number"]))
            # Worked out here rather than in the template: money multiplied in a
            # template goes through integer arithmetic and loses the paise.
            line.pending_value = (line.qty_pending * (line.rate or ZERO)).quantize(Decimal("0.01"))

        order.invoiced_qty = received_qty
        order.pending_qty = sum((line.qty_pending for line in lines), Decimal("0"))

        # Money, split by what has actually happened to the goods rather than by
        # the order's headline total. Three separate figures, because they
        # answer three different questions and adding the wrong one to a tile is
        # how a screen ends up claiming more is owed than was ever ordered.
        still_to_come = ZERO      # ordered, not yet arrived and still expected
        arrived_unbilled = ZERO   # ordered, no supplier bill against it yet
        for line in lines:
            rate = line.rate or Decimal("0")
            # ``qty_pending`` is nil on a line somebody closed short, so a
            # balance already written off does not keep money on the committed
            # tile that nobody expects to spend.
            still_to_come += (line.qty_pending * rate).quantize(Decimal("0.01"))
            # Ordered and not yet invoiced, at the rate that was agreed. The
            # invoice is the only thing that books goods in, so what an order
            # is waiting on is read straight off its own lines.
            arrived_unbilled += (line.qty_pending * rate).quantize(Decimal("0.01"))
        order.on_order_value = still_to_come
        order.unbilled_value = arrived_unbilled

        # Billed is read off the bills that were actually entered, not off a
        # typed-in invoice number. Part billed is worth seeing rather than
        # rounding away: it is a delivery somebody has been invoiced for twice
        # over, or once and not again.
        billed_units = sum((line.qty_invoiced or Decimal("0") for line in lines), Decimal("0"))
        ordered_units = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
        order.invoice_numbers = sorted(
            {invoice.supplier_invoice_num
             for invoice in order.invoices.all() if invoice.status != STATUS_REVERSED}
        )
        if not lines:
            order.billed_state = "none"
        elif billed_units <= Decimal("0.0005"):
            order.billed_state = "unbilled"
        elif billed_units + Decimal("0.0005") < ordered_units:
            order.billed_state = "partial"
        else:
            order.billed_state = "billed"

        # Whether anything can still be done to this order. A closed one is
        # read, not worked, and the row's action has to know that.
        order.is_live = order.status in LIVE_STATUSES
        order.is_closed_early = order.status in (STATUS_CANCELLED, STATUS_CLOSED)

        # How this order would be ended, if somebody ended it now. The two verbs
        # are not interchangeable and the wrong one is refused by the service:
        # nothing has arrived, so the whole thing is cancelled; something has,
        # so only the balance can be given up. The row needs to know which,
        # because it links straight to that panel on the order.
        if not order.is_live:
            order.end_action = ""
        elif received_qty > 0:
            order.end_action = "close-short" if outstanding_now(lines) else ""
        else:
            order.end_action = "cancel"

        # Goods that were promised by a date that has passed and are not all in.
        order.days_late = (
            (today - order.expected_date).days
            if order.expected_date and order.status in LIVE_STATUSES and order.expected_date < today
            else 0
        )

        # One action per row: the next thing this order is actually waiting for.
        if order.status == STATUS_DRAFT:
            order.next_action = "approve"
        elif order.is_closed_early:
            # Nothing is owed either way any more. The only move left is to
            # decide the closure was wrong, which belongs on the order itself.
            order.next_action = "reopen"
        elif order.unbilled_value:
            # A bill outranks chasing a late delivery: the goods are already in
            # the godown and the payable they created is not on the books yet.
            order.next_action = "bill"
        elif order.days_late:
            order.next_action = "chase"
        elif order.is_live and order.received_percent < 100:
            # Approved, on time, nothing in yet. The bill is what books the
            # goods in, so that is the action the row offers -- an approved
            # order that shows only "view" gives the person looking at it
            # nothing to do and no idea what is next.
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
        "closed_short_count": 0, "closed_short_value": ZERO,
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
        # Commitments deliberately given up on. Worth a figure of its own: a
        # mill that closes a fifth of its orders short every month has a
        # supplier problem nobody has said out loud yet.
        if order.status == STATUS_CLOSED:
            tiles["closed_short_count"] += 1
            tiles["closed_short_value"] += order.short_value or ZERO

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
    Column("received", "Progress",
           export=lambda o: f"{o.received_qty} of {o.ordered_qty} ({o.received_percent}%)"),
    Column("billed", "Invoices",
           export=lambda o: ", ".join(o.invoice_numbers) or BILLED_LABELS[o.billed_state]),
    Column("status", "Status", export=lambda o: o.get_status_display()),
    # Off by default: only a minority of orders end early, and the reason is
    # what somebody wants when they are looking at exactly those.
    Column("closed", "Closed because", default=False,
           export=lambda o: o.close_reason_label if o.close_reason else ""),
))


def visible_columns(session):
    return COLUMNS.visible(session)


def set_visible_columns(session, keys):
    COLUMNS.choose(session, keys)


def column_menu(session):
    return COLUMNS.menu(session)


def export_columns(session):
    return COLUMNS.exportable(session)


# ── Purchase invoices screen ───────────────────────────────────────────────
# Purchases entered straight off a supplier's bill, with no order raised first.
# The figures are added up from the lines rather than stored on the order, so
# the export asks the same questions of a row that the screen does.
PURCHASE_INVOICE_COLUMNS = ColumnSet("inventory.purchase_invoices", (
    Column("invoice_num", "Invoice #", locked=True, export=lambda o: o.invoice_num),
    Column("supplier_ref", "Supplier ref", export=lambda o: o.supplier_invoice_num or ""),
    Column("invoice_date", "Date", export=lambda o: o.invoice_date),
    Column("supplier", "Supplier", export=lambda o: o.supplier.name),
    Column("buyer", "Entered by", export=lambda o: (
        o.created_by.get_full_name() or o.created_by.username) if o.created_by else ""),
    Column("lines", "Items", export=lambda o: o.line_count),
    Column("quantity", "Quantity", export=lambda o: o.qty_total),
    # Which route the purchase came in by -- the one thing about it that still
    # varies now that every purchase is one document.
    Column("order", "Order", export=lambda o: (
        o.purchase_order.purchase_num if o.purchase_order_id else "Direct")),
    Column("status", "Status", export=lambda o: o.get_status_display()),
    Column("value", "Amount", export=lambda o: o.total_amount),
))


# ── Sale invoices screen ───────────────────────────────────────────────────
# The other direction: what went out, what it came to, and what is still owed
# for it. Declared here beside the purchase sets so the two registers cannot
# drift apart in what they call a column.
SALE_COLUMNS = ColumnSet("inventory.sale_invoices", (
    Column("sale_num", "Invoice #", locked=True, export=lambda o: o.sale_num),
    Column("invoice_num", "Reference", default=False, export=lambda o: o.invoice_num or ""),
    Column("sale_date", "Date", export=lambda o: o.sale_date),
    Column("customer", "Customer", export=lambda o: o.customer.customer_name if o.customer else "Walk-in"),
    Column("lines", "Items", export=lambda o: o.line_count),
    Column("quantity", "Quantity", export=lambda o: o.qty_total),
    Column("pay_mode", "Paid by", default=False, export=lambda o: o.get_pay_mode_display()),
    Column("paid", "Received", export=lambda o: o.total_paid),
    Column("balance", "Balance", export=lambda o: o.balance),
    Column("status", "Status", export=lambda o: o.state_label),
    Column("value", "Amount", export=lambda o: o.net_amount),
))


# ── Goods receipt screen ───────────────────────────────────────────────────
# Its own table, its own choice: the two screens list the same records but are
# read for different reasons, so what one person wants on show here is not what
# they want on the purchase orders board.
def linked_documents(order):
    """Everything raised off this order, as one row of links.

    An order is the head of a chain -- it is invoiced, and some of it may go
    back. The documents that exist are named; the ones that do not are absent,
    so the row states how far the order has got.
    """
    from django.urls import reverse

    from .models import PurchaseReturnMaster

    links = []

    for invoice in order.invoices.all():
        links.append({
            "kind": "Purchase Invoice",
            "label": invoice.invoice_num or invoice.supplier_invoice_num,
            "url": reverse("inventory:purchase_invoice_detail", args=[invoice.pk]),
            "new_tab": False,
            "dead": invoice.status == STATUS_REVERSED,
        })

    for entry in PurchaseReturnMaster.objects.filter(purchase_order=order).order_by("return_date", "pk"):
        links.append({
            "kind": "Purchase Return",
            "label": entry.return_num,
            "url": reverse("inventory:purchase_return_detail", args=[entry.pk]),
            "new_tab": False,
            "dead": entry.status == STATUS_REVERSED,
        })

    return links
