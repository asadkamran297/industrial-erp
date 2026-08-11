"""Drop the retired Current Stock page permissions.

The stock figures moved onto the item list, so the page — and the codes any
role was granted for it — no longer exist. Reversing re-creates the codes; the
role grants that referenced them are not restored.
"""

from django.db import migrations

PREFIX = "inventory.stock."
REVERSE_ROWS = (
    ("inventory.stock.index", "List Current Stock"),
    ("inventory.stock.view", "View Current Stock"),
)


def forwards(apps, schema_editor):
    Permission = apps.get_model("access_control", "Permission")
    Permission.objects.filter(code__startswith=PREFIX).delete()


def backwards(apps, schema_editor):
    Permission = apps.get_model("access_control", "Permission")
    for code, title in REVERSE_ROWS:
        Permission.objects.get_or_create(code=code, defaults={"title": title, "seq": 0})


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0003_rename_vendor_permissions"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
