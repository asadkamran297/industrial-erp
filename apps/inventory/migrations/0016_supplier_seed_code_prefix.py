"""Re-prefix the seeded supplier codes: VND001 -> SUP001.

The seeder hands out its own fixed codes, separate from ``Supplier.next_code``,
so they need the same word swap the rest of the rename got.
"""

from django.db import migrations


def _swap(apps, old_prefix, new_prefix):
    Supplier = apps.get_model("inventory", "Supplier")
    for supplier in Supplier.objects.filter(code__startswith=old_prefix):
        tail = supplier.code[len(old_prefix):]
        if not tail.isdigit():
            continue  # leaves the dashed next_code() sequence alone
        candidate = new_prefix + tail
        if Supplier.objects.filter(code=candidate).exists():
            continue
        supplier.code = candidate
        supplier.save(update_fields=["code"])


def forwards(apps, schema_editor):
    _swap(apps, "VND", "SUP")


def backwards(apps, schema_editor):
    _swap(apps, "SUP", "VND")


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0015_rename_vendor_to_supplier"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
