from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Portal profile",
            {
                "fields": (
                    "employee",
                    "name",
                    "phone",
                    "whatsapp",
                    "address",
                    "cnic",
                    "avatar",
                    "designation",
                    "user_type",
                    "status",
                    "last_login_timestamp",
                    "last_password_changed",
                    "temp_pwd",
                )
            },
        ),
    )
    list_display = ("username", "email", "phone", "user_type", "designation", "status", "is_staff", "is_active")
    list_filter = UserAdmin.list_filter + ("user_type", "status")
