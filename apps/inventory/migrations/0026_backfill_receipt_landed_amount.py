"""Give receipts already on file the landed value they were taken in at.

``landed_amount`` is what a supplier bill is matched against, so a receipt
without one cannot be billed. Historic rows never stored the figure, but it is
recoverable: the receipt kept the landed price per unit it wrote onto the order
line, and failing that the order's own rate is what the goods were valued at.
Freight on those old receipts was never apportioned anywhere else, so nothing
is lost by rebuilding the amount from the rate.
"""

from decimal import Decimal

from django.db import migrations

TWO_DP = Decimal("0.01")


def backfill(apps, schema_editor):
    Received = apps.get_model("inventory", "PurchaseOrderItemReceived")
    rows = Received.objects.select_related("purchase_order_item").all()
    for receipt in rows.iterator():
        if receipt.landed_amount:
            continue
        units = (receipt.quantity or Decimal("0")) + (receipt.extra_qty or Decimal("0"))
        rate = receipt.retail_price or Decimal("0")
        if not rate:
            rate = getattr(receipt.purchase_order_item, "rate", None) or Decimal("0")
        receipt.landed_amount = (units * rate).quantize(TWO_DP)
        # An invoice number was the old way of saying "this has been billed".
        # Honour it, so a receipt that was already invoiced does not turn up on
        # the unbilled list the moment this ships.
        if receipt.invoice_num:
            receipt.billed_qty = units
        receipt.save(update_fields=["landed_amount", "billed_qty"])


def unbackfill(apps, schema_editor):
    """Nothing to undo: the columns go with the schema migration."""


class Migration(migrations.Migration):

    dependencies = [("inventory", "0025_purchasebill_purchasebillitem_and_more")]

    operations = [migrations.RunPython(backfill, unbackfill)]
