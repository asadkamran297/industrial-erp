from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    """Carry what the receipts were billed for onto the order lines.

    Billing runs off the order line now. Orders entered under the goods-receipt
    flow hold that figure on their receipts, so without this every one of them
    would read as never invoiced and could be billed a second time.
    """
    PurchaseOrderItem = apps.get_model("inventory", "PurchaseOrderItem")
    PurchaseOrderItemReceived = apps.get_model("inventory", "PurchaseOrderItemReceived")

    billed = {}
    rows = PurchaseOrderItemReceived.objects.filter(
        reversed=False, reversal_of__isnull=True
    ).values_list("purchase_order_item_id", "billed_qty")
    for item_id, quantity in rows:
        billed[item_id] = billed.get(item_id, Decimal("0.0000")) + (quantity or Decimal("0.0000"))

    for item_id, quantity in billed.items():
        if quantity > Decimal("0.0000"):
            PurchaseOrderItem.objects.filter(pk=item_id).update(billed_qty=quantity)


def backwards(apps, schema_editor):
    PurchaseOrderItem = apps.get_model("inventory", "PurchaseOrderItem")
    PurchaseOrderItem.objects.update(billed_qty=Decimal("0.0000"))


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0034_purchasebillitem_purchase_order_item_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
