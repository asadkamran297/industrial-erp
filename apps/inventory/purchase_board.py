"""What the purchase orders screen knows about an order beyond its own row.

An order's row is mostly not on the order: how much of it has arrived lives on
the lines, what has been billed lives on the receipts, and whether it is late is
the promised date read against today. All of that is worked out here, once, so
the view stays a view and the template only prints.
"""

from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.core.table_columns import Column, ColumnSet

from apps.core.constants import (
    STATUS_CANCELLED,
    STATUS_CLOSED_SHORT,
    STATUS_DRAFT,
    STATUS_FULLY_RECEIVED,
    STATUS_PARTIAL_RECEIVED,
    STATUS_RAISED,
    STATUS_REVERSED,
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
    (TAB_CLOSED, "Closed & cancelled"),
)

TAB_STATUSES = {
    TAB_PENDING: (STATUS_DRAFT,),
    TAB_OPEN: (STATUS_RAISED, STATUS_PARTIAL_RECEIVED),
    TAB_RECEIVED: (STATUS_FULLY_RECEIVED,),
    # Both ways an order can stop early sit together: someone looking for an
    # order that is no longer running does not know, and should not have to
    # know, whether it was cancelled whole or given up on part way.
    TAB_CLOSED: (STATUS_CANCELLED, STATUS_CLOSED_SHORT),
}

# An order still working its way through: committed, and not yet finished or
# abandoned. What "open" means everywhere on this screen.
LIVE_STATUSES = (STATUS_RAISED, STATUS_PARTIAL_RECEIVED)


def outstanding_now(lines):
    """Quantity still genuinely expected across these lines.

    Reads ``open_receive_qty``, so a balance somebody has already given up on
    does not count as something left to give up on.
    """
    return sum((line.open_receive_qty for line in lines), Decimal("0"))


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
        # Given up on rather than delivered. Shown separately because an order
        # that was closed nine tenths of the way through is not the same story
        # as one that arrived in full, and a bar at 100% would tell the second.
        order.short_closed_qty = sum(
            (line.pending_receive_qty for line in lines if line.closed), Decimal("0")
        )
        order.ordered_qty = ordered_qty
        order.received_qty = received_qty
        # Rounded to whole percent: this drives a bar, and half a percent of a
        # bar is not a thing anyone can see.
        order.received_percent = int(received_qty / ordered_qty * 100) if ordered_qty else 0

        # What has arrived, and under which note. The last goods receipt is the
        # one worth showing: it is the most recent thing that happened here.
        # Reversals and the receipts they cancelled are left out of every count
        # below -- the pair nets to nothing, and showing either would say goods
        # are in the godown that were taken back out.
        receipts = [
            receipt for line in lines for receipt in line.receipts.all()
            if not receipt.reversed and receipt.reversal_of_id is None
        ]
        grns = [receipt.grn_number for receipt in receipts if receipt.grn_number]
        order.grn_number = grns[-1] if grns else ""

        # The same, per line: which notes this particular item came in under.
        # One line can have several -- a delivery a week for a month is four --
        # so they are gathered rather than reduced to the last one. Grouped by
        # number and not by receipt, because one note covering three lines is
        # one note, and the row is naming the document, not the posting.
        for line in lines:
            under = {}
            for receipt in line.receipts.all():
                if receipt.reversed or receipt.reversal_of_id is not None:
                    continue
                number = receipt.grn_number or ""
                if not number:
                    continue
                held = under.setdefault(number, {"number": number, "qty": ZERO, "date": receipt.receive_date, "pks": []})
                held["qty"] += receipt.received_units
                held["pks"].append(str(receipt.pk))
                # The note is dated when it was booked in; where one number was
                # somehow used twice the later date is the one that holds.
                if receipt.receive_date and (not held["date"] or receipt.receive_date > held["date"]):
                    held["date"] = receipt.receive_date
            line.grn_refs = sorted(under.values(), key=lambda ref: (ref["date"] or date.min, ref["number"]))

        # Money, split by what has actually happened to the goods rather than by
        # the order's headline total. Three separate figures, because they
        # answer three different questions and adding the wrong one to a tile is
        # how a screen ends up claiming more is owed than was ever ordered.
        still_to_come = ZERO      # ordered, not yet arrived and still expected
        arrived_unbilled = ZERO   # arrived, no supplier bill against it
        for line in lines:
            rate = line.rate or Decimal("0")
            # ``open_receive_qty`` and not ``pending_receive_qty``: a balance
            # somebody closed short is not still to come, and leaving it in
            # here would keep money on the committed tile that nobody expects
            # to spend.
            still_to_come += (line.open_receive_qty * rate).quantize(Decimal("0.01"))
        for receipt in receipts:
            # At what the goods were actually taken into stock at, which is the
            # figure sitting in GRN Clearing waiting for a bill -- not the
            # order's rate, which is what was hoped for rather than what came.
            arrived_unbilled += (receipt.pending_bill_qty * receipt.landed_rate).quantize(Decimal("0.01"))
        order.on_order_value = still_to_come
        order.unbilled_value = arrived_unbilled

        # Billed is read off the bills that were actually entered, not off a
        # typed-in invoice number. Part billed is worth seeing rather than
        # rounding away: it is a delivery somebody has been invoiced for twice
        # over, or once and not again.
        billed_units = sum((receipt.billed_qty or Decimal("0") for receipt in receipts), Decimal("0"))
        received_units = sum((receipt.received_units for receipt in receipts), Decimal("0"))
        order.invoice_numbers = sorted(
            {bill.supplier_invoice_num for bill in order.bills.all() if bill.status != STATUS_REVERSED}
        )
        if not receipts:
            order.billed_state = "none"
        elif billed_units <= Decimal("0.0005"):
            order.billed_state = "unbilled"
        elif billed_units + Decimal("0.0005") < received_units:
            order.billed_state = "partial"
        else:
            order.billed_state = "billed"

        # Whether anything can still be done to this order. A closed one is
        # read, not worked, and the row's action has to know that.
        order.is_live = order.status in LIVE_STATUSES
        order.is_closed_early = order.status in (STATUS_CANCELLED, STATUS_CLOSED_SHORT)

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
            # Approved, on time, nothing arrived yet. The next thing anyone does
            # to this order is book goods in against it, so that is the action
            # the row offers -- an approved order that shows only "view" gives
            # the person looking at it nothing to do and no idea what is next.
            order.next_action = "receive"
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
        if order.status == STATUS_CLOSED_SHORT:
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
    Column("received", "Received",
           export=lambda o: f"{o.received_qty} of {o.ordered_qty} ({o.received_percent}%)"),
    Column("grn", "Goods receipt", default=False, export=lambda o: o.grn_number),
    Column("billed", "Invoiced",
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
    Column("purchase_num", "Invoice #", locked=True, export=lambda o: o.purchase_num),
    Column("supplier_ref", "Supplier ref", export=lambda o: o.quot_num or ""),
    Column("purchase_date", "Date", export=lambda o: o.purchase_date),
    Column("supplier", "Supplier", export=lambda o: o.supplier.name),
    Column("buyer", "Entered by", export=lambda o: (
        o.created_by.get_full_name() or o.created_by.username) if o.created_by else ""),
    Column("lines", "Items", export=lambda o: o.line_count),
    Column("quantity", "Quantity", export=lambda o: o.qty_total),
    Column("bill", "Bill", export=lambda o: o.bill.bill_num if o.bill else "Not billed"),
    Column("value", "Amount", export=lambda o: o.total_amount),
))


