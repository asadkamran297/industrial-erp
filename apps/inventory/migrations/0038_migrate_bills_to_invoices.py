"""Move every purchase onto one document.

Two shapes go in and one comes out. A ``PurchaseBill`` carried the money for a
purchase raised as an order; a ``PurchaseOrder(is_direct=True)`` was itself the
invoice for one entered straight off the supplier's paperwork. Both become a
``PurchaseInvoice``.

The general ledger is not touched. Vouchers already exist for these purchases
and they stay exactly as posted -- only the ``source_ref`` that points back at
the source document is rewritten, because the document it named is going away.
No voucher, and no voucher line, is created, edited or deleted here. That is
what makes ``verify_ledger_totals --after`` able to prove the books are
unchanged, and it is why the step is done this way rather than by reposting.
"""

from decimal import Decimal

from django.db import migrations

ZERO = Decimal("0.00")
BILL_REF = "inv_purchase_bills:%s"
INVOICE_REF = "inv_purchase_invoices:%s"


def _voucher_for(AccountVoucher, source_ref):
    return AccountVoucher.objects.filter(source_ref=source_ref).first()


def forwards(apps, schema_editor):
    PurchaseBill = apps.get_model("inventory", "PurchaseBill")
    PurchaseOrder = apps.get_model("inventory", "PurchaseOrder")
    PurchaseInvoice = apps.get_model("inventory", "PurchaseInvoice")
    PurchaseInvoiceLine = apps.get_model("inventory", "PurchaseInvoiceLine")
    AccountVoucher = apps.get_model("finance", "AccountVoucher")

    seq = 0

    # Bills first, in the order they were raised, so the new numbers run in the
    # same direction as the old ones and a PI- number is never lower than the
    # PB- it replaced.
    for bill in PurchaseBill.objects.order_by("seq_num", "pk").iterator():
        seq += 1
        voucher = _voucher_for(AccountVoucher, BILL_REF % bill.pk)
        invoice = PurchaseInvoice.objects.create(
            supplier_id=bill.supplier_id,
            purchase_order_id=bill.purchase_order_id,
            seq_num=seq,
            invoice_num=f"PI-{seq:06d}",
            supplier_invoice_num=bill.supplier_invoice_num,
            supplier_invoice_date=bill.supplier_invoice_date,
            invoice_date=bill.bill_date,
            due_date=bill.due_date,
            goods_amount=bill.goods_amount or ZERO,
            # The bill held its discount netted into goods_amount rather than
            # on its own column, so there is nothing to carry across; freight
            # and tax were separate and are.
            discount_amount=ZERO,
            freight_amount=bill.freight_amount or ZERO,
            tax_amount=bill.tax_amount or ZERO,
            total_amount=bill.total_amount or ZERO,
            paid_amount=ZERO,
            status=bill.status,
            posted_at=bill.created_at,
            posted_by_id=bill.created_by_id,
            journal_ref=voucher.voucher_no if voucher else "",
            legacy_bill_no=bill.bill_num,
            reverse_reason=bill.reverse_reason,
            reversed_on=bill.reversed_on,
            remarks=bill.remarks,
            is_active=bill.is_active,
            deleted_at=bill.deleted_at,
            created_by_id=bill.created_by_id,
            updated_by_id=bill.updated_by_id,
        )

        for line in bill.items.order_by("seq_num", "pk"):
            order_item = line.purchase_order_item
            PurchaseInvoiceLine.objects.create(
                invoice=invoice,
                purchase_order_item_id=line.purchase_order_item_id,
                inventory_item_id=line.inventory_item_id,
                seq_num=line.seq_num,
                descr=line.descr,
                quantity=line.quantity,
                rate=line.rate,
                uom_id=getattr(order_item, "uom_id", None),
                tax_perc=line.tax_perc or ZERO,
                tax_amount=line.tax_amount or ZERO,
                discount_amount=ZERO,
                amount=line.amount or ZERO,
                created_by_id=line.created_by_id,
                updated_by_id=line.updated_by_id,
            )

        if voucher:
            voucher.source_ref = INVOICE_REF % invoice.pk
            voucher.save(update_fields=["source_ref"])

    # A direct purchase with no bill behind it: the order row was the invoice,
    # so it becomes one and stops being an order.
    billed_orders = set(
        PurchaseBill.objects.values_list("purchase_order_id", flat=True)
    )
    directs = (
        PurchaseOrder.objects.filter(is_direct=True)
        .exclude(pk__in=billed_orders)
        .order_by("seq_num", "pk")
    )
    for order in directs.iterator():
        seq += 1
        invoice = PurchaseInvoice.objects.create(
            supplier_id=order.supplier_id,
            purchase_order=None,
            seq_num=seq,
            invoice_num=f"PI-{seq:06d}",
            supplier_invoice_num=order.quot_num or order.purchase_num,
            supplier_invoice_date=order.quot_date,
            invoice_date=order.purchase_date,
            goods_amount=ZERO,
            total_amount=ZERO,
            status="posted",
            posted_at=order.created_at,
            posted_by_id=order.created_by_id,
            legacy_bill_no="",
            remarks=order.descr,
            is_active=order.is_active,
            deleted_at=order.deleted_at,
            created_by_id=order.created_by_id,
            updated_by_id=order.updated_by_id,
        )
        goods = ZERO
        for line in order.items.order_by("seq_num", "pk"):
            amount = (line.quantity or Decimal("0")) * (line.rate or ZERO)
            goods += amount
            PurchaseInvoiceLine.objects.create(
                invoice=invoice,
                purchase_order_item=None,
                inventory_item_id=line.inventory_item_id,
                seq_num=line.seq_num,
                descr=line.descr,
                quantity=line.quantity,
                rate=line.rate,
                uom_id=line.uom_id,
                tax_perc=line.tax_perc or ZERO,
                amount=amount,
                created_by_id=line.created_by_id,
                updated_by_id=line.updated_by_id,
            )
        invoice.goods_amount = goods
        invoice.total_amount = goods
        invoice.save(update_fields=["goods_amount", "total_amount"])


