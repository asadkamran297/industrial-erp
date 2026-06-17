from django.db import migrations


def seed_system_setting(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    SystemSetting.objects.get_or_create(
        pk=1,
        defaults={
            "company_name": "Industrial ERP",
            "company_tagline": "Official MIS Portal",
            "md_message": "Please use this system responsibly for official work only.",
            "primary_color": "#2563eb",
            "secondary_color": "#0f172a",
            "default_theme": "light",
            "footer_text": "Authorized users only.",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_system_setting, migrations.RunPython.noop),
    ]
