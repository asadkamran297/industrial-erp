from django.urls import path

from .views import (
    AccountLinkView,
    CodePreviewView,
    FinishBardanaLinkView,
    OpeningBalanceView,
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
    path("code-preview/", CodePreviewView.as_view(), name="code_preview"),
    path("<int:pk>/edit/", ProductUpdateView.as_view(), name="product_update"),
    path("<int:pk>/toggle-status/", ProductStatusToggleView.as_view(), name="product_status_toggle"),
    path("account-linking/", AccountLinkView.as_view(), name="account_linking"),
    path("raw-bardana-linking/", RawBardanaLinkView.as_view(), name="raw_bardana_linking"),
    path("finish-bardana-linking/", FinishBardanaLinkView.as_view(), name="finish_bardana_linking"),
    path("opening-balance/", OpeningBalanceView.as_view(), name="opening_balance"),
    path("rate-update/", RateUpdateView.as_view(), name="rate_update"),
]