def backwards(apps, schema_editor):
    """Put the bills back and hand the vouchers their old source_ref.

    Only invoices that came from a bill are restored -- they are the ones
    carrying a ``legacy_bill_no``. A direct purchase's order row was never
    deleted going forwards, so there is nothing to rebuild for it.
    """
    PurchaseBill = apps.get_model("inventory", "PurchaseBill")
    PurchaseBillItem = apps.get_model("inventory", "PurchaseBillItem")
    PurchaseInvoice = apps.get_model("inventory", "PurchaseInvoice")
    AccountVoucher = apps.get_model("finance", "AccountVoucher")

    for invoice in PurchaseInvoice.objects.exclude(legacy_bill_no="").order_by("seq_num"):
        seq = int(invoice.legacy_bill_no.rsplit("-", 1)[-1])
        bill = PurchaseBill.objects.create(
            supplier_id=invoice.supplier_id,
            purchase_order_id=invoice.purchase_order_id,
            seq_num=seq,
            bill_num=invoice.legacy_bill_no,
            supplier_invoice_num=invoice.supplier_invoice_num,
            supplier_invoice_date=invoice.supplier_invoice_date,
            bill_date=invoice.invoice_date,
            due_date=invoice.due_date,
            goods_amount=invoice.goods_amount,
            freight_amount=invoice.freight_amount,
            tax_amount=invoice.tax_amount,
            total_amount=invoice.total_amount,
            cleared_amount=invoice.goods_amount,
            variance_amount=ZERO,
            variance_approved=True,
            status=invoice.status,
            reverse_reason=invoice.reverse_reason,
            reversed_on=invoice.reversed_on,
            remarks=invoice.remarks,
            is_active=invoice.is_active,
            deleted_at=invoice.deleted_at,
            created_by_id=invoice.created_by_id,
            updated_by_id=invoice.updated_by_id,
        )
        for line in invoice.items.order_by("seq_num"):
            PurchaseBillItem.objects.create(
                bill=bill,
                purchase_order_item_id=line.purchase_order_item_id,
                inventory_item_id=line.inventory_item_id,
                seq_num=line.seq_num,
                descr=line.descr,
                quantity=line.quantity,
                rate=line.rate,
                receipt_rate=line.rate,
                tax_perc=line.tax_perc,
                tax_amount=line.tax_amount,
                amount=line.amount,
                created_by_id=line.created_by_id,
                updated_by_id=line.updated_by_id,
            )

        voucher = _voucher_for(AccountVoucher, INVOICE_REF % invoice.pk)
        if voucher:
            voucher.source_ref = BILL_REF % bill.pk
            voucher.save(update_fields=["source_ref"])

    PurchaseInvoice.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0037_purchase_invoice_tables"),
        ("finance", "0016_alter_accountconfiguration_created_at_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
