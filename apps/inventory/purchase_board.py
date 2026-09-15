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

TAB_ALL = "all"
TAB_PENDING = "pending"
TAB_OPEN = "open"
TAB_PARTIAL = "partial"
TAB_INVOICED = "invoiced"
TAB_CLOSED = "closed"

TAB_UNBILLED = "unbilled"
TAB_LIVE = "live"
TAB_LIVE = "live"

TABS = (
    (TAB_LIVE, "Still expected"),
    (TAB_ALL, "All"),
    (TAB_PENDING, "Awaiting approval"),
    (TAB_OPEN, "Awaiting invoice"),
    (TAB_PARTIAL, "Partly invoiced"),
    (TAB_INVOICED, "Fully invoiced"),
    (TAB_CLOSED, "Closed & cancelled"),
)

TAB_STATUSES = {
    TAB_LIVE: (STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED),
    TAB_PENDING: (STATUS_DRAFT,),
    TAB_OPEN: (STATUS_SUBMITTED,),
    TAB_PARTIAL: (STATUS_PARTIALLY_INVOICED,),
    TAB_INVOICED: (STATUS_FULLY_INVOICED,),
    TAB_CLOSED: (STATUS_CANCELLED, STATUS_CLOSED),
}

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
        order.short_closed_qty = sum(
            (line.qty_ordered - (line.qty_invoiced or Decimal("0"))
             for line in lines if line.closed), Decimal("0")
        )
        order.ordered_qty = ordered_qty
        order.received_qty = received_qty
        order.received_percent = int(received_qty / ordered_qty * 100) if ordered_qty else 0

        for line in lines:
            refs = []
            for invoice_line in line.invoice_lines.all():
                invoice = invoice_line.invoice
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
            line.pending_value = (line.qty_pending * (line.rate or ZERO)).quantize(Decimal("0.01"))

        order.invoiced_qty = received_qty
        order.pending_qty = sum((line.qty_pending for line in lines), Decimal("0"))

        still_to_come = ZERO      # ordered, not yet arrived and still expected
        arrived_unbilled = ZERO   # ordered, no supplier bill against it yet
        for line in lines:
            rate = line.rate or Decimal("0")
            still_to_come += (line.qty_pending * rate).quantize(Decimal("0.01"))
            arrived_unbilled += (line.qty_pending * rate).quantize(Decimal("0.01"))
        order.on_order_value = still_to_come
        order.unbilled_value = arrived_unbilled

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

        order.is_live = order.status in LIVE_STATUSES
        order.is_closed_early = order.status in (STATUS_CANCELLED, STATUS_CLOSED)

        if not order.is_live:
            order.end_action = ""
        elif received_qty > 0:
            order.end_action = "close-short" if outstanding_now(lines) else ""
        else:
            order.end_action = "cancel"

        order.days_late = (
            (today - order.expected_date).days
            if order.expected_date and order.status in LIVE_STATUSES and order.expected_date < today
            else 0
        )

        if order.status == STATUS_DRAFT:
            order.next_action = "approve"
        elif order.is_closed_early:
            order.next_action = "reopen"
        elif order.unbilled_value:
            order.next_action = "bill"
        elif order.days_late:
            order.next_action = "chase"
        elif order.is_live and order.received_percent < 100:
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
            if order.received_percent < 100:
                tiles["awaiting_count"] += 1
                tiles["awaiting_value"] += order.on_order_value
        if order.status == STATUS_DRAFT:
            tiles["pending_count"] += 1
            tiles["pending_value"] += order.total_amount
            if not order.line_count:
                tiles["pending_empty"] += 1
        if order.unbilled_value:
            tiles["unbilled_count"] += 1
            tiles["unbilled_value"] += order.unbilled_value
        if order.days_late:
            tiles["overdue_count"] += 1
        if order.status == STATUS_CLOSED:
            tiles["closed_short_count"] += 1
            tiles["closed_short_value"] += order.short_value or ZERO

    return tiles


BILLED_LABELS = {"none": "", "unbilled": "Not invoiced", "partial": "Part invoiced", "billed": ""}

COLUMNS = ColumnSet("inventory.purchase_orders", (
    Column("purchase_num", "Order #", locked=True, export=lambda o: o.purchase_num),
    Column("purchase_date", "Date", export=lambda o: o.purchase_date),
    Column("supplier", "Supplier", export=lambda o: o.supplier.name),
    Column("buyer", "Raised by", default=False,
           export=lambda o: (o.created_by.get_full_name() or o.created_by.username) if o.created_by else ""),
    Column("expected", "Expected", export=lambda o: o.expected_date or ""),
    Column("value", "Order value", locked=True, export=lambda o: o.total_amount),
    Column("received", "Progress",
           export=lambda o: f"{o.received_qty} of {o.ordered_qty} ({o.received_percent}%)"),
    Column("billed", "Invoices",
           export=lambda o: ", ".join(o.invoice_numbers) or BILLED_LABELS[o.billed_state]),
    Column("status", "Status", export=lambda o: o.get_status_display()),
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


PURCHASE_INVOICE_COLUMNS = ColumnSet("inventory.purchase_invoices", (
    Column("invoice_num", "Invoice #", locked=True, export=lambda o: o.invoice_num),
    Column("supplier_ref", "Supplier ref", export=lambda o: o.supplier_invoice_num or ""),
    Column("invoice_date", "Date", export=lambda o: o.invoice_date),
    Column("supplier", "Supplier", export=lambda o: o.supplier.name),
    Column("buyer", "Entered by", export=lambda o: (
        o.created_by.get_full_name() or o.created_by.username) if o.created_by else ""),
    Column("lines", "Items", export=lambda o: o.line_count),
    Column("quantity", "Quantity", export=lambda o: o.qty_total),
    Column("order", "Order", export=lambda o: (
        o.purchase_order.purchase_num if o.purchase_order_id else "Direct")),
    Column("status", "Status", export=lambda o: o.get_status_display()),
    Column("value", "Amount", export=lambda o: o.total_amount),
))


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
