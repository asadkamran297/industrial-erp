from django.contrib import admin

from .models import Branch, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "parent", "status")
    search_fields = ("title", "code")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "organization", "city", "status")
    search_fields = ("title", "code", "email", "phone")
    list_filter = ("organization", "city", "status")
