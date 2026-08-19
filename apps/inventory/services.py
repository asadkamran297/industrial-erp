from decimal import Decimal

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

from apps.core.constants import LEDGER_ADJUSTMENT, LEDGER_OPENING, LEDGER_PURCHASE_RETURN, LEDGER_RECEIVE, LEDGER_SALE, LEDGER_SALE_RETURN, NO, STATUS_ACTIVE, STATUS_DRAFT, STATUS_FULLY_RECEIVED, STATUS_PARTIAL_RECEIVED, STATUS_PARTIAL_RETURNED, STATUS_POSTED, STATUS_RAISED, STATUS_RETURNED, STATUS_SUBMITTED, YES

from .models import (
    ItemLedger,
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
def receive_purchase_order_item(*, purchase_order_item, quantity, extra_qty, retail_price, receive_date, invoice_num, invoice_date, rv_number, remarks, user, freight_amount=Decimal("0")):
    purchase_order_item = PurchaseOrderItem.objects.select_for_update().select_related("purchase_order", "inventory_item").get(pk=purchase_order_item.pk)
    allowed = purchase_order_item.quantity + purchase_order_item.extra_qty - purchase_order_item.total_receive_qty
    if quantity <= 0:
        raise ValidationError("Receive quantity must be greater than zero.")
    if quantity + extra_qty > allowed:
        raise ValidationError("PO item cannot receive more than ordered quantity unless extra quantity is available.")

    po = purchase_order_item.purchase_order

    received_units = quantity + extra_qty
    freight_per_unit = (freight_amount / received_units) if received_units > 0 else Decimal("0")
    landed_price = (retail_price or Decimal("0")) + freight_per_unit

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
        grn_number=f"GRN-{po.purchase_num}-{purchase_order_item.seq_num}",
        rv_number=rv_number,
        extra_qty_tag=YES if extra_qty > 0 else NO,
        extra_qty=extra_qty,
        retail_price=retail_price,
        created_by=user,
        updated_by=user,
    )

    purchase_order_item.last_receive_qty = purchase_order_item.curr_receive_qty
    purchase_order_item.curr_receive_qty = quantity + extra_qty
    purchase_order_item.total_receive_qty = purchase_order_item.total_receive_qty + quantity + extra_qty
    purchase_order_item.retail_price = landed_price
    purchase_order_item.updated_by = user
    purchase_order_item.save()

    po_items = po.items.all()
    if po_items.exists() and all(item.total_receive_qty >= item.quantity for item in po_items):
        po.status = STATUS_FULLY_RECEIVED
    else:
        po.status = STATUS_PARTIAL_RECEIVED
    po.updated_by = user
    po.save(update_fields=["status", "updated_by", "updated_at"])

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

    post_purchase_receipt_to_gl(
        receipt=receipt, supplier=po.supplier, amount=landed_price * received_units, user=user
    )
    return receipt


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
        return quantity / factor, rate * factor

    # 1 picked = factor base  ->  the picked unit is the larger of the two.
    up = UOMConversion.objects.filter(uom_from=uom, uom_to=base, status=STATUS_ACTIVE).first()
    if up and up.conversion_factor:
        factor = Decimal(up.conversion_factor)
        return quantity * factor, rate / factor

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
