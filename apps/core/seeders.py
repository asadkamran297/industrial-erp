from apps.core.models import SystemSetting


def seed_system_settings() -> int:
    _, created = SystemSetting.objects.update_or_create(
        pk=1,
        defaults={
            "company_name": "Industrial ERP",
            "company_tagline": "Official MIS Portal",
            "md_message": "Please use this system responsibly for official work only.",
            "mis_helpline_phone": "+92-000-0000000",
            "mis_helpline_email": "mis@example.com",
            "support_phone": "+92-000-0000000",
            "support_email": "support@example.com",
            "primary_color": "#2563eb",
            "secondary_color": "#0f172a",
            "default_theme": "light",
            "footer_text": "Authorized users only.",
        },
    )
    return 1 if created else 0
