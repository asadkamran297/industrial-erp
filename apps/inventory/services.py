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

from apps.core.constants import LEDGER_ADJUSTMENT, LEDGER_PURCHASE_RETURN, LEDGER_RECEIVE, LEDGER_SALE, LEDGER_SALE_RETURN, NO, STATUS_DRAFT, STATUS_FULLY_RECEIVED, STATUS_PARTIAL_RECEIVED, STATUS_PARTIAL_RETURNED, STATUS_POSTED, STATUS_RETURNED, STATUS_SUBMITTED, YES

from .models import (
    ItemLedger,
    ManualTransaction,
    POSMaster,
    POSReturnMaster,
    PurchaseMaster,
    PurchaseMasterReturn,
    PurchaseOrderItem,
    PurchaseOrderItemReceived,
    PurchaseReturnMaster,
    Stock,
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
def receive_purchase_order_item(*, purchase_order_item, quantity, extra_qty, retail_price, receive_date, invoice_num, invoice_date, rv_number, remarks, user):
    purchase_order_item = PurchaseOrderItem.objects.select_for_update().select_related("purchase_order", "inventory_item").get(pk=purchase_order_item.pk)
    allowed = purchase_order_item.quantity + purchase_order_item.extra_qty - purchase_order_item.total_receive_qty
    if quantity <= 0:
        raise ValidationError("Receive quantity must be greater than zero.")
    if quantity + extra_qty > allowed:
        raise ValidationError("PO item cannot receive more than ordered quantity unless extra quantity is available.")

    po = purchase_order_item.purchase_order

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
    purchase_order_item.retail_price = retail_price
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
            "vendor": po.vendor,
            "inv_purchase_order_inv_num": invoice_num,
            "created_by": user,
            "updated_by": user,
        },
    )
    purchase_master.inv_purchase_order_inv_num = invoice_num
    purchase_master.vendor = po.vendor
    purchase_master.total_amount = sum((item.total_receive_qty or 0) * (item.rate or 0) for item in po.items.all())
    purchase_master.updated_by = user
    purchase_master.save()

    stock = Stock.objects.select_for_update().get(inventory_item=purchase_order_item.inventory_item)
    old_quantity = stock.current_quantity
    old_price = stock.current_price
    stock.last_price = retail_price if stock.current_quantity <= 0 and stock.current_price <= 0 else stock.current_price
    stock.current_price = retail_price
    stock.current_quantity = stock.current_quantity + quantity + extra_qty
    stock.updated_by = user
    stock.save()

    create_ledger_entry(stock=stock, inventory_item=purchase_order_item.inventory_item, transaction_id=purchase_master.transaction_id, transaction_no=po.purchase_num, transaction_type=LEDGER_RECEIVE, transaction_date=receive_date, ref_table="inv_purchase_order_item_received", ref_id=receipt.pk, ref_no=receipt.grn_number, quantity=quantity + extra_qty, old_quantity=old_quantity, new_quantity=stock.current_quantity, old_price=old_price, current_price=stock.current_price, remarks=remarks or purchase_order_item.descr, user=user)
    return receipt


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
    for item in sale.items.all():
        stock = Stock.objects.select_for_update().get(inventory_item=item.inventory_item)
        if item.quantity > stock.current_quantity:
            raise ValidationError(f"Insufficient stock for {item.item_name}.")
        old_quantity = stock.current_quantity
        old_price = stock.current_price
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
    return sale


@transaction.atomic
def post_sale_return(*, sale_return, user):
    sale_return = POSReturnMaster.objects.select_for_update().select_related("pos_master").prefetch_related("items__inventory_item", "items__pos_detail").get(pk=sale_return.pk)
    if sale_return.posted == YES:
        raise ValidationError("Posted return cannot be changed.")
    total_return = Decimal("0.00")
    for item in sale_return.items.all():
        already_returned = sale_return.pos_master.returns.exclude(pk=sale_return.pk).filter(items__pos_detail=item.pos_detail).aggregate(total=Sum("items__quantity"))["total"] or Decimal("0.0000")
        allowed = item.pos_detail.quantity - already_returned
        if item.quantity > allowed:
            raise ValidationError(f"Return quantity exceeds sold quantity for {item.item_name}.")
        stock = Stock.objects.select_for_update().get(inventory_item=item.inventory_item)
        old_quantity = stock.current_quantity
        old_price = stock.current_price
        stock.current_quantity += item.quantity
        stock.updated_by = user
        stock.save(update_fields=["current_quantity", "updated_by", "updated_at"])
        create_ledger_entry(stock=stock, inventory_item=item.inventory_item, transaction_id=sale_return.transaction_id, transaction_no=sale_return.return_num, transaction_type=LEDGER_SALE_RETURN, transaction_date=sale_return.return_date, ref_table="inv_pos_return_details", ref_id=item.pk, ref_no=sale_return.return_num, quantity=item.quantity, old_quantity=old_quantity, new_quantity=stock.current_quantity, old_price=old_price, current_price=stock.current_price, remarks=sale_return.remarks, user=user)
        total_return += item.net_total

    sale_return.returned_amount = total_return
    sale_return.status = STATUS_POSTED
    sale_return.posted = YES
    sale_return.updated_by = user
    sale_return.save()

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
    return purchase_return
