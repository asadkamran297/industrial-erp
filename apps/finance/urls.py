from django.urls import path

from .views import (
    AccountConfigurationCreateView,
    AccountConfigurationListView,
    AccountConfigurationUpdateView,
    AccountVoucherCreateView,
    AccountVoucherDetailView,
    AccountVoucherLineCreateView,
    AccountVoucherLineDeleteView,
    AccountVoucherListView,
    AccountVoucherUpdateView,
    FiscalYearCreateView,
    FiscalYearListView,
    FiscalYearUpdateView,
)

app_name = "finance"

urlpatterns = [
    path("fiscal-years/", FiscalYearListView.as_view(), name="fiscal_year_list"),
    path("fiscal-years/new/", FiscalYearCreateView.as_view(), name="fiscal_year_create"),
    path("fiscal-years/<int:pk>/edit/", FiscalYearUpdateView.as_view(), name="fiscal_year_update"),
    path("accounts/", AccountConfigurationListView.as_view(), name="account_configuration_list"),
    path("accounts/new/", AccountConfigurationCreateView.as_view(), name="account_configuration_create"),
    path("accounts/<int:pk>/edit/", AccountConfigurationUpdateView.as_view(), name="account_configuration_update"),
    path("vouchers/", AccountVoucherListView.as_view(), name="account_voucher_list"),
    path("vouchers/new/", AccountVoucherCreateView.as_view(), name="account_voucher_create"),
    path("vouchers/<int:pk>/", AccountVoucherDetailView.as_view(), name="account_voucher_detail"),
    path("vouchers/<int:pk>/edit/", AccountVoucherUpdateView.as_view(), name="account_voucher_update"),
    path("vouchers/<int:voucher_pk>/lines/new/", AccountVoucherLineCreateView.as_view(), name="account_voucher_line_create"),
    path("vouchers/<int:voucher_pk>/lines/<int:pk>/delete/", AccountVoucherLineDeleteView.as_view(), name="account_voucher_line_delete"),
]
