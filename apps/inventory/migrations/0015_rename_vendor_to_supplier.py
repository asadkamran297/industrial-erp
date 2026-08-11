"""Rename Vendor to Supplier everywhere, down to table and column names.

The portal only ever called these records suppliers; the model, table and
foreign-key columns were the last place the old word survived. Renames are used
rather than drop/create so existing purchase history keeps its rows.
"""

import django.db.models.deletion
from django.db import migrations, models


def forwards_codes(apps, schema_editor):
    """Re-prefix issued supplier codes: VEN-0001 -> SUP-0001."""
    Supplier = apps.get_model("inventory", "Supplier")
    for supplier in Supplier.objects.filter(code__startswith="VEN-"):
        supplier.code = "SUP-" + supplier.code[4:]
        supplier.save(update_fields=["code"])


def backwards_codes(apps, schema_editor):
    Supplier = apps.get_model("inventory", "Supplier")
    for supplier in Supplier.objects.filter(code__startswith="SUP-"):
        supplier.code = "VEN-" + supplier.code[4:]
        supplier.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("configurations", "0001_initial"),
        ("inventory", "0014_alter_vendor_code"),
    ]

    operations = [
        migrations.RenameModel(old_name="Vendor", new_name="Supplier"),
        migrations.AlterModelTable(name="supplier", table="inv_config_suppliers"),
        migrations.RenameField(
            model_name="supplier",
            old_name="vendor_current_status",
            new_name="supplier_current_status",
        ),
        migrations.RenameField(model_name="purchaseorder", old_name="vendor", new_name="supplier"),
        migrations.RenameField(model_name="purchasemaster", old_name="vendor", new_name="supplier"),
        migrations.RenameField(model_name="purchasereturnmaster", old_name="vendor", new_name="supplier"),
        migrations.RenameField(model_name="manualtransaction", old_name="vendor", new_name="supplier"),
        migrations.AlterField(
            model_name="purchaseorder",
            name="supplier",
            field=models.ForeignKey(
                db_column="inv_config_supplier_id",
                on_delete=django.db.models.deletion.PROTECT,
                to="inventory.supplier",
            ),
        ),
        migrations.AlterField(
            model_name="purchasemaster",
            name="supplier",
            field=models.ForeignKey(
                db_column="inv_config_supplier_id",
                on_delete=django.db.models.deletion.PROTECT,
                to="inventory.supplier",
            ),
        ),
        migrations.AlterField(
            model_name="purchasereturnmaster",
            name="supplier",
            field=models.ForeignKey(
                db_column="inv_config_supplier_id",
                on_delete=django.db.models.deletion.PROTECT,
                to="inventory.supplier",
            ),
        ),
        migrations.AlterField(
            model_name="manualtransaction",
            name="supplier",
            field=models.ForeignKey(
                blank=False,
                db_column="inv_config_supplier_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="inventory.supplier",
            ),
        ),
        migrations.RunPython(forwards_codes, backwards_codes),
    ]
