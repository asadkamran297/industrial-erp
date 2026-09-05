from django.contrib import admin

from .models import (
    FinishBardanaLink,
    ProductAccountLink,
    ProductLedger,
    ProductNode,
    ProductOpeningBalance,
    ProductRate,
    RawBardanaLink,
)


@admin.register(ProductNode)
class ProductNodeAdmin(admin.ModelAdmin):
    list_display = ("display_code", "name", "level", "specification", "unit", "status")
    list_filter = ("level", "specification", "status")
    search_fields = ("name", "complete_code", "quick_code")
    ordering = ("complete_code",)


@admin.register(ProductAccountLink)
class ProductAccountLinkAdmin(admin.ModelAdmin):
    list_display = ("product", "purchase_account")
    search_fields = ("product__name",)


@admin.register(RawBardanaLink)
class RawBardanaLinkAdmin(admin.ModelAdmin):
    list_display = ("wheat_item", "bardana_item")


@admin.register(FinishBardanaLink)
class FinishBardanaLinkAdmin(admin.ModelAdmin):
    list_display = ("finish_item", "bag_item")


@admin.register(ProductOpeningBalance)
class ProductOpeningBalanceAdmin(admin.ModelAdmin):
    list_display = ("product", "as_of_date", "quantity", "rate")


@admin.register(ProductRate)
class ProductRateAdmin(admin.ModelAdmin):
    list_display = ("product", "rate", "effective_date", "is_current")
    list_filter = ("is_current",)


@admin.register(ProductLedger)
class ProductLedgerAdmin(admin.ModelAdmin):
    list_display = ("product", "entry_date", "source", "reference", "quantity")
    list_filter = ("source",)
    search_fields = ("product__name", "reference")
