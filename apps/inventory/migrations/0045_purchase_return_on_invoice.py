"""Hang the purchase return off the invoice, and retire the purchase master.

``PurchaseMaster`` was a headless row with no screen behind it. It existed to
give a return something to point at and to feed the supplier "amount bought"
figures; both now read ``PurchaseInvoice``, which is the document that actually
brought the goods in. Two consequences worth naming:

  * a spot purchase can now be returned. It has no order, so it never got a
    purchase master, so until now it was the one purchase that could not go back.
  * ``purchase_order`` on a return becomes nullable, for the same reason.

The table is renamed rather than dropped. It carries pre-cutover history, the
model is read-only from here on, and a report that reads it keeps working.
"""

from django.db import migrations, models
import django.db.models.deletion

STATUS_POSTED = "POSTED"


def link_returns_to_invoices(apps, schema_editor):
    """Point each existing return at the invoice its old master stood for."""
    PurchaseReturnMaster = apps.get_model("inventory", "PurchaseReturnMaster")
    PurchaseInvoice = apps.get_model("inventory", "PurchaseInvoice")

    for pr in PurchaseReturnMaster.objects.filter(purchase_invoice__isnull=True).iterator():
        order_id = pr.purchase_master.purchase_order_id if pr.purchase_master_id else pr.purchase_order_id
        invoice = (
            PurchaseInvoice.objects.filter(purchase_order_id=order_id, status=STATUS_POSTED)
            .order_by("invoice_date", "id")
            .first()
        )
        if invoice is None:
            raise RuntimeError(
                f"Purchase return {pr.pk} has no posted invoice behind order {order_id}; "
                "migrate it by hand rather than orphaning it."
            )
        pr.purchase_invoice = invoice
        pr.save(update_fields=["purchase_invoice"])


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0044_repoint_bill_item_ledger_refs"),
    ]

    operations = [
        migrations.RenameModel(old_name="PurchaseMaster", new_name="LegacyPurchaseMaster"),
        migrations.RenameModel(old_name="PurchaseMasterReturn", new_name="LegacyPurchaseMasterReturn"),
        migrations.AlterModelTable(name="legacypurchasemaster", table="legacy_inv_purchase_master"),
        migrations.AlterModelTable(name="legacypurchasemasterreturn", table="legacy_inv_purchase_master_returns"),
        # Nullable first so the column can be added, then filled, then closed.
        migrations.AddField(
            model_name="purchasereturnmaster",
            name="purchase_invoice",
            field=models.ForeignKey(
                null=True, blank=True, db_column="inv_purchase_invoice_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="returns", to="inventory.purchaseinvoice",
            ),
        ),
        migrations.RunPython(link_returns_to_invoices, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="purchasereturnmaster",
            name="purchase_invoice",
            field=models.ForeignKey(
                db_column="inv_purchase_invoice_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="returns", to="inventory.purchaseinvoice",
            ),
        ),
        migrations.AlterField(
            model_name="purchasereturnmaster",
            name="purchase_order",
            field=models.ForeignKey(
                null=True, blank=True, db_column="inv_purchase_order_id",
                on_delete=django.db.models.deletion.PROTECT, to="inventory.purchaseorder",
            ),
        ),
        migrations.RemoveField(model_name="purchasereturnmaster", name="purchase_master"),
    ]
