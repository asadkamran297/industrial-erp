"""Wheat and bardana lines on the purchase invoice.

A line now names a stores item or a product, never both and never neither --
the check constraint says so, not just the service. Stores items keep the
inventory ledger; wheat and bardana post to the product ledger that grinding
reads, so the mill never holds two answers to how much wheat is in the godown.

The weight columns are filled only on a wheat line. They are columns rather
than JSON because they decide the money and the quantity that reaches the
ledger: credit_weight is the paid weight, stored as it was worked out, so a
later change to the deduction rules cannot silently restate an old purchase.

Every column is nullable and every existing line names an inventory item, so
nothing already entered is touched or has to be backfilled.
"""


import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0047_purchase_godown_vehicle_broker'),
        ('products', '0002_productledger_bardana_item_productledger_godown_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='credit_weight',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='katla',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='khoot',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='mill_weight',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='moisture',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='party_weight',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='product',
            field=models.ForeignKey(blank=True, db_column='prod_node_id', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='purchase_lines', to='products.productnode'),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='rate_per_mund',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='sack_weight_deduction',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoiceline',
            name='selected_weight',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AlterField(
            model_name='purchaseinvoiceline',
            name='inventory_item',
            field=models.ForeignKey(blank=True, db_column='inv_inventory_code_id', null=True, on_delete=django.db.models.deletion.PROTECT, to='inventory.inventoryitem'),
        ),
        migrations.AddIndex(
            model_name='purchaseinvoiceline',
            index=models.Index(fields=['product', '-id'], name='inv_pi_line_product_idx'),
        ),
        migrations.AddConstraint(
            model_name='purchaseinvoiceline',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('inventory_item__isnull', False), ('product__isnull', True)), models.Q(('inventory_item__isnull', True), ('product__isnull', False)), _connector='OR'), name='inv_pi_line_one_item_kind'),
        ),
    ]
