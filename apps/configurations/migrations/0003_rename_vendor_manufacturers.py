"""Rename the seeded Local/Global Vendor manufacturer rows to Supplier.

These are seeded master-data rows keyed by code, so the seeder would otherwise
create a second pair rather than update the existing one.
"""

from django.db import migrations

RENAMES = (
    ("LOCAL_VENDOR", "LOCAL_SUPPLIER", "Local Vendor", "Local Supplier"),
    ("GLOBAL_VENDOR", "GLOBAL_SUPPLIER", "Global Vendor", "Global Supplier"),
)


def _apply(apps, pairs):
    Manufacturer = apps.get_model("configurations", "Manufacturer")
    for old_code, new_code, old_title, new_title in pairs:
        if Manufacturer.objects.filter(code=new_code).exists():
            continue
        Manufacturer.objects.filter(code=old_code).update(code=new_code, title=new_title)


def forwards(apps, schema_editor):
    _apply(apps, RENAMES)


def backwards(apps, schema_editor):
    _apply(apps, [(new_c, old_c, new_t, old_t) for old_c, new_c, old_t, new_t in RENAMES])


class Migration(migrations.Migration):

    dependencies = [
        ("configurations", "0002_bank"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
