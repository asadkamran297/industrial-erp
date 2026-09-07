"""Godown, vehicle and broker on the two purchase documents.

Three facts a mill writes on every purchase and had nowhere to put: where the
goods are expected or were received, which truck brought them, and who arranged
the deal. All nullable -- every existing order and invoice predates them, and a
purchase entered without a broker is a purchase with no broker rather than an
incomplete one.

The godown is recorded on the document only. Stock is still one pool per item,
so this says where goods should arrive; it does not hold a per-godown balance.

The broker is an account, not a name, because brokerage is owed to them and has
to settle on its own. The heading they hang under is created here so the picker
has somewhere to look; the brokers themselves are added by the site.
"""

from django.db import migrations, models
import django.db.models.deletion

BROKERS_PATH = ("LIABILITIES", "Current Liabilities", "Brokers")


def create_brokers_group(apps, schema_editor):
    """Add the Brokers heading if the chart has no such heading yet."""
    ChartOfAccount = apps.get_model("finance", "ChartOfAccount")

    node = None
    for title in BROKERS_PATH:
        found = ChartOfAccount.objects.filter(parent=node, title=title).first()
        if found is None:
            if node is None:
                # The root is not ours to invent: a chart without LIABILITIES
                # has not been set up, and guessing its account_type here would
                # be a second opinion about the shape of the books.
                return
            found = ChartOfAccount.objects.create(
                parent=node, title=title, account_type=node.account_type,
                is_group=True, sort_order=(
                    ChartOfAccount.objects.filter(parent=node).order_by("-sort_order")
                    .values_list("sort_order", flat=True).first() or 0
                ) + 1,
            )
        node = found


def drop_brokers_group(apps, schema_editor):
    """Remove the heading only while it is still empty."""
    ChartOfAccount = apps.get_model("finance", "ChartOfAccount")
    group = ChartOfAccount.objects.filter(title=BROKERS_PATH[-1], is_group=True).first()
    if group and not ChartOfAccount.objects.filter(parent=group).exists():
        group.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0046_legacy_purchase_master_index"),
        ("godowns", "0001_initial"),
        ("finance", "0004_chartofaccount"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="godown",
            field=models.ForeignKey(
                null=True, blank=True, db_column="godown_id", related_name="purchase_orders",
                on_delete=django.db.models.deletion.PROTECT, to="godowns.godown",
            ),
        ),
        migrations.AddField(
            model_name="purchaseorder",
            name="broker",
            field=models.ForeignKey(
                null=True, blank=True, db_column="broker_account_id", related_name="broker_purchase_orders",
                on_delete=django.db.models.deletion.PROTECT, to="finance.chartofaccount",
            ),
        ),
        migrations.AddField(
            model_name="purchaseinvoice",
            name="godown",
            field=models.ForeignKey(
                null=True, blank=True, db_column="godown_id", related_name="purchase_invoices",
                on_delete=django.db.models.deletion.PROTECT, to="godowns.godown",
            ),
        ),
        migrations.AddField(
            model_name="purchaseinvoice",
            name="vehicle_no",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="purchaseinvoice",
            name="broker",
            field=models.ForeignKey(
                null=True, blank=True, db_column="broker_account_id", related_name="broker_purchase_invoices",
                on_delete=django.db.models.deletion.PROTECT, to="finance.chartofaccount",
            ),
        ),
        # Indexes ship with the columns, not in a later pass: the godown filter
        # on both list screens reads exactly these.
        migrations.AddIndex(
            model_name="purchaseorder",
            index=models.Index(fields=["godown", "-purchase_date"], name="inv_po_godown_date_idx"),
        ),
        migrations.AddIndex(
            model_name="purchaseinvoice",
            index=models.Index(fields=["godown", "-invoice_date"], name="inv_pi_godown_date_idx"),
        ),
        migrations.RunPython(create_brokers_group, drop_brokers_group),
    ]
