from django.urls import path

from . import report_views as rv

from .views import (
    AccountLinkView,
    CodePreviewView,
    FinishBardanaLinkView,
    OpeningBalanceView,
    PartyBardanaListView,
    ProductColumnsView,
    ProductDetailView,
    ProductCreateView,
    ProductListView,
    ProductStatusToggleView,
    ProductUpdateView,
    RateUpdateView,
    RawBardanaLinkView,
)

app_name = "products"

urlpatterns = [
    path("", ProductListView.as_view(), name="product_list"),
    path("new/", ProductCreateView.as_view(), name="product_create"),
    path("columns/", ProductColumnsView.as_view(), name="product_columns"),
    path("code-preview/", CodePreviewView.as_view(), name="code_preview"),
    path("<int:pk>/", ProductDetailView.as_view(), name="product_detail"),
    path("<int:pk>/edit/", ProductUpdateView.as_view(), name="product_update"),
    path("<int:pk>/toggle-status/", ProductStatusToggleView.as_view(), name="product_status_toggle"),
    path("account-linking/", AccountLinkView.as_view(), name="account_linking"),
    path("raw-bardana-linking/", RawBardanaLinkView.as_view(), name="raw_bardana_linking"),
    path("finish-bardana-linking/", FinishBardanaLinkView.as_view(), name="finish_bardana_linking"),
    path("opening-balance/", OpeningBalanceView.as_view(), name="opening_balance"),
    path("rate-update/", RateUpdateView.as_view(), name="rate_update"),
    path("party-bardana/", PartyBardanaListView.as_view(), name="party_bardana"),
    path("reports/bardana-stock/", rv.BardanaStockView.as_view(), name="report_bardana_stock"),
    path("reports/bardana-stock/export/", rv.BardanaStockExportView.as_view(), name="report_bardana_stock_export"),
    path("reports/bardana-stock/columns/", rv.BardanaStockColumnsView.as_view(), name="report_bardana_stock_columns"),
    path("reports/party-bardana-balances/", rv.PartyBardanaBalancesView.as_view(), name="report_party_bardana"),
    path("reports/party-bardana-balances/export/", rv.PartyBardanaBalancesExportView.as_view(), name="report_party_bardana_export"),
    path("reports/party-bardana-balances/columns/", rv.PartyBardanaBalancesColumnsView.as_view(), name="report_party_bardana_columns"),
    path("reports/bardana-movements/", rv.BardanaMovementView.as_view(), name="report_bardana_movements"),
    path("reports/bardana-movements/export/", rv.BardanaMovementExportView.as_view(), name="report_bardana_movements_export"),
    path("reports/bardana-movements/columns/", rv.BardanaMovementColumnsView.as_view(), name="report_bardana_movements_columns"),
    path("reports/packing-consumption/", rv.PackingConsumptionView.as_view(), name="report_packing_consumption"),
    path("reports/packing-consumption/export/", rv.PackingConsumptionExportView.as_view(), name="report_packing_consumption_export"),
    path("reports/packing-consumption/columns/", rv.PackingConsumptionColumnsView.as_view(), name="report_packing_consumption_columns"),
]
