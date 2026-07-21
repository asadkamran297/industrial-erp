from django.urls import path

from .views import (
    AccountConfigurationCreateView,
    AccountConfigurationListView,
    AccountConfigurationUpdateView,
    ChartOfAccountCreateView,
    ChartOfAccountDeleteView,
    ChartOfAccountRenameView,
    ChartOfAccountReorderView,
    ChartOfAccountTreeView,
    AccountVoucherCreateView,
    AccountVoucherDetailView,
    AccountVoucherLineCreateView,
    AccountVoucherLineDeleteView,
    AccountVoucherListView,
    AccountVoucherUpdateView,
    FiscalPeriodSetActiveView,
    FiscalYearToggleActiveView,
    FiscalYearCreateView,
    FiscalYearListView,
    FiscalYearUpdateView,
)

app_name = "finance"

urlpatterns = [
    path("fiscal-years/", FiscalYearListView.as_view(), name="fiscal_year_list"),
    path("fiscal-years/new/", FiscalYearCreateView.as_view(), name="fiscal_year_create"),
    path("fiscal-years/<int:pk>/edit/", FiscalYearUpdateView.as_view(), name="fiscal_year_update"),
    path("fiscal-years/<int:pk>/set-active-period/", FiscalPeriodSetActiveView.as_view(), name="fiscal_period_set_active"),
    path("fiscal-years/<int:pk>/toggle-active/", FiscalYearToggleActiveView.as_view(), name="fiscal_year_toggle_active"),
    path("accounts/", AccountConfigurationListView.as_view(), name="account_configuration_list"),
    path("accounts/new/", AccountConfigurationCreateView.as_view(), name="account_configuration_create"),
    path("accounts/<int:pk>/edit/", AccountConfigurationUpdateView.as_view(), name="account_configuration_update"),
    path("chart-of-accounts/", ChartOfAccountTreeView.as_view(), name="chart_of_accounts"),
    path("chart-of-accounts/create/", ChartOfAccountCreateView.as_view(), name="coa_create"),
    path("chart-of-accounts/reorder/", ChartOfAccountReorderView.as_view(), name="coa_reorder"),
    path("chart-of-accounts/<int:pk>/rename/", ChartOfAccountRenameView.as_view(), name="coa_rename"),
    path("chart-of-accounts/<int:pk>/delete/", ChartOfAccountDeleteView.as_view(), name="coa_delete"),
    path("vouchers/", AccountVoucherListView.as_view(), name="account_voucher_list"),
    path("vouchers/new/", AccountVoucherCreateView.as_view(), name="account_voucher_create"),
    path("vouchers/<int:pk>/", AccountVoucherDetailView.as_view(), name="account_voucher_detail"),
    path("vouchers/<int:pk>/edit/", AccountVoucherUpdateView.as_view(), name="account_voucher_update"),
    path("vouchers/<int:voucher_pk>/lines/new/", AccountVoucherLineCreateView.as_view(), name="account_voucher_line_create"),
    path("vouchers/<int:voucher_pk>/lines/<int:pk>/delete/", AccountVoucherLineDeleteView.as_view(), name="account_voucher_line_delete"),
]
