from django.contrib import admin

from .models import GrindingOutput, GrindingVoucher, ProductConversion, ProductConversionLine


class GrindingOutputInline(admin.TabularInline):
    model = GrindingOutput
    extra = 0


@admin.register(GrindingVoucher)
class GrindingVoucherAdmin(admin.ModelAdmin):
    list_display = ("voucher_no", "date", "wheat_item", "disposal_wheat", "total_output_kg", "yield_percent")
    list_filter = ("godown", "date")
    search_fields = ("voucher_no", "wheat_item__name", "issue_area")
    inlines = [GrindingOutputInline]


class ProductConversionLineInline(admin.TabularInline):
    model = ProductConversionLine
    extra = 0


@admin.register(ProductConversion)
class ProductConversionAdmin(admin.ModelAdmin):
    list_display = ("voucher_no", "date", "source_product", "source_quantity", "total_output_kg")
    list_filter = ("godown", "date")
    search_fields = ("voucher_no", "source_product__name")
    inlines = [ProductConversionLineInline]
