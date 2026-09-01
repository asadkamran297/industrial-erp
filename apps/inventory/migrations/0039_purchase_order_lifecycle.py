"""Put the purchase order on its own lifecycle.

An order commits nothing to the books, so what moves it along is the invoice
against it. The statuses are renamed to say that: an order is submitted, then
partially or fully invoiced, then closed -- rather than "received", which
described a goods receipt that no longer exists.

The line's ``billed_qty`` becomes ``qty_invoiced`` for the same reason. It is a
rename, not a new column: the figures in it are correct and are kept.
"""

from django.db import migrations, models

# Old value -> new. "Raised" and "submitted" are the same act under two names;
# "closed_short" and "cancelled" both just mean the order stopped, and the
# reason for it is already held in close_reason.
FORWARD_STATUS = {
    "raised": "submitted",
    "partial_received": "partially_invoiced",
    "fully_received": "fully_invoiced",
    "closed_short": "closed",
}
BACKWARD_STATUS = {new: old for old, new in FORWARD_STATUS.items()}


def _remap(apps, mapping):
    PurchaseOrder = apps.get_model("inventory", "PurchaseOrder")
    for old, new in mapping.items():
        PurchaseOrder.objects.filter(status=old).update(status=new)


def forwards(apps, schema_editor):
    _remap(apps, FORWARD_STATUS)


def backwards(apps, schema_editor):
    _remap(apps, BACKWARD_STATUS)


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0038_migrate_bills_to_invoices"),
    ]

    operations = [
        migrations.RenameField(
            model_name="purchaseorderitem",
            old_name="billed_qty",
            new_name="qty_invoiced",
        ),
        migrations.AlterField(
            model_name="purchaseorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("partially_invoiced", "Partially Invoiced"),
                    ("fully_invoiced", "Fully Invoiced"),
                    ("closed", "Closed"),
                    ("cancelled", "Cancelled"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