# ── Goods receipt screen ───────────────────────────────────────────────────
# Its own table, its own choice: the two screens list the same records but are
# read for different reasons, so what one person wants on show here is not what
# they want on the purchase orders board.
def receipt_state(receipt):
    """What a goods receipt row is: one of four states, named once.

    Read off the receipt itself rather than off a text invoice number, so a
    receipt billed in two instalments is still "part billed" and a reversed one
    says so instead of quietly counting as goods in hand.
    """
    if receipt.reversed:
        return "reversed", "Reversed"
    if receipt.reversal_of_id:
        return "reversal", "Reversal"
    if receipt.pending_bill_qty:
        if receipt.billed_qty:
            return "part_billed", "Part billed"
        return "unbilled", "Not billed"
    return "billed", "Billed"


# The goods receipt register: one row per receipt, not per order. The screen is
# a list of what actually came through the gate, so the row's identity is the
# note it came in under.
GRN_COLUMNS = ColumnSet("inventory.grn.receipts", (
    Column("grn_number", "GRN #", locked=True, export=lambda r: r.grn_number),
    Column("purchase_num", "PO #", export=lambda r: r.purchase_num),
    Column("supplier", "Supplier", export=lambda r: r.purchase_order_item.purchase_order.supplier.name),
    Column("item", "Item", export=lambda r: r.descr),
    Column("receive_date", "Receive date", export=lambda r: r.receive_date),
    Column("quantity", "Qty", export=lambda r: r.received_units),
    Column("retail_price", "Retail price", export=lambda r: r.retail_price),
    # Off by default: what the goods came in at is what the bill is matched
    # against -- worth having, not worth the width by default.
    Column("landed", "Landed amount", default=False, export=lambda r: r.landed_amount),
    Column("invoice", "Invoice #", default=False, export=lambda r: r.invoice_num),
    Column("status", "Status", export=lambda r: receipt_state(r)[1]),
))


def linked_documents(order):
    """Everything raised off this order, as one row of links.

    An order is the head of a chain -- goods arrive under a note, the note is
    billed, some of it may go back. The documents that exist are named; the
    ones that do not are absent, so the row states how far the order has got.
    """
    from django.urls import reverse

    from .models import PurchaseReturnMaster

    links = []

    # One entry per note rather than per posting: a note covering four lines is
    # one document. A reversed receipt stays, greyed -- it happened, and the
    # entry cancelling it sits next to it.
    notes = {}
    for line in order.items.all():
        for receipt in line.receipts.all():
            number = receipt.grn_number or ""
            if not number:
                continue
            held = notes.setdefault(number, {"pks": [], "date": receipt.receive_date, "dead": True})
            held["pks"].append(str(receipt.pk))
            if receipt.receive_date and (not held["date"] or receipt.receive_date > held["date"]):
                held["date"] = receipt.receive_date
            if not receipt.reversed and receipt.reversal_of_id is None:
                held["dead"] = False
    for number, note in sorted(notes.items(), key=lambda pair: (pair[1]["date"] or date.min, pair[0])):
        links.append({
            "kind": "GRN",
            "label": number,
            # The note's own page, not a print sheet: a link in a chain is
            # followed to read the document, and printing it is a choice made
            # once it is open.
            "url": reverse("inventory:grn_detail", args=[number]),
            "new_tab": False,
            "dead": note["dead"],
        })

    for bill in order.bills.all():
        links.append({
            "kind": "Purchase Bill",
            "label": bill.bill_num or bill.supplier_invoice_num,
            "url": reverse("inventory:purchase_bill_detail", args=[bill.pk]),
            "new_tab": False,
            "dead": bill.status == STATUS_REVERSED,
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
