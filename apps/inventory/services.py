from decimal import Decimal, ROUND_HALF_UP

_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _three_digits(n):
    parts = []
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10])
        n %= 10
    if n:
        parts.append(_ONES[n])
    return " ".join(parts)


def _indian_words(n):
    if n <= 0:
        return ""
    if n < 1000:
        return _three_digits(n)
    if n < 100000:
        return (_three_digits(n // 1000) + " Thousand " + _indian_words(n % 1000)).strip()
    if n < 10000000:
        return (_three_digits(n // 100000) + " Lac " + _indian_words(n % 100000)).strip()
    return (_indian_words(n // 10000000) + " Crore " + _indian_words(n % 10000000)).strip()


def amount_in_words(amount):
    n = int(Decimal(amount or 0))
    if n == 0:
        return "Zero Only"
    return _indian_words(n) + " Only"


from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.constants import CONF_PO_APPROVAL_LIMIT_DEFAULT, CONF_PO_APPROVAL_LIMIT_KEY, INV_BILL_MATCH_TOLERANCE_PERCENT, INV_PO_CANCEL_REASONS, INV_PO_CLOSE_SHORT_REASONS, INV_ORDER_OPEN_STATUSES, INV_REVERSAL_REASONS, INVENTORY_KIND_PRODUCT, LEDGER_ADJUSTMENT, LEDGER_OPENING, LEDGER_PURCHASE_RETURN, LEDGER_RECEIVE, LEDGER_REVERSAL, LEDGER_SALE, LEDGER_SALE_RETURN, NO, STATUS_ACTIVE, STATUS_CANCELLED, STATUS_CLOSED, STATUS_DRAFT, STATUS_FULLY_INVOICED, STATUS_PARTIALLY_INVOICED, STATUS_PARTIAL_RETURNED, STATUS_POSTED, STATUS_SUBMITTED, STATUS_RETURNED, STATUS_REVERSED, YES

TWO_DP = Decimal("0.01")
FOUR_DP = Decimal("0.0001")

from .models import (
    ItemLedger,
    SalesOrder,
    SalesOrderItem,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    ManualTransaction,
    POSDetail,
    POSMaster,
    POSReturnMaster,
    PurchaseMaster,
    PurchaseMasterReturn,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReturnMaster,
    Stock,
    UOMConversion,
)


def generate_transaction_id(prefix: str, model):
    last = model.all_objects.order_by("-id").values_list("id", flat=True).first() or 0
    return f"{prefix}-{timezone.now():%Y%m%d}-{last + 1:06d}"


def create_ledger_entry(*, stock, inventory_item, transaction_id, transaction_no, transaction_type, transaction_date, ref_table, ref_id, ref_no, quantity, old_quantity, new_quantity, old_price, current_price, remarks, user):
    ItemLedger.objects.create(
        transaction_id=transaction_id,
        transaction_no=transaction_no,
        inventory_item=inventory_item,
        item_code=inventory_item.code,
        item_name=inventory_item.item_name,
        transaction_type=transaction_type,
        transaction_date=transaction_date,
        ref_table=ref_table,
        ref_id=ref_id,
        ref_no=ref_no,
        quantity=quantity,
        old_quantity=old_quantity,
        new_quantity=new_quantity,
        old_price=old_price,
        current_price=current_price,
        remarks=remarks,
        status=stock.status,
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def set_opening_stock(*, inventory_item, quantity, price, opening_date, user):
    """Record the stock an item already had when it was put on the system.

    Written the same way a stock adjustment is — the Stock row moves and an
    ItemLedger row records the movement — so the opening figure is auditable
    rather than a quantity that simply appeared. The Inventory control account
    is brought in line from the Inventory Valuation screen, which is how every
    other stock movement outside a goods receipt reaches the general ledger.
    """
    if quantity is None or quantity <= 0:
        return None

    stock = Stock.objects.select_for_update().get(inventory_item=inventory_item)
    old_quantity = stock.current_quantity
    old_price = stock.current_price
    if old_quantity:
        raise ValidationError("Opening stock can only be set while the item has no stock movement.")

    unit_price = (price or Decimal("0.00")).quantize(Decimal("0.01"))
    stock.last_price = old_price
    stock.current_price = unit_price
    stock.current_quantity = quantity
    stock.updated_by = user
    stock.save(update_fields=["last_price", "current_price", "current_quantity", "updated_by", "updated_at"])

    transaction_id = generate_transaction_id("OPEN", ItemLedger)
    create_ledger_entry(
        stock=stock,
        inventory_item=inventory_item,
        transaction_id=transaction_id,
        transaction_no=transaction_id,
        transaction_type=LEDGER_OPENING,
        transaction_date=opening_date,
        ref_table="inv_inventory_codes",
        ref_id=inventory_item.pk,
        ref_no=inventory_item.code,
        quantity=quantity,
        old_quantity=old_quantity,
        new_quantity=quantity,
        old_price=old_price,
        current_price=unit_price,
        remarks="Opening stock",
        user=user,
    )
    return stock


@transaction.atomic
def finalize_manual_transaction(*, transaction_id, user):
    rows = list(ManualTransaction.objects.select_related("inventory_item").filter(transaction_id=transaction_id, status=STATUS_DRAFT, selected=YES))
    if not rows:
        raise ValidationError("No selected draft entries to submit. Toggle at least one entry on.")

    today = timezone.localdate()
    for row in rows:
        stock = Stock.objects.select_for_update().get(inventory_item=row.inventory_item)
        old_quantity = stock.current_quantity
        old_price = stock.current_price
        new_quantity = old_quantity + row.qty
        if new_quantity > 0:
            weighted_price = ((old_quantity * old_price) + (row.qty * row.price)) / new_quantity
        else:
            weighted_price = row.price
        weighted_price = weighted_price.quantize(Decimal("0.01"))

        stock.last_price = old_price
        stock.current_price = weighted_price
        stock.current_quantity = new_quantity
        stock.updated_by = user
        stock.save(update_fields=["last_price", "current_price", "current_quantity", "updated_by", "updated_at"])

        create_ledger_entry(stock=stock, inventory_item=row.inventory_item, transaction_id=transaction_id, transaction_no=transaction_id, transaction_type=LEDGER_ADJUSTMENT, transaction_date=today, ref_table="inv_manual_transaction", ref_id=row.pk, ref_no=transaction_id, quantity=row.qty, old_quantity=old_quantity, new_quantity=new_quantity, old_price=old_price, current_price=weighted_price, remarks=row.descr, user=user)

        row.status = STATUS_SUBMITTED
        row.updated_by = user
        row.save(update_fields=["status", "updated_by", "updated_at"])
    return len(rows)


def _fits(quantity, rate):
    """A converted quantity and rate, cut to what the columns actually hold.

    Dividing by a conversion factor gives whatever precision Decimal feels
    like -- 10 bags in kilos at a factor of 3 is 3.333... to twenty-seven
    places -- and the line refuses to save, because the columns are four
    places and two. Even a factor that divides cleanly overshoots: a rate
    multiplied by 20.0000 keeps the four places the factor was stored with.
    So the figures are rounded here, at the point of conversion, rather than
    reaching a model that can only reject them.
    """
    return quantity.quantize(FOUR_DP, rounding=ROUND_HALF_UP), rate.quantize(TWO_DP, rounding=ROUND_HALF_UP)


def to_base_unit(*, item, uom, quantity, rate):
    """A quantity and rate bought in one unit, restated in the item's own unit.

    Stock, the item ledger and the general ledger are all kept in the item's
    base unit, so a bill written in kilos for something stocked in bags is
    converted here rather than each reader having to know the difference. The
    amount is unchanged by the move: fewer bags at a higher rate per bag comes
    to the same money as more kilos at the rate per kilo.
    """
    base = item.uom
    if not uom or not base or uom.pk == base.pk:
        return quantity, rate

    # 1 base = factor picked  ->  the picked unit is the smaller of the two.
    down = UOMConversion.objects.filter(uom_from=base, uom_to=uom, status=STATUS_ACTIVE).first()
    if down and down.conversion_factor:
        factor = Decimal(down.conversion_factor)
        return _fits(quantity / factor, rate * factor)

    # 1 picked = factor base  ->  the picked unit is the larger of the two.
    up = UOMConversion.objects.filter(uom_from=uom, uom_to=base, status=STATUS_ACTIVE).first()
    if up and up.conversion_factor:
        factor = Decimal(up.conversion_factor)
        return _fits(quantity * factor, rate / factor)

    raise ValidationError(
        f"{item.item_name} is stocked in {base.title}, and there is no conversion "
        f"between {uom.title} and {base.title}. Set one up, or enter the line in {base.title}."
    )


def next_purchase_order_number():
    """What the next purchase order will be called; advisory, like the bill one."""
    last = PurchaseOrder.all_objects.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
    return f"PO-{last + 1}"


@transaction.atomic
def create_purchase_order(*, supplier, quot_num, quot_date, order_date, lines, expected_date=None,
                          discount_amount=Decimal("0"), tax_amount=Decimal("0"),
                          remarks="", status=STATUS_SUBMITTED, extra_data=None, user):
    """An order raised on a supplier: goods asked for, none of them here yet.

    Same entry shape as ``create_purchase_invoice`` so both purchase screens read
    alike, but nothing is received: stock, the item ledger and the general
    ledger stay untouched until the goods arrive through the receive screen.

    ``lines`` is a list of dicts: inventory_item, quantity, rate, an optional
    uom the line was written in, and an optional descr.
    """
    if not supplier:
        raise ValidationError("Pick a supplier.")

    clean_lines = [line for line in lines if line.get("inventory_item") and line.get("quantity")]
    if not clean_lines:
        raise ValidationError("Add at least one item with a quantity.")

    order = PurchaseOrder.objects.create(
        supplier=supplier,
        purchase_date=order_date,
        status=status,
        quot_num=quot_num or "",
        quot_date=quot_date or None,
        expected_date=expected_date or None,
        # Every document says what it is for. Where nobody wrote a narration
        # the obvious one is written for them, so a printed order is never
        # blank where the reader expects a sentence.
        descr=(remarks or "").strip() or f"Purchase order to {supplier.name}",
        # Whatever the site added to its own form; nothing here reads it.
        extra_data=extra_data or {},
        created_by=user,
        updated_by=user,
    )

    # One discount typed at the foot is spread over the lines by their share of
    # the goods, so the order's own lines still add up to what was agreed.
    goods_total = Decimal("0.00")
    prepared = []
    for line in clean_lines:
        quantity = Decimal(line["quantity"])
        rate = Decimal(line.get("rate") or 0)
        if quantity <= 0:
            raise ValidationError("Every line needs a quantity greater than zero.")
        item = line["inventory_item"]
        quantity, rate = to_base_unit(item=item, uom=line.get("uom"), quantity=quantity, rate=rate)
        amount = (quantity * rate).quantize(Decimal("0.01"))
        goods_total += amount
        prepared.append((item, quantity, rate, amount, line.get("descr")))

    discount = Decimal(discount_amount or 0).quantize(Decimal("0.01"))
    if discount > goods_total:
        raise ValidationError("Discount cannot be more than the order total.")

    spread = Decimal("0.00")
    for seq, (item, quantity, rate, amount, descr) in enumerate(prepared, start=1):
        if seq == len(prepared):
            # The last line carries whatever rounding the split left over, so
            # the discounts on the lines add back to the one that was typed.
            share = discount - spread
        else:
            share = (discount * amount / goods_total).quantize(Decimal("0.01")) if goods_total else Decimal("0.00")
            spread += share
        PurchaseOrderItem.objects.create(
            purchase_order=order,
            seq_num=seq,
            purchase_num=order.purchase_num,
            purchase_date=order.purchase_date,
            inventory_item=item,
            quantity=quantity,
            rate=rate,
            unit_rate=rate,
            uom=item.uom,
            discount_amount=share,
            descr=(descr or item.item_name)[:255],
            created_by=user,
            updated_by=user,
        )

    net_amount = (goods_total - discount + Decimal(tax_amount or 0)).quantize(Decimal("0.01"))

    # The approval limit bites here, not on the button. Whoever raised the
    # order does not get to decide whether it needed signing off, so an order
    # asked for as raised drops back to draft when it is worth more than the
    # buyer may commit -- and stays there until someone with the right releases
    # it. Setting the status straight to raised in a form post is exactly the
    # gap this closes.
    committed = (goods_total - discount).quantize(Decimal("0.01"))
    if order.status == STATUS_SUBMITTED:
        if needs_approval(committed) and not user_can_approve(user):
            order.status = STATUS_DRAFT
        else:
            order.approved_by = user
            order.approved_at = timezone.now()
            order.approved_amount = committed
        order.save(update_fields=["status", "approved_by", "approved_at", "approved_amount", "updated_at"])

    return order, net_amount


def next_sale_invoice_number():
    """What the next sale invoice will be called; advisory, like the purchase one."""
    last = POSMaster.all_objects.order_by("-sale_seq_num").values_list("sale_seq_num", flat=True).first() or 0
    return f"SAL-{last + 1}"


@transaction.atomic
# ── The sales order ─────────────────────────────────────────────────────────
# The mirror of the purchase side, written the same way on purpose: an order
# states intent and moves nothing, the invoice is the event.


def next_sales_order_number():
    """What the next sales order will be called; advisory, like the others."""
    last = (
        SalesOrder.all_objects.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
    )
    return f"SO-{last + 1:06d}"


def open_sales_order_lines(*, customer=None, sales_order=None):
    """Order lines still open to be invoiced."""
    rows = (
        SalesOrderItem.objects
        .select_related("sales_order__customer", "inventory_item", "uom")
        .filter(sales_order__status__in=INV_ORDER_OPEN_STATUSES)
    )
    if customer is not None:
        rows = rows.filter(sales_order__customer=customer)
    if sales_order is not None:
        rows = rows.filter(sales_order=sales_order)
    return [
        row for row in rows.order_by("sales_order__order_date", "sales_order_id", "seq_num")
        if row.qty_pending > FOUR_DP
    ]


def customer_has_open_orders(*, customer):
    """Whether the sale invoice screen should offer orders to pull lines from.

    Offered, not demanded. A customer standing at the counter buying something
    off the shelf is a real sale even when an order of theirs is open
    elsewhere, and refusing it would stop the till.
    """
    if customer is None:
        return False
    return bool(open_sales_order_lines(customer=customer))


@transaction.atomic
def create_sales_order(*, customer, order_date=None, lines, expected_date=None,
                       customer_ref="", remarks="", status=STATUS_DRAFT, user):
    """Raise an order on a customer. Nothing is committed to the books by it."""
    if not customer:
        raise ValidationError("Pick a customer.")

    clean = [
        line for line in lines
        if line.get("inventory_item") and Decimal(line.get("quantity") or 0) > 0
    ]
    if not clean:
        raise ValidationError("Add at least one item with a quantity.")

    order = SalesOrder.objects.create(
        customer=customer,
        order_date=order_date or timezone.localdate(),
        expected_date=expected_date or None,
        customer_ref=(customer_ref or "").strip(),
        status=status,
        remarks=remarks or "",
        created_by=user,
        updated_by=user,
    )

    total = Decimal("0.00")
    for seq, line in enumerate(clean, start=1):
        item = line["inventory_item"]
        quantity, rate = to_base_unit(
            item=item, uom=line.get("uom"),
            quantity=Decimal(line["quantity"]), rate=Decimal(line.get("rate") or 0),
        )
        SalesOrderItem.objects.create(
            sales_order=order,
            seq_num=seq,
            inventory_item=item,
            descr=(line.get("descr") or item.item_name)[:255],
            quantity=quantity,
            rate=rate,
            uom=item.uom,
            tax_perc=Decimal(line.get("tax_perc") or 0),
            discount_amount=Decimal(line.get("discount_amount") or 0),
            created_by=user,
            updated_by=user,
        )
        total += (quantity * rate).quantize(TWO_DP)
    return order, total


@transaction.atomic
def submit_sales_order(*, order, user):
    """Commit to the order, so it starts showing on the invoice screen."""
    order = SalesOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != STATUS_DRAFT:
        raise ValidationError("Only a draft order can be submitted.")
    if not order.items.exists():
        raise ValidationError("An order with no lines cannot be submitted.")
    order.status = STATUS_SUBMITTED
    order.updated_by = user
    order.save(update_fields=["status", "updated_by", "updated_at"])
    return order


@transaction.atomic
def close_sales_order(*, order, reason, remarks="", user):
    """Stop an order early. The balance on it is given up on, not shipped."""
    order = SalesOrder.objects.select_for_update().get(pk=order.pk)
    if order.is_closed:
        raise ValidationError("This order has already finished.")
    if not reason:
        raise ValidationError(
            "Closing an order needs a reason - 'closed' on its own tells the next reader nothing."
        )
    order.status = STATUS_CLOSED
    order.close_reason = reason
    order.close_remarks = remarks or ""
    order.closed_on = timezone.localdate()
    order.closed_by = user
    order.updated_by = user
    order.save()
    return order


def _refresh_sales_order_status(order, *, user=None):
    """Move a sales order along to whatever its own lines now say it is."""
    if order is None:
        return None
    order = SalesOrder.objects.prefetch_related("items").get(pk=order.pk)
    status = order.invoiced_status()
    if status == order.status:
        return order
    order.status = status
    order.updated_by = user
    order.save(update_fields=["status", "updated_by", "updated_at"])
    return order


def create_direct_sale(*, customer, sale_date, lines, discount_amount=Decimal("0"),
                       tax_amount=Decimal("0"), paid_amount=Decimal("0"), remarks="", user):
    """A sale entered as an invoice, posted the moment it is saved.

    The counterpart of ``create_purchase_invoice``: the same shape of entry, and
    it runs through ``post_sale()`` so stock, the item ledger and the general
    ledger move exactly as they do for a sale rung up on the POS screen.

    ``lines`` is a list of dicts: inventory_item, quantity, price, and an
    optional uom the line was written in.
    """
    if not customer:
        raise ValidationError("Pick a customer.")

    clean_lines = [line for line in lines if line.get("inventory_item") and line.get("quantity")]
    if not clean_lines:
        raise ValidationError("Add at least one item with a quantity.")

    # Lines pulled off a sales order carry it; typed lines do not. What is
    # invoiced against an order line is bounded by what is still open on it.
    touched_orders = {}
    for line in clean_lines:
        order_item = line.get("order_item")
        if order_item is None:
            continue
        order_item = SalesOrderItem.objects.select_for_update().select_related(
            "sales_order"
        ).get(pk=order_item.pk)
        if order_item.sales_order.customer_id != customer.pk:
            raise ValidationError(
                f"{order_item.sales_order.order_num} was raised on a different customer."
            )
        quantity = Decimal(line["quantity"])
        if quantity > order_item.qty_pending + FOUR_DP:
            raise ValidationError(
                f"{order_item.sales_order.order_num} line {order_item.seq_num} has only "
                f"{order_item.qty_pending} left to invoice; this invoice is asking for {quantity}."
            )
        line["_locked_order_item"] = order_item
        touched_orders[order_item.sales_order_id] = order_item.sales_order

    sale = POSMaster.objects.create(
        transaction_id=generate_transaction_id("SAL", POSMaster),
        sale_date=sale_date,
        customer=customer,
        sales_order=list(touched_orders.values())[0] if len(touched_orders) == 1 else None,
        remarks=remarks or "",
        created_by=user,
        updated_by=user,
    )

    for seq, line in enumerate(clean_lines, start=1):
        quantity = Decimal(line["quantity"])
        price = Decimal(line.get("price") or 0)
        if quantity <= 0:
            raise ValidationError("Every line needs a quantity greater than zero.")

        item = line["inventory_item"]
        # A line may be written in a second unit the item is handled in; stock
        # and the books are kept in its own unit either way.
        quantity, price = to_base_unit(item=item, uom=line.get("uom"), quantity=quantity, rate=price)
        POSDetail.objects.create(
            pos_master=sale,
            seq_num=seq,
            inventory_item=item,
            quantity=quantity,
            price=price,
            created_by=user,
            updated_by=user,
        )

    # The bill-level discount and tax ride on the first line, because the totals
    # are derived from the lines when the sale is posted.
    first = sale.items.first()
    first.discount_amount = Decimal(discount_amount or 0).quantize(Decimal("0.01"))
    first.tax_amount = Decimal(tax_amount or 0).quantize(Decimal("0.01"))
    first.updated_by = user
    first.save()

    goods_total = sum((line.total_price for line in sale.items.all()), Decimal("0.00"))
    net_amount = (goods_total - Decimal(discount_amount or 0) + Decimal(tax_amount or 0)).quantize(Decimal("0.01"))

    paid = Decimal(paid_amount or 0).quantize(Decimal("0.01"))
    if paid > net_amount:
        raise ValidationError("Paid cannot be more than the invoice total.")

    # Set before posting: the posting reads it to split the sale between cash
    # collected and what the customer still owes.
    sale.total_paid = paid
    sale.pay_mode = "cash"
    sale.updated_by = user
    sale.save()

    sale = post_sale(sale=sale, user=user)

    # The order lines this sale drew down, and the orders they belong to.
    for line in clean_lines:
        order_item = line.get("_locked_order_item")
        if order_item is None:
            continue
        quantity, _rate = to_base_unit(
            item=line["inventory_item"], uom=line.get("uom"),
            quantity=Decimal(line["quantity"]), rate=Decimal(line.get("price") or 0),
        )
        order_item.qty_invoiced = (order_item.qty_invoiced or Decimal("0")) + quantity
        order_item.updated_by = user
        order_item.save()
    for order in touched_orders.values():
        _refresh_sales_order_status(order, user=user)

    # The voucher this sale posted, named on the invoice so it reads on its own.
    from apps.finance.models import AccountVoucher

    voucher = AccountVoucher.objects.filter(source_ref=f"inv_pos_masters:{sale.pk}").first()
    sale.journal_ref = voucher.voucher_no if voucher else ""
    sale.posted_at = timezone.now()
    sale.posted_by = user
    sale.save(update_fields=["journal_ref", "posted_at", "posted_by", "updated_at"])
    return sale, sale.net_amount


@transaction.atomic
def post_sale(*, sale, user):
    sale = POSMaster.objects.select_for_update().prefetch_related("items__inventory_item").get(pk=sale.pk)
    if sale.posted == YES:
        raise ValidationError("Posted sale cannot be edited or posted again.")
    if not sale.items.exists():
        raise ValidationError("Sale items are required before posting.")

    total = Decimal("0.00")
    tax_total = Decimal("0.00")
    discount_total = Decimal("0.00")
    cost_total = Decimal("0.00")
    for item in sale.items.all():
        stock = Stock.objects.select_for_update().get(inventory_item=item.inventory_item)
        if item.quantity > stock.current_quantity:
            raise ValidationError(f"Insufficient stock for {item.item_name}.")
        old_quantity = stock.current_quantity
        old_price = stock.current_price
        cost_total += item.quantity * (old_price or Decimal("0.00"))
        stock.current_quantity -= item.quantity
        stock.updated_by = user
        stock.save(update_fields=["current_quantity", "updated_by", "updated_at"])
        create_ledger_entry(stock=stock, inventory_item=item.inventory_item, transaction_id=sale.transaction_id, transaction_no=sale.sale_num, transaction_type=LEDGER_SALE, transaction_date=sale.sale_date, ref_table="inv_pos_details", ref_id=item.pk, ref_no=sale.sale_num, quantity=item.quantity, old_quantity=old_quantity, new_quantity=stock.current_quantity, old_price=old_price, current_price=stock.current_price, remarks=sale.remarks, user=user)
        total += item.total_price
        tax_total += item.tax_amount
        discount_total += item.discount_amount

    sale.total_amount = total
    sale.tax_amount = tax_total
    sale.discount_amount = discount_total
    sale.net_amount = total - discount_total + tax_total
    sale.balance = sale.net_amount - sale.total_paid
    sale.status = STATUS_POSTED
    sale.posted = YES
    sale.updated_by = user
    sale.save()

    # Posting the sale is also the accounting event: recognise revenue and match
    # the cost of the stock just issued. Same transaction, so stock and ledger
    # can never disagree.
    from apps.finance.services import post_sale_to_gl  # lazy: finance imports inventory

    post_sale_to_gl(sale=sale, cost_of_goods=cost_total, user=user)
    return sale


@transaction.atomic
def post_sale_return(*, sale_return, user):
    sale_return = POSReturnMaster.objects.select_for_update().select_related("pos_master").prefetch_related("items__inventory_item", "items__pos_detail").get(pk=sale_return.pk)
    if sale_return.posted == YES:
        raise ValidationError("Posted return cannot be changed.")
    total_return = Decimal("0.00")
    cost_total = Decimal("0.00")
    for item in sale_return.items.all():
        already_returned = sale_return.pos_master.returns.filter(posted=YES).exclude(pk=sale_return.pk).filter(items__pos_detail=item.pos_detail).aggregate(total=Sum("items__quantity"))["total"] or Decimal("0.0000")
        allowed = item.pos_detail.quantity - already_returned
        if item.quantity > allowed:
            raise ValidationError(f"Return quantity exceeds sold quantity for {item.item_name}.")
        stock = Stock.objects.select_for_update().get(inventory_item=item.inventory_item)
        old_quantity = stock.current_quantity
        old_price = stock.current_price
        stock.current_quantity += item.quantity
        stock.updated_by = user
        stock.save(update_fields=["current_quantity", "updated_by", "updated_at"])
        create_ledger_entry(stock=stock, inventory_item=item.inventory_item, transaction_id=sale_return.transaction_id, transaction_no=sale_return.return_num, transaction_type=LEDGER_SALE_RETURN, transaction_date=sale_return.return_date, ref_table="inv_pos_return_details", ref_id=item.pk, ref_no=f"Sale Return | {sale_return.sale_num}", quantity=item.quantity, old_quantity=old_quantity, new_quantity=stock.current_quantity, old_price=old_price, current_price=stock.current_price, remarks=f"Sale Return {sale_return.return_num} against {sale_return.sale_num}", user=user)
        total_return += item.net_total
        cost_total += item.quantity * (old_price or Decimal("0.00"))

    sale_return.returned_amount = total_return
    sale_return.status = STATUS_POSTED
    sale_return.posted = YES
    sale_return.updated_by = user
    sale_return.save()

    # Mirror of the sale's entry: reverse the revenue and put the cost back
    # into stock, in the same transaction so ledger and stock cannot diverge.
    from apps.finance.services import post_sale_return_to_gl  # lazy: finance imports inventory

    post_sale_return_to_gl(sale_return=sale_return, cost_of_goods=cost_total, user=user)

    master = sale_return.pos_master
    returned_qty = master.returns.filter(posted=YES).aggregate(total=Sum("items__quantity"))["total"] or Decimal("0.0000")
    sold_qty = master.items.aggregate(total=Sum("quantity"))["total"] or Decimal("0.0000")
    master.status = STATUS_RETURNED if returned_qty >= sold_qty else STATUS_PARTIAL_RETURNED
    master.updated_by = user
    master.save(update_fields=["status", "updated_by", "updated_at"])
    return sale_return


@transaction.atomic
def post_purchase_return(*, purchase_return, user):
    purchase_return = PurchaseReturnMaster.objects.select_for_update().select_related("purchase_master", "purchase_order").prefetch_related("items__inventory_item").get(pk=purchase_return.pk)
    if purchase_return.posted == YES:
        raise ValidationError("Posted purchase return cannot be changed.")
    total = Decimal("0.00")
    for item in purchase_return.items.all():
        # What may go back is what was invoiced, because the invoice is what
        # brought it in. Read off the order lines when the return is against an
        # order, and off the invoices themselves when it is not.
        received_qty = purchase_return.purchase_order.items.filter(
            inventory_item=item.inventory_item
        ).aggregate(total=Sum("qty_invoiced"))["total"] or Decimal("0.0000")
        if not received_qty:
            received_qty = PurchaseInvoiceLine.objects.filter(
                invoice__purchase_order=purchase_return.purchase_order,
                invoice__status=STATUS_POSTED,
                inventory_item=item.inventory_item,
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.0000")
        already_returned = PurchaseReturnMaster.objects.exclude(pk=purchase_return.pk).filter(purchase_order=purchase_return.purchase_order, posted=YES, items__inventory_item=item.inventory_item).aggregate(total=Sum("items__quantity"))["total"] or Decimal("0.0000")
        allowed = received_qty - already_returned
        if item.quantity > allowed:
            raise ValidationError(f"Return quantity exceeds received quantity for {item.item_name}.")
        stock = Stock.objects.select_for_update().get(inventory_item=item.inventory_item)
        if item.quantity > stock.current_quantity:
            raise ValidationError(f"Insufficient stock for purchase return of {item.item_name}.")
        old_quantity = stock.current_quantity
        old_price = stock.current_price
        stock.current_quantity -= item.quantity
        stock.updated_by = user
        stock.save(update_fields=["current_quantity", "updated_by", "updated_at"])
        create_ledger_entry(stock=stock, inventory_item=item.inventory_item, transaction_id=purchase_return.transaction_id, transaction_no=purchase_return.return_num, transaction_type=LEDGER_PURCHASE_RETURN, transaction_date=purchase_return.return_date, ref_table="inv_purchase_return_details", ref_id=item.pk, ref_no=purchase_return.return_num, quantity=item.quantity, old_quantity=old_quantity, new_quantity=stock.current_quantity, old_price=old_price, current_price=stock.current_price, remarks=purchase_return.remarks, user=user)
        PurchaseMasterReturn.objects.create(purchase_master=purchase_return.purchase_master, inv_purchase_master_transaction_id=purchase_return.purchase_master.transaction_id, inventory_item=item.inventory_item, inv_inventory_item_name=item.item_name, quantity=item.quantity, rate=item.rate, total_price=item.total_price, created_by=user, updated_by=user)
        total += item.total_price
    purchase_return.returned_amount = total
    purchase_return.status = STATUS_POSTED
    purchase_return.posted = YES
    purchase_return.updated_by = user
    purchase_return.save()
    purchase_master = purchase_return.purchase_master
    purchase_master.return_amount = (purchase_master.return_amount or Decimal("0.00")) + total
    purchase_master.updated_by = user
    purchase_master.save(update_fields=["return_amount", "updated_by", "updated_at"])

    # Goods go back to the supplier, so the stock asset and the debt both fall.
    from apps.finance.services import post_purchase_return_to_gl  # lazy: finance imports inventory

    post_purchase_return_to_gl(purchase_return=purchase_return, user=user)
    return purchase_return


# ══════════════════════════════════════════════════════════════════════════
# Purchase order lifecycle
#
# An order moves: draft -> raised -> partly received -> fully received. It can
# also stop early, in one of two ways that are deliberately not the same thing:
#
#   Cancelled     nothing ever arrived. The order is abandoned whole.
#   Closed short  something arrived, the rest never will, and somebody said so.
#
# Neither deletes anything. The number stays in the sequence and the reason
# stays on the record, because an order that vanishes is indistinguishable
# from one that was never raised, and the difference matters to whoever is
# reconciling commitments at the end of the month.
# ══════════════════════════════════════════════════════════════════════════


def purchase_order_approval_limit():
    """What a buyer may commit on their own signature.

    A setting rather than a constant: the figure is company policy, and policy
    changes without anyone wanting to ship a release for it.
    """
    from apps.configurations.models import SystemConfiguration

    row = SystemConfiguration.objects.filter(key=CONF_PO_APPROVAL_LIMIT_KEY).first()
    raw = (row.value or {}).get("amount") if row else None
    try:
        return Decimal(str(raw if raw is not None else CONF_PO_APPROVAL_LIMIT_DEFAULT))
    except (ArithmeticError, ValueError, TypeError):
        # A setting somebody typed by hand and got wrong must not stop the
        # purchase screens working; falling back to the shipped figure keeps
        # the control on rather than switching it off.
        return Decimal(CONF_PO_APPROVAL_LIMIT_DEFAULT)


def set_purchase_order_approval_limit(amount, *, user=None):
    from apps.configurations.models import SystemConfiguration

    limit = Decimal(amount or 0).quantize(TWO_DP)
    if limit < 0:
        raise ValidationError("An approval limit cannot be negative.")
    SystemConfiguration.objects.update_or_create(
        key=CONF_PO_APPROVAL_LIMIT_KEY,
        defaults={"value": {"amount": str(limit)}, "updated_by": user},
    )
    return limit


def needs_approval(amount):
    """Whether an order of this value is above what a buyer may commit alone."""
    return Decimal(amount or 0) > purchase_order_approval_limit()


def order_value(po):
    return sum((line.total_amount for line in po.items.all()), Decimal("0.00")).quantize(TWO_DP)


@transaction.atomic
def approve_purchase_order(*, order, user):
    """Release a draft order to the supplier, and record who released it.

    Approving is the moment the money is committed. It is also the only control
    on the purchase side that a person performs rather than the software, so
    the name and the amount approved are both kept — an approval limit whose
    approvals are anonymous is not a control, it is a speed bump.
    """
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != STATUS_DRAFT:
        raise ValidationError(f"{order.purchase_num} is not awaiting approval.")
    if not order.items.exists():
        raise ValidationError("An order with no lines on it cannot be approved.")

    value = order_value(order)
    if needs_approval(value) and not user_can_approve(user):
        raise ValidationError(
            f"{order.purchase_num} is worth {value} which is above the approval limit of "
            f"{purchase_order_approval_limit()}. It needs someone with purchase approval rights."
        )

    order.status = STATUS_SUBMITTED
    order.approved_by = user
    order.approved_at = timezone.now()
    order.approved_amount = value
    order.updated_by = user
    order.save(update_fields=["status", "approved_by", "approved_at", "approved_amount", "updated_by", "updated_at"])
    return order


def user_can_approve(user):
    """Who may commit above the buyer's own limit.

    Above the limit the order needs someone holding the approval right, not the
    buyer signing off their own order. Below it anybody who may raise an order
    may release it, which is what an approval limit means.
    """
    from apps.access_control.selectors import user_has_permission

    return user_has_permission(user, "inventory.purchase_orders.approve")


@transaction.atomic
def cancel_purchase_order(*, order, reason, user, remarks=""):
    """Abandon an order nothing has arrived against.

    Deliberately not a delete. The number stays in the sequence — a gap in a
    numbered series is the first thing anybody auditing purchases looks for,
    and "it was cancelled" is only believable if the cancelled document is
    still there to read.
    """
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if reason not in dict(INV_PO_CANCEL_REASONS):
        raise ValidationError("Pick a reason for cancelling this order.")
    if order.status in (STATUS_CANCELLED, STATUS_CLOSED):
        raise ValidationError(f"{order.purchase_num} is already closed.")
    if any((line.total_receive_qty or Decimal("0")) > 0 for line in order.items.all()):
        raise ValidationError(
            "Part of this order has already been received, so it cannot be cancelled. "
            "Close the PO instead — that keeps what arrived and gives up the rest."
        )

    order.items.update(closed=True)
    order.status = STATUS_CANCELLED
    order.close_reason = reason
    order.close_remarks = (remarks or "").strip()
    order.closed_on = timezone.localdate()
    order.closed_by = user
    order.short_qty = sum((line.quantity or Decimal("0") for line in order.items.all()), Decimal("0.0000"))
    order.short_value = order_value(order)
    order.updated_by = user
    order.save()
    return order


@transaction.atomic
def close_purchase_order_short(*, order, reason, user, remarks=""):
    """Give up on the balance of a part-delivered order.

    Creates no accounting entry, because an order never had one — nothing was
    debited when it was raised, so nothing has to be credited when it is
    abandoned. What it does is release the commitment: the outstanding quantity
    stops counting as goods on order, which is the figure the reorder decision
    is made on.
    """
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if reason not in dict(INV_PO_CLOSE_SHORT_REASONS):
        raise ValidationError("Pick a reason for closing this order short.")
    if order.status in (STATUS_CANCELLED, STATUS_CLOSED, STATUS_FULLY_INVOICED):
        raise ValidationError(f"{order.purchase_num} has nothing outstanding to close.")

    short_qty, short_value = Decimal("0.0000"), Decimal("0.00")
    for line in order.items.select_for_update():
        pending = line.open_receive_qty
        if pending <= FOUR_DP:
            continue
        short_qty += pending
        short_value += (pending * (line.rate or Decimal("0"))).quantize(TWO_DP)
        line.closed = True
        line.updated_by = user
        line.save(update_fields=["closed", "updated_by", "updated_at"])

    if short_qty <= FOUR_DP:
        raise ValidationError(f"{order.purchase_num} has nothing outstanding to close.")

    order.status = STATUS_CLOSED
    order.close_reason = reason
    order.close_remarks = (remarks or "").strip()
    order.closed_on = timezone.localdate()
    order.closed_by = user
    order.short_qty = short_qty
    order.short_value = short_value
    order.updated_by = user
    order.save()
    return order


@transaction.atomic
def reopen_purchase_order(*, order, user):
    """Expect the balance again, because the goods turned up after all.

    Closing short is a judgement, not a fact, and judgements are sometimes
    wrong. Re-opening puts the line balances back on the outstanding list; it
    touches no ledger, for the same reason closing it never did.
    """
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if order.status not in (STATUS_CANCELLED, STATUS_CLOSED):
        raise ValidationError(f"{order.purchase_num} is not closed.")

    order.items.update(closed=False)
    order.close_reason = ""
    order.closed_on = None
    order.closed_by = None
    order.short_qty = Decimal("0.0000")
    order.short_value = Decimal("0.00")
    # Back to whatever its receipts say it is, which may be raised or partly
    # received — never straight back to draft, because it was approved once.
    order.status = STATUS_SUBMITTED
    order.updated_by = user
    order.save()
    _refresh_order_receipt_status(order, user=user)
    return order


# ══════════════════════════════════════════════════════════════════════════
# Correcting a posted receipt — reversal, never deletion
#
# A posted goods receipt has moved stock, written an insert-only item ledger
# row and posted a general-ledger voucher. Deleting it would break the GRN
# sequence, take the document out of the audit trail, silently restate the
# weighted-average cost of every later movement of that item, and put the books
# out of step with anything already filed on them. It is also how theft is
# hidden: take the goods, delete the receipt.
#
# So a receipt is withdrawn by posting its mirror image. Both stay visible and
# the pair nets to nothing, which is what actually happened: an entry was made
# and then taken back.
# ══════════════════════════════════════════════════════════════════════════


# ── The purchase invoice ────────────────────────────────────────────────────
# One entry point for both routes in. Whether an order was raised first only
# decides where the lines are copied from; what happens to the books after
# that is identical, so it is written once.


def open_order_lines(*, supplier=None, purchase_order=None):
    """Order lines still open to be invoiced.

    An order commits nothing, so what is open on it is simply what was ordered
    and not yet invoiced. A line closed short is out of it: the balance was
    given up on and is never going to be invoiced.
    """
    rows = (
        PurchaseOrderItem.objects
        .select_related("purchase_order__supplier", "inventory_item", "uom")
        .filter(purchase_order__status__in=INV_ORDER_OPEN_STATUSES)
    )
    if supplier is not None:
        rows = rows.filter(purchase_order__supplier=supplier)
    if purchase_order is not None:
        rows = rows.filter(purchase_order=purchase_order)
    return [
        row for row in rows.order_by(
            "purchase_order__purchase_date", "purchase_order_id", "seq_num"
        )
        if row.qty_pending > FOUR_DP
    ]


def supplier_has_open_orders(*, supplier):
    """Whether the invoice screen must make the user pick an order.

    This is the branch the whole entry flow turns on, and it is decided by the
    supplier in front of you rather than by a setting: a supplier you have
    ordered from is invoiced against that order, and one you have not is
    invoiced directly.
    """
    if supplier is None:
        return False
    return bool(open_order_lines(supplier=supplier))


def next_purchase_invoice_number():
    """What the next invoice will be called.

    Advisory only: the number is allocated in ``PurchaseInvoice.save()``, so an
    invoice saved between this preview and the save takes it and the next one
    moves up.
    """
    last = (
        PurchaseInvoice.all_objects.order_by("-seq_num")
        .values_list("seq_num", flat=True).first() or 0
    )
    return f"PI-{last + 1:06d}"


def duplicate_supplier_invoice_number(*, supplier, supplier_invoice_num, exclude_pk=None):
    """The invoice this supplier number was already entered as, if it was."""
    if not supplier or not supplier_invoice_num:
        return None
    rows = PurchaseInvoice.objects.filter(
        supplier=supplier,
        supplier_invoice_num=supplier_invoice_num,
        status=STATUS_POSTED,
    )
    if exclude_pk:
        rows = rows.exclude(pk=exclude_pk)
    return rows.first()


def _refresh_order_invoiced_status(order, *, user=None):
    """Move an order along to whatever its own lines now say it is.

    Auto-closing happens here rather than in the invoice service so there is
    one place that decides, and a line edited by any other route lands on the
    same answer.
    """
    if order is None:
        return None
    order = PurchaseOrder.objects.prefetch_related("items").get(pk=order.pk)
    status = order.invoiced_status()
    if status == order.status:
        return order
    order.status = status
    order.updated_by = user
    order.save(update_fields=["status", "updated_by", "updated_at"])
    return order


@transaction.atomic
def create_purchase_invoice(*, supplier, supplier_invoice_num, supplier_invoice_date=None,
                            invoice_date=None, due_date=None, lines,
                            discount_amount=Decimal("0"), freight_amount=Decimal("0"),
                            tax_amount=None, paid_amount=Decimal("0"), remarks="", user):
    """Enter a supplier's invoice. The one financial document on this side.

    ``lines`` is a list of dicts carrying ``inventory_item``, ``quantity`` and
    ``rate``, optionally ``uom``, ``tax_perc``, ``discount_amount``, ``descr``
    and ``order_item``. A line naming an ``order_item`` is being invoiced
    against an order and is bounded by what is still open on it; a line without
    one was typed straight off the supplier's paperwork and is bounded by
    nothing else.

    Both kinds may sit on the same invoice, and lines may come off several
    orders at once -- the old one-order-per-document rule went with the bill,
    which needed it because it posted one payable against one commitment.

    Submitting is the whole event: stock comes in, the item ledger is written
    and the voucher is posted, in this transaction. There is nothing left
    parked anywhere waiting to be matched.
    """
    from apps.finance.services import post_purchase_invoice_to_gl  # lazy: finance imports inventory

    if not supplier:
        raise ValidationError("Pick the supplier this invoice is from.")
    supplier_invoice_num = (supplier_invoice_num or "").strip()
    if not supplier_invoice_num:
        raise ValidationError(
            "Enter the supplier's own invoice number - it is how a duplicate invoice is caught."
        )
    existing = duplicate_supplier_invoice_number(
        supplier=supplier, supplier_invoice_num=supplier_invoice_num
    )
    if existing:
        raise ValidationError(
            f"Duplicate: invoice {supplier_invoice_num} from this supplier was already "
            f"entered as {existing.invoice_num}."
        )

    clean = [
        line for line in lines
        if line.get("inventory_item") and Decimal(line.get("quantity") or 0) > 0
    ]
    if not clean:
        raise ValidationError("Add at least one line with a quantity.")

    invoice_date = invoice_date or timezone.localdate()

    prepared, goods_total, tax_from_lines = [], Decimal("0.00"), Decimal("0.00")
    touched_orders = {}
    for line in clean:
        item = line["inventory_item"]
        quantity = Decimal(line["quantity"])
        rate = Decimal(line.get("rate") or 0)
        if rate <= 0:
            raise ValidationError(
                "Every line needs a rate - the system will not guess what was agreed."
            )

        # A line written in a second unit the item is handled in is restated in
        # the item's own unit; the books are kept in that unit either way.
        quantity, rate = to_base_unit(
            item=item, uom=line.get("uom"), quantity=quantity, rate=rate
        )

        order_item = line.get("order_item")
        if order_item is not None:
            order_item = PurchaseOrderItem.objects.select_for_update().select_related(
                "purchase_order", "inventory_item"
            ).get(pk=order_item.pk)
            order = order_item.purchase_order
            if order.supplier_id != supplier.pk:
                raise ValidationError(f"{order.purchase_num} was raised on a different supplier.")
            if order.status in (STATUS_DRAFT, STATUS_CANCELLED):
                raise ValidationError("An order can only be invoiced once it has been submitted.")
            if quantity > order_item.qty_pending + FOUR_DP:
                raise ValidationError(
                    f"{order.purchase_num} line {order_item.seq_num} has only "
                    f"{order_item.qty_pending} left to invoice; this invoice is asking for "
                    f"{quantity}. You cannot be invoiced past what was ordered."
                )
            touched_orders[order.pk] = order

        line_discount = Decimal(line.get("discount_amount") or 0).quantize(TWO_DP)
        tax_perc = Decimal(line.get("tax_perc") or 0)
        amount = (quantity * rate - line_discount).quantize(TWO_DP)
        goods_total += amount
        tax_from_lines += (quantity * rate * tax_perc / 100).quantize(TWO_DP)
        prepared.append({
            "item": item,
            "order_item": order_item,
            "quantity": quantity,
            "rate": rate,
            "uom": item.uom,
            "tax_perc": tax_perc,
            "discount_amount": line_discount,
            "amount": amount,
            "descr": (line.get("descr") or item.item_name)[:255],
        })

    freight = Decimal(freight_amount or 0).quantize(TWO_DP)
    discount = Decimal(discount_amount or 0).quantize(TWO_DP)
    if discount > goods_total + freight:
        raise ValidationError("A discount cannot be more than the goods on the invoice.")

    # Tax is stated either off the face of the invoice as one figure, which is
    # how most supplier invoices in this trade are written, or per line.
    tax_total = (
        Decimal(tax_amount or 0).quantize(TWO_DP) if tax_amount is not None else tax_from_lines
    )
    total = (goods_total + freight - discount + tax_total).quantize(TWO_DP)

    paid = Decimal(paid_amount or 0).quantize(TWO_DP)
    if paid > total:
        raise ValidationError("Paid cannot be more than the invoice total.")

    # One order behind the invoice is recorded on it; several are recorded on
    # the lines, because the header has one column and cannot hold two answers.
    header_order = list(touched_orders.values())[0] if len(touched_orders) == 1 else None

    invoice = PurchaseInvoice.objects.create(
        supplier=supplier,
        purchase_order=header_order,
        supplier_invoice_num=supplier_invoice_num,
        supplier_invoice_date=supplier_invoice_date or None,
        invoice_date=invoice_date,
        due_date=due_date or None,
        goods_amount=goods_total,
        discount_amount=discount,
        freight_amount=freight,
        tax_amount=tax_total,
        total_amount=total,
        paid_amount=paid,
        status=STATUS_POSTED,
        posted_at=timezone.now(),
        posted_by=user,
        remarks=remarks or "",
        created_by=user,
        updated_by=user,
    )

    transaction_id = generate_transaction_id("PINV", PurchaseInvoice)

    # A purchase return is raised against a PurchaseMaster, so one is written
    # here for the same reason the bill used to write it: without it the
    # invoice would be the one kind of purchase that cannot be sent back.
    purchase_master = None
    if header_order is not None:
        purchase_master, _made = PurchaseMaster.objects.get_or_create(
            purchase_order=header_order,
            defaults={
                "transaction_id": generate_transaction_id("PUR", PurchaseMaster),
                "supplier": supplier,
                "inv_purchase_order_inv_num": supplier_invoice_num,
                "created_by": user,
                "updated_by": user,
            },
        )

    for seq, row in enumerate(prepared, start=1):
        PurchaseInvoiceLine.objects.create(
            invoice=invoice,
            purchase_order_item=row["order_item"],
            inventory_item=row["item"],
            seq_num=seq,
            descr=row["descr"],
            quantity=row["quantity"],
            rate=row["rate"],
            uom=row["uom"],
            tax_perc=row["tax_perc"],
            tax_amount=(row["quantity"] * row["rate"] * row["tax_perc"] / 100).quantize(TWO_DP),
            discount_amount=row["discount_amount"],
            amount=row["amount"],
            created_by=user,
            updated_by=user,
        )

        order_item = row["order_item"]
        if order_item is not None:
            order_item.qty_invoiced = (order_item.qty_invoiced or Decimal("0")) + row["quantity"]
            order_item.retail_price = row["rate"]
            order_item.updated_by = user
            order_item.save()

        # A service is not stocked, so there is nothing to take in and nothing
        # for the item ledger to say about it.
        if row["item"].item_kind != INVENTORY_KIND_PRODUCT:
            continue

        stock = Stock.objects.select_for_update().get(inventory_item=row["item"])
        old_quantity = stock.current_quantity
        old_price = stock.current_price
        stock.last_price = (
            row["rate"] if stock.current_quantity <= 0 and stock.current_price <= 0
            else stock.current_price
        )
        stock.current_price = row["rate"]
        stock.current_quantity = stock.current_quantity + row["quantity"]
        stock.updated_by = user
        stock.save()

        create_ledger_entry(
            stock=stock, inventory_item=row["item"],
            transaction_id=transaction_id, transaction_no=invoice.invoice_num,
            transaction_type=LEDGER_RECEIVE, transaction_date=invoice.invoice_date,
            ref_table="inv_purchase_invoices", ref_id=invoice.pk, ref_no=invoice.invoice_num,
            quantity=row["quantity"], old_quantity=old_quantity, new_quantity=stock.current_quantity,
            old_price=old_price, current_price=stock.current_price,
            remarks=remarks or row["descr"], user=user,
        )

    if purchase_master is not None:
        purchase_master.inv_purchase_order_inv_num = supplier_invoice_num
        purchase_master.total_amount = (purchase_master.total_amount or Decimal("0.00")) + goods_total
        purchase_master.updated_by = user
        purchase_master.save()

    # Every order this invoice touched moves along, however many there were.
    for order in touched_orders.values():
        _refresh_order_invoiced_status(order, user=user)

    voucher = post_purchase_invoice_to_gl(invoice=invoice, user=user)
    if voucher is not None:
        invoice.journal_ref = voucher.voucher_no
        invoice.save(update_fields=["journal_ref", "updated_at"])

    if paid > 0:
        from apps.finance.services import post_supplier_payment_to_gl

        post_supplier_payment_to_gl(
            source_ref=f"inv_purchase_invoices_paid:{invoice.pk}",
            payment_date=invoice.invoice_date,
            supplier=supplier,
            amount=paid,
            reference=supplier_invoice_num,
            user=user,
        )

    return invoice


def can_reverse_invoice(invoice):
    if invoice is None:
        return False, "Invoice not found."
    if invoice.status == STATUS_REVERSED:
        return False, "This invoice has already been reversed."
    if invoice.reversal_of_id:
        return False, "This is itself a reversal. If the invoice really is due, enter it again."
    return True, ""


@transaction.atomic
def reverse_purchase_invoice(*, invoice, reason, user):
    """Withdraw a posted invoice.

    The invoice is what took the goods in, so withdrawing it takes them back
    out: the stock comes off, the item ledger carries the reversal, and the
    payable goes with it. Order lines go back to uninvoiced, which is the state
    the books were in the moment before it was entered, so the correct invoice
    can be entered against the same order.

    Nothing is deleted. The original stays exactly as posted and a mirror
    cancels it, because deleting it would take the document out of the audit
    trail and silently restate a period that may already have been reported on.
    """
    from apps.finance.services import reverse_gl_posting  # lazy: finance imports inventory

    invoice = PurchaseInvoice.objects.select_for_update().select_related("supplier").get(pk=invoice.pk)
    ok, why = can_reverse_invoice(invoice)
    if not ok:
        raise ValidationError(why)
    if reason not in dict(INV_REVERSAL_REASONS):
        raise ValidationError(
            "A reversal needs a reason - one without it is unusable to whoever reads the books later."
        )

    transaction_id = generate_transaction_id("PINVR", PurchaseInvoice)
    touched_orders = {}

    for line in invoice.items.select_related("inventory_item", "purchase_order_item").all():
        order_item = line.purchase_order_item
        if order_item is not None:
            order_item = PurchaseOrderItem.objects.select_for_update().select_related(
                "purchase_order"
            ).get(pk=order_item.pk)
            order_item.qty_invoiced = max(
                Decimal("0.0000"), (order_item.qty_invoiced or Decimal("0")) - line.quantity
            )
            order_item.updated_by = user
            order_item.save()
            touched_orders[order_item.purchase_order_id] = order_item.purchase_order

        if line.inventory_item.item_kind != INVENTORY_KIND_PRODUCT:
            continue

        stock = Stock.objects.select_for_update().get(inventory_item=line.inventory_item)
        old_quantity = stock.current_quantity
        old_price = stock.current_price
        stock.current_quantity = stock.current_quantity - line.quantity
        stock.updated_by = user
        stock.save()

        create_ledger_entry(
            stock=stock, inventory_item=line.inventory_item,
            transaction_id=transaction_id, transaction_no=invoice.invoice_num,
            transaction_type=LEDGER_REVERSAL, transaction_date=timezone.localdate(),
            ref_table="inv_purchase_invoices", ref_id=invoice.pk, ref_no=invoice.invoice_num,
            quantity=line.quantity, old_quantity=old_quantity, new_quantity=stock.current_quantity,
            old_price=old_price, current_price=stock.current_price,
            remarks=f"Reversal of {invoice.invoice_num}", user=user,
        )

    invoice.status = STATUS_REVERSED
    invoice.reverse_reason = reason
    invoice.reversed_on = timezone.localdate()
    invoice.updated_by = user
    invoice.save(update_fields=["status", "reverse_reason", "reversed_on", "updated_by", "updated_at"])

    for order in touched_orders.values():
        _refresh_order_invoiced_status(order, user=user)

    reverse_gl_posting(
        source_ref=f"inv_purchase_invoices:{invoice.pk}",
        reversal_ref=f"inv_purchase_invoices_reversal:{invoice.pk}",
        voucher_date=timezone.localdate(),
        remarks=f"Reversal of purchase invoice {invoice.invoice_num}",
        user=user,
    )
    # Money paid on the invoice was a second posting, and withdrawing the
    # invoice without withdrawing it would leave the supplier's account showing
    # a payment against a purchase that no longer exists.
    if invoice.paid_amount:
        reverse_gl_posting(
            source_ref=f"inv_purchase_invoices_paid:{invoice.pk}",
            reversal_ref=f"inv_purchase_invoices_paid_reversal:{invoice.pk}",
            voucher_date=timezone.localdate(),
            remarks=f"Reversal of payment on purchase invoice {invoice.invoice_num}",
            user=user,
        )
    return invoice


