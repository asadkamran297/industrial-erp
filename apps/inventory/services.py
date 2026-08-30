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

from apps.core.constants import CONF_PO_APPROVAL_LIMIT_DEFAULT, CONF_PO_APPROVAL_LIMIT_KEY, INV_BILL_MATCH_TOLERANCE_PERCENT, INV_PO_CANCEL_REASONS, INV_PO_CLOSE_SHORT_REASONS, INV_REVERSAL_REASONS, LEDGER_ADJUSTMENT, LEDGER_OPENING, LEDGER_PURCHASE_RETURN, LEDGER_RECEIVE, LEDGER_REVERSAL, LEDGER_SALE, LEDGER_SALE_RETURN, NO, STATUS_ACTIVE, STATUS_CANCELLED, STATUS_CLOSED_SHORT, STATUS_DRAFT, STATUS_FULLY_RECEIVED, STATUS_PARTIAL_RECEIVED, STATUS_PARTIAL_RETURNED, STATUS_POSTED, STATUS_RAISED, STATUS_RETURNED, STATUS_REVERSED, STATUS_SUBMITTED, YES

TWO_DP = Decimal("0.01")
FOUR_DP = Decimal("0.0001")

from .models import (
    ItemLedger,
    PurchaseBill,
    PurchaseBillItem,
    ManualTransaction,
    POSDetail,
    POSMaster,
    POSReturnMaster,
    PurchaseMaster,
    PurchaseMasterReturn,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderItemReceived,
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


@transaction.atomic
def default_receipt_narration(*, purchase_order, receive_date, rv_number=""):
    """What to write on a receipt nobody wrote anything on.

    A blank narration is not neutral: it reads, months later, as though nobody
    checked the delivery. So the facts that are known anyway are stated —
    which order, which supplier, what day, and the carrier's paperwork where
    the store recorded it.

    Deliberately says nothing about the items: every line of one delivery gets
    the same sentence, so a note covering four lines reads as one narration
    rather than four near-identical ones. What arrived on each line is in the
    table beside it.
    """
    day = receive_date
    if isinstance(day, str):
        day = parse_date(day) or day
    when = day.strftime("%d-%m-%Y") if hasattr(day, "strftime") else str(day)
    text = (
        f"Goods received against {purchase_order.purchase_num} "
        f"from {purchase_order.supplier.name} on {when}."
    )
    carrier = (rv_number or "").strip()
    if carrier:
        text = f"{text} Delivery ref: {carrier}."
    return f"{text} Entered automatically — no narration was given."


def receive_purchase_order_item(*, purchase_order_item, quantity, extra_qty, retail_price, receive_date, invoice_num, invoice_date, rv_number, remarks, user, grn_number="", dc_number="", vehicle_no="", driver_number="", inspected_by=""):
    purchase_order_item = PurchaseOrderItem.objects.select_for_update().select_related("purchase_order", "inventory_item").get(pk=purchase_order_item.pk)
    if purchase_order_item.closed:
        raise ValidationError("This line was closed short — nothing more is expected on it. Re-open the order first if the goods have turned up after all.")
    if purchase_order_item.purchase_order.status in (STATUS_DRAFT, STATUS_CANCELLED, STATUS_CLOSED_SHORT):
        raise ValidationError("Goods can only be received against an approved order that is still open.")
    if quantity <= 0:
        raise ValidationError("Receive quantity must be greater than zero.")
    # What turned up is what turned up: a delivery may be short, exact, or over
    # the ordered figure. The receipt records the fact; the order line is not a
    # ceiling on it. Over-receipt shows up as a total above the ordered quantity
    # and is settled on the bill, not by refusing the goods at the gate.

    po = purchase_order_item.purchase_order

    if not (remarks or "").strip():
        remarks = default_receipt_narration(
            purchase_order=po, receive_date=receive_date, rv_number=rv_number
        )

    received_units = quantity + extra_qty
    # The goods are valued at what was agreed for them and nothing else.
    # Carriage is not loaded onto the stock: it is settled on the supplier's
    # bill, where the money actually changes hands.
    landed_price = retail_price or Decimal("0")
    landed_amount = (landed_price * received_units).quantize(TWO_DP)

    receipt = PurchaseOrderItemReceived.objects.create(
        purchase_order_item=purchase_order_item,
        seq_num=(purchase_order_item.receipts.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0) + 1,
        purchase_num=po.purchase_num,
        purchase_date=po.purchase_date,
        descr=purchase_order_item.descr,
        status=STATUS_POSTED,
        inventory_item=purchase_order_item.inventory_item,
        quantity=quantity,
        receive_date=receive_date,
        invoice_num=invoice_num,
        invoice_date=invoice_date,
        # One delivery is one document, so the store's own GRN number is kept
        # when it hands one over; the per-line fallback is only for the screens
        # that receive a single row on its own.
        grn_number=(grn_number or "").strip()[:80] or f"GRN-{po.purchase_num}-{purchase_order_item.seq_num}",
        rv_number=rv_number,
        dc_number=(dc_number or "").strip()[:80],
        vehicle_no=(vehicle_no or "").strip()[:60],
        driver_number=(driver_number or "").strip()[:60],
        inspected_by=(inspected_by or "").strip()[:120],
        remarks=remarks or "",
        extra_qty_tag=YES if extra_qty > 0 else NO,
        extra_qty=extra_qty,
        retail_price=retail_price,
        landed_amount=landed_amount,
        created_by=user,
        updated_by=user,
    )

    purchase_order_item.last_receive_qty = purchase_order_item.curr_receive_qty
    purchase_order_item.curr_receive_qty = quantity + extra_qty
    purchase_order_item.total_receive_qty = purchase_order_item.total_receive_qty + quantity + extra_qty
    purchase_order_item.retail_price = landed_price
    purchase_order_item.updated_by = user
    purchase_order_item.save()

    _refresh_order_receipt_status(po, user=user)

    purchase_master, _ = PurchaseMaster.objects.get_or_create(
        purchase_order=po,
        defaults={
            "transaction_id": generate_transaction_id("PUR", PurchaseMaster),
            "supplier": po.supplier,
            "inv_purchase_order_inv_num": invoice_num,
            "created_by": user,
            "updated_by": user,
        },
    )
    purchase_master.inv_purchase_order_inv_num = invoice_num
    purchase_master.supplier = po.supplier
    purchase_master.total_amount = sum((item.total_receive_qty or 0) * (item.rate or 0) for item in po.items.all())
    purchase_master.updated_by = user
    purchase_master.save()

    stock = Stock.objects.select_for_update().get(inventory_item=purchase_order_item.inventory_item)
    old_quantity = stock.current_quantity
    old_price = stock.current_price
    stock.last_price = landed_price if stock.current_quantity <= 0 and stock.current_price <= 0 else stock.current_price
    stock.current_price = landed_price
    stock.current_quantity = stock.current_quantity + quantity + extra_qty
    stock.updated_by = user
    stock.save()

    create_ledger_entry(stock=stock, inventory_item=purchase_order_item.inventory_item, transaction_id=purchase_master.transaction_id, transaction_no=po.purchase_num, transaction_type=LEDGER_RECEIVE, transaction_date=receive_date, ref_table="inv_purchase_order_item_received", ref_id=receipt.pk, ref_no=receipt.grn_number, quantity=quantity + extra_qty, old_quantity=old_quantity, new_quantity=stock.current_quantity, old_price=old_price, current_price=stock.current_price, remarks=remarks or purchase_order_item.descr, user=user)

    # Receiving the goods is the accounting event: the asset arrives and the
    # debt to the supplier arises at the same moment, at landed cost.
    from apps.finance.services import post_purchase_receipt_to_gl  # lazy: finance imports inventory

    post_purchase_receipt_to_gl(receipt=receipt, supplier=po.supplier, amount=landed_amount, user=user)
    return receipt


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


def next_direct_purchase_number():
    """What the next purchase invoice will be called.

    Advisory only: the number is allocated by ``PurchaseOrder.save()`` off the
    shared sequence, so a bill saved between this preview and the save takes it
    and the next one moves up.
    """
    last = PurchaseOrder.all_objects.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
    return f"PI-{last + 1:06d}"


def next_grn_number():
    """What the next goods receipt will be called; advisory, like the order one."""
    numbers = [
        int(value.split("-")[1])
        for value in PurchaseOrderItemReceived.all_objects
        .filter(grn_number__regex=r"^GRN-\d+$")
        .values_list("grn_number", flat=True)
    ]
    return f"GRN-{(max(numbers) if numbers else 0) + 1}"


def next_purchase_order_number():
    """What the next purchase order will be called; advisory, like the bill one."""
    last = PurchaseOrder.all_objects.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
    return f"PO-{last + 1}"


@transaction.atomic
def create_purchase_order(*, supplier, quot_num, quot_date, order_date, lines, expected_date=None,
                          discount_amount=Decimal("0"), tax_amount=Decimal("0"),
                          remarks="", status=STATUS_RAISED, extra_data=None, user):
    """An order raised on a supplier: goods asked for, none of them here yet.

    Same entry shape as ``create_direct_purchase`` so both purchase screens read
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
        is_direct=False,
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
    if order.status == STATUS_RAISED:
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
def create_direct_sale(*, customer, sale_date, lines, discount_amount=Decimal("0"),
                       tax_amount=Decimal("0"), paid_amount=Decimal("0"), remarks="", user):
    """A sale entered as an invoice, posted the moment it is saved.

    The counterpart of ``create_direct_purchase``: the same shape of entry, and
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

    sale = POSMaster.objects.create(
        transaction_id=generate_transaction_id("SAL", POSMaster),
        sale_date=sale_date,
        customer=customer,
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

    # Straight off the supplier's bill, so the goods arriving and the invoice
    # arriving are the same event. The bill is posted here rather than left for
    # somebody to enter later: without it the value would sit in GRN Clearing
    # for ever, saying the business had been delivered goods nobody had billed
    # it for, which for a direct purchase is not true even for a moment.
    receipts = list(
        PurchaseOrderItemReceived.objects
        .filter(purchase_order_item__purchase_order=order, reversed=False, reversal_of__isnull=True)
        .select_related("purchase_order_item__purchase_order", "inventory_item")
    )
    create_purchase_bill(
        supplier=supplier,
        supplier_invoice_num=bill_number or order.purchase_num,
        supplier_invoice_date=bill_date,
        bill_date=bill_date,
        lines=[{"receipt": receipt, "quantity": receipt.received_units, "rate": receipt.landed_rate}
               for receipt in receipts],
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        remarks=remarks or "",
        # The one document was typed by hand as a whole, so the difference
        # between it and the receipt it created is the discount that was on it
        # and nothing else. There is no second party's figure to match against.
        variance_approved=True,
        user=user,
    )

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
    return sale, sale.net_amount


@transaction.atomic
def create_direct_purchase(*, supplier, bill_number, bill_date, lines, discount_amount=Decimal("0"),
                           tax_amount=Decimal("0"), paid_amount=Decimal("0"), remarks="", user):
    """A purchase entered straight off the supplier's bill, with no order first.

    The bill still lands in the order and receipt tables, and every line is
    received in full as it is entered. That is deliberate: stock, the item
    ledger and the general ledger then read exactly as they would for a
    purchase that had gone through an order, so nothing downstream needs to
    know which route the goods came in by.

    ``lines`` is a list of dicts: inventory_item, quantity, rate, and an
    optional description.
    """
    if not supplier:
        raise ValidationError("Pick a supplier.")

    clean_lines = [line for line in lines if line.get("inventory_item") and line.get("quantity")]
    if not clean_lines:
        raise ValidationError("Add at least one item with a quantity.")

    order = PurchaseOrder.objects.create(
        supplier=supplier,
        purchase_date=bill_date,
        status=STATUS_RAISED,
        is_direct=True,
        quot_num=bill_number or "",
        descr=remarks or "",
        created_by=user,
        updated_by=user,
    )

    goods_total = Decimal("0.00")
    for seq, line in enumerate(clean_lines, start=1):
        quantity = Decimal(line["quantity"])
        rate = Decimal(line.get("rate") or 0)
        if quantity <= 0:
            raise ValidationError("Every line needs a quantity greater than zero.")

        item = line["inventory_item"]
        # The line may be written in a second unit the item is handled in; the
        # books are kept in its own unit either way.
        quantity, rate = to_base_unit(item=item, uom=line.get("uom"), quantity=quantity, rate=rate)
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=order,
            seq_num=seq,
            purchase_num=order.purchase_num,
            purchase_date=order.purchase_date,
            inventory_item=item,
            quantity=quantity,
            rate=rate,
            unit_rate=rate,
            uom=item.uom,
            descr=(line.get("descr") or item.item_name)[:255],
            created_by=user,
            updated_by=user,
        )
        goods_total += (quantity * rate).quantize(Decimal("0.01"))

        # Received as it is entered: the bill is the goods arriving.
        receive_purchase_order_item(
            purchase_order_item=po_item,
            quantity=quantity,
            extra_qty=Decimal("0"),
            retail_price=rate,
            receive_date=bill_date,
            invoice_num=bill_number or order.purchase_num,
            invoice_date=bill_date,
            rv_number="",
            remarks=line.get("descr") or "",
            user=user,
        )

    net_amount = (goods_total - Decimal(discount_amount or 0) + Decimal(tax_amount or 0)).quantize(Decimal("0.01"))

    # Straight off the supplier's bill, so the goods arriving and the invoice
    # arriving are the same event. The bill is posted here rather than left for
    # somebody to enter later: without it the value would sit in GRN Clearing
    # for ever, saying the business had been delivered goods nobody had billed
    # it for, which for a direct purchase is not true even for a moment.
    receipts = list(
        PurchaseOrderItemReceived.objects
        .filter(purchase_order_item__purchase_order=order, reversed=False, reversal_of__isnull=True)
        .select_related("purchase_order_item__purchase_order", "inventory_item")
    )
    create_purchase_bill(
        supplier=supplier,
        supplier_invoice_num=bill_number or order.purchase_num,
        supplier_invoice_date=bill_date,
        bill_date=bill_date,
        lines=[{"receipt": receipt, "quantity": receipt.received_units, "rate": receipt.landed_rate}
               for receipt in receipts],
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        remarks=remarks or "",
        # The one document was typed by hand as a whole, so the difference
        # between it and the receipt it created is the discount that was on it
        # and nothing else. There is no second party's figure to match against.
        variance_approved=True,
        user=user,
    )

    paid = Decimal(paid_amount or 0).quantize(Decimal("0.01"))
    if paid > net_amount:
        raise ValidationError("Paid cannot be more than the bill total.")

    if paid > 0:
        from apps.finance.services import post_supplier_payment_to_gl

        post_supplier_payment_to_gl(
            source_ref=f"inv_purchase_orders_paid:{order.pk}",
            payment_date=bill_date,
            supplier=supplier,
            amount=paid,
            reference=bill_number or order.purchase_num,
            user=user,
        )

    return order, net_amount


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
        received_qty = purchase_return.purchase_order.items.filter(inventory_item=item.inventory_item).aggregate(total=Sum("total_receive_qty"))["total"] or Decimal("0.0000")
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


def _refresh_order_receipt_status(po, *, user=None):
    """Set the order's status from what its lines are actually still owed.

    A line that was closed short counts as finished even though nothing more
    came, which is the whole point of closing it: the commitment is released
    without the books pretending goods arrived.
    """
    lines = list(po.items.all())
    if not lines:
        return po

    if po.status in (STATUS_CANCELLED, STATUS_CLOSED_SHORT):
        return po

    received_any = any((line.total_receive_qty or Decimal("0")) > 0 for line in lines)
    all_done = all(line.open_receive_qty <= FOUR_DP for line in lines)

    if all_done:
        # Everything settled, but by delivery or by decision? If any line was
        # given up on, the order ended short and should say so.
        po.status = STATUS_CLOSED_SHORT if any(line.closed for line in lines) else STATUS_FULLY_RECEIVED
    elif received_any:
        po.status = STATUS_PARTIAL_RECEIVED
    else:
        po.status = STATUS_RAISED

    po.updated_by = user
    po.save(update_fields=["status", "updated_by", "updated_at"])
    return po


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

    order.status = STATUS_RAISED
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
    if order.status in (STATUS_CANCELLED, STATUS_CLOSED_SHORT):
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
    if order.status in (STATUS_CANCELLED, STATUS_CLOSED_SHORT, STATUS_FULLY_RECEIVED):
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

    order.status = STATUS_CLOSED_SHORT
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
    if order.status not in (STATUS_CANCELLED, STATUS_CLOSED_SHORT):
        raise ValidationError(f"{order.purchase_num} is not closed.")

    order.items.update(closed=False)
    order.close_reason = ""
    order.closed_on = None
    order.closed_by = None
    order.short_qty = Decimal("0.0000")
    order.short_value = Decimal("0.00")
    # Back to whatever its receipts say it is, which may be raised or partly
    # received — never straight back to draft, because it was approved once.
    order.status = STATUS_RAISED
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


def can_reverse_receipt(receipt):
    """Whether this receipt may be withdrawn, and if not, why not.

    Returns ``(ok, reason)``. The checks run in the order documents were
    created, so the caller is always told to unwind the *last* thing first —
    unwinding out of order would leave a bill pointing at goods that are no
    longer on the books.
    """
    if receipt is None:
        return False, "Goods receipt not found."
    if receipt.reversed:
        return False, "This receipt has already been reversed."
    if receipt.reversal_of_id:
        return False, (
            "This is itself a reversal. Reversing it would simply re-post the original — "
            "if the goods really did arrive, enter a fresh receipt."
        )
    # Read the billed quantity back from the database rather than trusting the
    # instance handed in. A screen holds a receipt object across a request, and
    # a bill entered in between would leave that copy saying it was unbilled --
    # which is exactly the case this guard exists to catch.
    billed = PurchaseOrderItemReceived.objects.filter(pk=receipt.pk).values_list("billed_qty", flat=True).first() or Decimal("0")
    if billed > FOUR_DP:
        return False, "A supplier bill has already been matched to this receipt. Reverse the bill first, then this."

    # Taking the goods back out must not drive the item negative. If the stock
    # has already been sold or milled, the receipt is no longer the thing to
    # correct — the movements on top of it are.
    units = receipt.received_units
    on_hand = Stock.objects.filter(inventory_item=receipt.inventory_item_id).values_list("current_quantity", flat=True).first() or Decimal("0")
    if on_hand + FOUR_DP < units:
        item_name = receipt.inventory_item.item_name
        return False, (
            f"Reversing this would take {units} of {item_name} back out, but only {on_hand} is left in stock — "
            "it has been used or sold. Reverse the movements that came after it first."
        )
    return True, ""


@transaction.atomic
def reverse_purchase_receipt(*, receipt, reason, user):
    """Withdraw a posted goods receipt by posting its mirror image.

    Writes a second receipt row carrying the negative quantity, takes the stock
    back out at the rate it came in at, writes the item-ledger row that says so,
    and reverses the general-ledger voucher. Then it rolls back the counters the
    original had advanced, so the order goes back to expecting the goods.
    """
    from apps.finance.services import reverse_gl_posting  # lazy: finance imports inventory

    receipt = PurchaseOrderItemReceived.objects.select_for_update().select_related(
        "purchase_order_item__purchase_order", "inventory_item"
    ).get(pk=receipt.pk)

    ok, why = can_reverse_receipt(receipt)
    if not ok:
        raise ValidationError(why)
    if reason not in dict(INV_REVERSAL_REASONS):
        raise ValidationError("A reversal needs a reason — one without it is unusable to whoever reads the books later.")

    line = PurchaseOrderItem.objects.select_for_update().get(pk=receipt.purchase_order_item_id)
    po = line.purchase_order
    units = receipt.received_units
    today = timezone.localdate()

    mirror = PurchaseOrderItemReceived.objects.create(
        purchase_order_item=line,
        seq_num=(line.receipts.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0) + 1,
        purchase_num=po.purchase_num,
        purchase_date=po.purchase_date,
        descr=receipt.descr,
        status=STATUS_REVERSED,
        inventory_item=receipt.inventory_item,
        quantity=-(receipt.quantity or Decimal("0")),
        extra_qty=-(receipt.extra_qty or Decimal("0")),
        receive_date=today,
        invoice_num=receipt.invoice_num,
        invoice_date=receipt.invoice_date,
        grn_number=f"REV-{receipt.grn_number}",
        rv_number=receipt.rv_number,
        extra_qty_tag=receipt.extra_qty_tag,
        retail_price=receipt.retail_price,
        landed_amount=-(receipt.landed_amount or Decimal("0")),
        reversal_of=receipt,
        reverse_reason=reason,
        reversed_on=today,
        created_by=user,
        updated_by=user,
    )

    # Stock back out at the rate it came in at. The average cost is left where
    # the remaining stock puts it rather than being recomputed backwards: the
    # units are leaving at their own cost, which is all a reversal claims.
    stock = Stock.objects.select_for_update().get(inventory_item=receipt.inventory_item)
    old_quantity, old_price = stock.current_quantity, stock.current_price
    stock.current_quantity = stock.current_quantity - units
    stock.updated_by = user
    stock.save()

    create_ledger_entry(
        stock=stock, inventory_item=receipt.inventory_item,
        transaction_id=generate_transaction_id("REV", PurchaseOrderItemReceived),
        transaction_no=po.purchase_num, transaction_type=LEDGER_REVERSAL, transaction_date=today,
        ref_table="inv_purchase_order_item_received", ref_id=mirror.pk, ref_no=mirror.grn_number,
        quantity=-units, old_quantity=old_quantity, new_quantity=stock.current_quantity,
        old_price=old_price, current_price=stock.current_price,
        remarks=f"Reversal of {receipt.grn_number} — {dict(INV_REVERSAL_REASONS)[reason]}", user=user,
    )

    reverse_gl_posting(
        source_ref=f"inv_purchase_order_item_received:{receipt.pk}",
        reversal_ref=f"inv_purchase_order_item_received:{mirror.pk}",
        voucher_date=today,
        remarks=f"Reversal of goods receipt {receipt.grn_number} — {dict(INV_REVERSAL_REASONS)[reason]}",
        user=user,
    )

    # Put the order line back to expecting these goods again.
    line.total_receive_qty = (line.total_receive_qty or Decimal("0")) - units
    line.curr_receive_qty = Decimal("0.0000")
    line.updated_by = user
    line.save()

    receipt.reversed = True
    receipt.reverse_reason = reason
    receipt.reversed_on = today
    receipt.updated_by = user
    receipt.save(update_fields=["reversed", "reverse_reason", "reversed_on", "updated_by", "updated_at"])

    _refresh_order_receipt_status(po, user=user)
    return mirror


# ══════════════════════════════════════════════════════════════════════════
# Supplier bills — the third leg of the three-way match
#
#   1. Purchase order   what was agreed to buy, and at what rate
#   2. Goods receipt    what actually arrived at the gate
#   3. Supplier bill    what they are asking to be paid
#
# A bill is entered against receipts, never against the order, because the
# order is a promise and the receipt is a fact. Quantity cannot exceed what
# arrived; value is compared to what the goods were taken into stock at, and a
# difference beyond tolerance stops the bill until somebody with the authority
# says otherwise. That single control is what stops a supplier billing weight
# that never crossed the gate.
# ══════════════════════════════════════════════════════════════════════════


def bill_match_tolerance():
    return Decimal(INV_BILL_MATCH_TOLERANCE_PERCENT)


def billable_receipts(*, supplier=None, purchase_order=None):
    """Receipts with goods in the godown that no bill has been entered against."""
    rows = (
        PurchaseOrderItemReceived.objects
        .select_related("purchase_order_item__purchase_order__supplier", "inventory_item")
        .filter(reversed=False, reversal_of__isnull=True)
    )
    if supplier is not None:
        rows = rows.filter(purchase_order_item__purchase_order__supplier=supplier)
    if purchase_order is not None:
        rows = rows.filter(purchase_order_item__purchase_order=purchase_order)
    return [row for row in rows.order_by("receive_date", "id") if row.pending_bill_qty > FOUR_DP]


def duplicate_supplier_invoice(*, supplier, supplier_invoice_num, exclude_pk=None):
    """The bill this invoice number was already entered as, if it was.

    The supplier's own number is the only thing that catches the same invoice
    arriving twice — by post and again by hand, or from two people in the
    office — which is the usual way a supplier ends up paid twice for one load.
    """
    rows = PurchaseBill.objects.filter(
        supplier=supplier, supplier_invoice_num__iexact=(supplier_invoice_num or "").strip(), status=STATUS_POSTED
    )
    if exclude_pk:
        rows = rows.exclude(pk=exclude_pk)
    return rows.first()


@transaction.atomic
def create_purchase_bill(*, supplier, supplier_invoice_num, supplier_invoice_date, bill_date, lines,
                         due_date=None, freight_amount=Decimal("0"), discount_amount=Decimal("0"),
                         tax_amount=None, remarks="", variance_approved=False, user):
    """Enter a supplier's invoice against goods already received.

    ``lines`` is a list of dicts: ``receipt``, ``quantity``, ``rate`` and an
    optional ``tax_perc``. Pass ``tax_amount`` to state the tax as one figure
    off the face of the invoice instead of per line, which is how most supplier
    bills in this trade are actually written.

    A discount the supplier allowed is not taken back off the stock: those
    units were valued when they arrived and some may be sold already. It shows
    up as the bill coming in under what was received, which is a credit to
    Purchase Price Variance — the goods did cost less than the books said.

    Nothing here touches stock. The goods were valued when they arrived; this
    releases that value out of GRN Clearing and puts the real payable in its
    place. Where the bill and the receipt disagree the difference goes to
    Purchase Price Variance, because re-costing the stock now would rewrite the
    cost of units that may already have been sold.
    """
    from apps.finance.services import post_purchase_bill_to_gl  # lazy: finance imports inventory

    if not supplier:
        raise ValidationError("Pick the supplier this bill is from.")
    supplier_invoice_num = (supplier_invoice_num or "").strip()
    if not supplier_invoice_num:
        raise ValidationError("Enter the supplier's own invoice number — it is how a duplicate bill is caught.")
    existing = duplicate_supplier_invoice(supplier=supplier, supplier_invoice_num=supplier_invoice_num)
    if existing:
        raise ValidationError(
            f"Duplicate: invoice {supplier_invoice_num} from this supplier was already entered as {existing.bill_num}."
        )

    clean = [line for line in lines if line.get("receipt") and Decimal(line.get("quantity") or 0) > 0]
    if not clean:
        raise ValidationError("Add at least one line with a quantity — pick the goods receipts this bill covers.")

    # Every line has to come off the same order, because a bill posts one
    # payable against one commitment and splitting it across orders would leave
    # neither of them traceable to what was paid.
    orders = {line["receipt"].purchase_order_item.purchase_order_id for line in clean}
    if len(orders) > 1:
        raise ValidationError("All the lines on one bill must belong to the same purchase order.")

    prepared, goods_total, cleared_total = [], Decimal("0.00"), Decimal("0.00")
    for line in clean:
        receipt = PurchaseOrderItemReceived.objects.select_for_update().select_related(
            "purchase_order_item__purchase_order", "inventory_item"
        ).get(pk=line["receipt"].pk)
        if receipt.purchase_order_item.purchase_order.supplier_id != supplier.pk:
            raise ValidationError(f"{receipt.grn_number} was received from a different supplier.")
        quantity = Decimal(line["quantity"])
        rate = Decimal(line.get("rate") or 0)
        if rate <= 0:
            raise ValidationError("Every line needs a rate — the system will not guess what was agreed.")
        if quantity > receipt.pending_bill_qty + FOUR_DP:
            raise ValidationError(
                f"{receipt.grn_number} has only {receipt.pending_bill_qty} left to bill; "
                f"the bill is asking for {quantity}. You cannot be billed for goods that did not arrive."
            )
        amount = (quantity * rate).quantize(TWO_DP)
        goods_total += amount
        # What these same units are holding in GRN Clearing, at what they were
        # received at — the figure the bill is being matched against.
        cleared_total += (quantity * receipt.landed_rate).quantize(TWO_DP)
        prepared.append((receipt, quantity, rate, amount, Decimal(line.get("tax_perc") or 0)))

    freight = Decimal(freight_amount or 0).quantize(TWO_DP)
    discount = Decimal(discount_amount or 0).quantize(TWO_DP)
    if discount > goods_total + freight:
        raise ValidationError("A discount cannot be more than the goods on the bill.")
    billed_goods = (goods_total + freight - discount).quantize(TWO_DP)
    variance = (billed_goods - cleared_total).quantize(TWO_DP)
    drift = (abs(variance) / cleared_total * 100) if cleared_total else Decimal("0")

    if drift > bill_match_tolerance() and not variance_approved:
        raise ValidationError(
            f"Blocked — this bill is {drift.quantize(TWO_DP)}% away from the {cleared_total} the goods were "
            f"received at, against a tolerance of {bill_match_tolerance()}%. Check the rate against the "
            "purchase order, or have the difference approved before posting."
        )

    if tax_amount is not None:
        tax_total = Decimal(tax_amount or 0).quantize(TWO_DP)
    else:
        tax_total = sum(
            ((quantity * rate * tax_perc / 100).quantize(TWO_DP) for _r, quantity, rate, _a, tax_perc in prepared),
            Decimal("0.00"),
        )

    bill = PurchaseBill.objects.create(
        supplier=supplier,
        purchase_order_id=orders.pop(),
        supplier_invoice_num=supplier_invoice_num,
        supplier_invoice_date=supplier_invoice_date or None,
        bill_date=bill_date or timezone.localdate(),
        due_date=due_date or None,
        goods_amount=(goods_total - discount).quantize(TWO_DP),
        freight_amount=freight,
        tax_amount=tax_total,
        total_amount=(billed_goods + tax_total).quantize(TWO_DP),
        cleared_amount=cleared_total,
        variance_amount=variance,
        variance_approved=bool(variance_approved and drift > bill_match_tolerance()),
        remarks=remarks or "",
        created_by=user,
        updated_by=user,
    )

    for seq, (receipt, quantity, rate, amount, tax_perc) in enumerate(prepared, start=1):
        PurchaseBillItem.objects.create(
            bill=bill, receipt=receipt, inventory_item=receipt.inventory_item, seq_num=seq,
            descr=receipt.descr, quantity=quantity, rate=rate,
            receipt_rate=receipt.landed_rate.quantize(TWO_DP), tax_perc=tax_perc,
            tax_amount=(quantity * rate * tax_perc / 100).quantize(TWO_DP), amount=amount,
            created_by=user, updated_by=user,
        )
        receipt.billed_qty = (receipt.billed_qty or Decimal("0")) + quantity
        # Carry the supplier's number onto the receipt too, so the goods
        # receipt register can say at a glance what invoiced it.
        receipt.invoice_num = supplier_invoice_num
        receipt.invoice_date = supplier_invoice_date or receipt.invoice_date
        receipt.updated_by = user
        receipt.save(update_fields=["billed_qty", "invoice_num", "invoice_date", "updated_by", "updated_at"])

    post_purchase_bill_to_gl(bill=bill, user=user)
    return bill


def can_reverse_bill(bill):
    if bill is None:
        return False, "Bill not found."
    if bill.status == STATUS_REVERSED:
        return False, "This bill has already been reversed."
    if bill.reversal_of_id:
        return False, "This is itself a reversal. If the bill really is due, enter it again."
    return True, ""


@transaction.atomic
def reverse_purchase_bill(*, bill, reason, user):
    """Withdraw a posted supplier bill.

    Puts the value back into GRN Clearing and takes the payable off, which is
    the state the books were in the moment before the bill was entered: goods
    on hand, nobody billed for them yet. The receipts go back to unbilled, so
    the correct invoice can be entered against them.
    """
    from apps.finance.services import reverse_gl_posting  # lazy: finance imports inventory

    bill = PurchaseBill.objects.select_for_update().select_related("supplier").get(pk=bill.pk)
    ok, why = can_reverse_bill(bill)
    if not ok:
        raise ValidationError(why)
    if reason not in dict(INV_REVERSAL_REASONS):
        raise ValidationError("A reversal needs a reason — one without it is unusable to whoever reads the books later.")

    today = timezone.localdate()
    mirror = PurchaseBill.objects.create(
        supplier=bill.supplier,
        purchase_order=bill.purchase_order,
        # Not the supplier's number again: that number is unique per supplier
        # among posted bills, and this reversal must not stand in the way of
        # the corrected bill being entered under it.
        supplier_invoice_num=f"REV/{bill.supplier_invoice_num}"[:80],
        supplier_invoice_date=bill.supplier_invoice_date,
        bill_date=today,
        goods_amount=-bill.goods_amount, freight_amount=-bill.freight_amount,
        tax_amount=-bill.tax_amount, total_amount=-bill.total_amount,
        cleared_amount=-bill.cleared_amount, variance_amount=-bill.variance_amount,
        status=STATUS_REVERSED, reversal_of=bill, reverse_reason=reason, reversed_on=today,
        remarks=f"Reversal of {bill.bill_num} — {dict(INV_REVERSAL_REASONS)[reason]}",
        created_by=user, updated_by=user,
    )

    for item in bill.items.select_related("receipt"):
        receipt = PurchaseOrderItemReceived.objects.select_for_update().get(pk=item.receipt_id)
        receipt.billed_qty = max(Decimal("0.0000"), (receipt.billed_qty or Decimal("0")) - item.quantity)
        if receipt.billed_qty <= FOUR_DP:
            receipt.invoice_num = ""
            receipt.invoice_date = None
        receipt.updated_by = user
        receipt.save(update_fields=["billed_qty", "invoice_num", "invoice_date", "updated_by", "updated_at"])

    reverse_gl_posting(
        source_ref=f"inv_purchase_bills:{bill.pk}",
        reversal_ref=f"inv_purchase_bills:{mirror.pk}",
        voucher_date=today,
        remarks=f"Reversal of purchase bill {bill.bill_num} — {dict(INV_REVERSAL_REASONS)[reason]}",
        user=user,
    )

    bill.status = STATUS_REVERSED
    bill.reverse_reason = reason
    bill.reversed_on = today
    bill.updated_by = user
    bill.save(update_fields=["status", "reverse_reason", "reversed_on", "updated_by", "updated_at"])
    return mirror
