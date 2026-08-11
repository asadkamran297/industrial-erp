"""Re-key the vendor page permissions to supplier.

Permission codes are stored rows, so renaming the page in ``pages.py`` alone
would orphan every role that already grants ``inventory.vendors.*``. Updating
the rows in place keeps existing role grants intact.
"""

from django.db import migrations

OLD_PREFIX = "inventory.vendors."
NEW_PREFIX = "inventory.suppliers."


def _swap(apps, old_prefix, new_prefix, old_word, new_word):
    Permission = apps.get_model("access_control", "Permission")
    for permission in Permission.objects.filter(code__startswith=old_prefix):
        permission.code = new_prefix + permission.code[len(old_prefix):]
        permission.title = permission.title.replace(old_word, new_word)
        permission.save(update_fields=["code", "title"])


def forwards(apps, schema_editor):
    _swap(apps, OLD_PREFIX, NEW_PREFIX, "Vendors", "Suppliers")


def backwards(apps, schema_editor):
    _swap(apps, NEW_PREFIX, OLD_PREFIX, "Suppliers", "Vendors")


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0002_alter_rolepermission_permission_and_more"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
