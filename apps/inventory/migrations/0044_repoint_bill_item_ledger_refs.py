"""Point the stock ledger at the invoice that replaced the bill.

Migration 0038 moved every purchase bill onto a ``PurchaseInvoice`` and rewrote
the vouchers that named it, but the item ledger was left naming
``inv_purchase_bills`` and a row id in a table that 0041 then dropped. The
quantities were always right -- stock never moved -- so this is the audit trail
only: 189 rows whose drill-through leads nowhere.

The match is ``ref_no`` against ``legacy_bill_no``, which is the bill number the
invoice carries precisely so this link can be rebuilt. No quantity, price or
running balance is touched. A row whose bill number finds no invoice is left
exactly as it is rather than guessed at.
"""

from django.db import migrations

BILL_TABLE = "inv_purchase_bills"
INVOICE_TABLE = "inv_purchase_invoices"


def forwards(apps, schema_editor):
    ItemLedger = apps.get_model("inventory", "ItemLedger")
    PurchaseInvoice = apps.get_model("inventory", "PurchaseInvoice")

    invoices = {
        row["legacy_bill_no"]: row
        for row in PurchaseInvoice.objects.exclude(legacy_bill_no="").values("id", "invoice_num", "legacy_bill_no")
    }
    if not invoices:
        return

    for entry in ItemLedger.objects.filter(ref_table=BILL_TABLE).iterator():
        invoice = invoices.get(entry.ref_no)
        if not invoice:
            continue
        entry.ref_table = INVOICE_TABLE
        entry.ref_id = invoice["id"]
        entry.ref_no = invoice["invoice_num"]
        entry.save(update_fields=["ref_table", "ref_id", "ref_no"])


def backwards(apps, schema_editor):
    """Send the rows back to the bill number they came from.

    Lossy on purpose: the bill row ids died with the table in 0041, so ``ref_id``
    keeps pointing at the invoice. Reversing restores the name, not the id.
    """
    ItemLedger = apps.get_model("inventory", "ItemLedger")
    PurchaseInvoice = apps.get_model("inventory", "PurchaseInvoice")

    invoices = {
        row["invoice_num"]: row
        for row in PurchaseInvoice.objects.exclude(legacy_bill_no="").values("id", "invoice_num", "legacy_bill_no")
    }
    for entry in ItemLedger.objects.filter(ref_table=INVOICE_TABLE).iterator():
        invoice = invoices.get(entry.ref_no)
        if not invoice or invoice["id"] != entry.ref_id:
            continue
        entry.ref_table = BILL_TABLE
        entry.ref_no = invoice["legacy_bill_no"]
        entry.save(update_fields=["ref_table", "ref_no"])


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0043_purchase_invoice_extra_data"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
