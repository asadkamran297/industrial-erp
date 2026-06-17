from django.contrib import admin

from .models import SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("company_name", "default_theme", "support_email", "updated_at")
    fieldsets = (
        ("Company", {"fields": ("company_name", "company_logo", "company_tagline")}),
        ("Managing Director", {"fields": ("md_name", "md_picture", "md_message")}),
        ("Support", {"fields": ("mis_helpline_phone", "mis_helpline_email", "support_phone", "support_email")}),
        ("Theme", {"fields": ("primary_color", "secondary_color", "default_theme", "login_background_image")}),
        ("Footer", {"fields": ("footer_text",)}),
    )
