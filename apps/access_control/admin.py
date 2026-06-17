from django.contrib import admin

from .models import Permission, Role, RolePermission, UserAssignment


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("title", "status")
    search_fields = ("title",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "seq", "status")
    search_fields = ("title", "code")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")
    list_filter = ("role",)


@admin.register(UserAssignment)
class UserAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "organization", "branch", "is_primary", "status")
    list_filter = ("role", "organization", "branch", "status", "is_primary")
