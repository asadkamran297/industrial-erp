from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Portal profile", {"fields": ("phone", "avatar", "designation", "user_type")}),
    )
    list_display = ("username", "email", "user_type", "designation", "is_staff", "is_active")
    list_filter = UserAdmin.list_filter + ("user_type",)
