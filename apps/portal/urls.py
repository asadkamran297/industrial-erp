from django.urls import path

from .report_views import (
    DailyPositionColumnsView,
    DailyPositionExportView,
    DailyPositionView,
    MonthGlanceColumnsView,
    MonthGlanceExportView,
    MonthGlanceView,
    PayablesAgingColumnsView,
    PayablesAgingExportView,
    PayablesAgingView,
    ProductProfitColumnsView,
    ProductProfitExportView,
    ProductProfitView,
    ReceivablesAgingColumnsView,
    ReceivablesAgingExportView,
    ReceivablesAgingView,
)
from .report_views_setup import (
    ChartOfAccountsColumnsView,
    ChartOfAccountsExportView,
    ChartOfAccountsView,
    PartyDirectoryColumnsView,
    PartyDirectoryExportView,
    PartyDirectoryView,
    ProductMasterColumnsView,
    ProductMasterExportView,
    ProductMasterView,
    UserAccessColumnsView,
    UserAccessExportView,
    UserAccessView,
)
from .views import DashboardView, FavouriteToggleView

app_name = "portal"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("favourites/toggle/", FavouriteToggleView.as_view(), name="favourite_toggle"),

    path("reports/daily-position/", DailyPositionView.as_view(), name="report_daily_position"),
    path("reports/daily-position/export/", DailyPositionExportView.as_view(), name="report_daily_position_export"),
    path("reports/daily-position/columns/", DailyPositionColumnsView.as_view(), name="report_daily_position_columns"),
    path("reports/month-glance/", MonthGlanceView.as_view(), name="report_month_glance"),
    path("reports/month-glance/export/", MonthGlanceExportView.as_view(), name="report_month_glance_export"),
    path("reports/month-glance/columns/", MonthGlanceColumnsView.as_view(), name="report_month_glance_columns"),
    path("reports/product-profit/", ProductProfitView.as_view(), name="report_product_profit"),
    path("reports/product-profit/export/", ProductProfitExportView.as_view(), name="report_product_profit_export"),
    path("reports/product-profit/columns/", ProductProfitColumnsView.as_view(), name="report_product_profit_columns"),
    path("reports/receivables-aging/", ReceivablesAgingView.as_view(), name="report_receivables_aging"),
    path("reports/receivables-aging/export/", ReceivablesAgingExportView.as_view(), name="report_receivables_aging_export"),
    path("reports/receivables-aging/columns/", ReceivablesAgingColumnsView.as_view(), name="report_receivables_aging_columns"),
    path("reports/payables-aging/", PayablesAgingView.as_view(), name="report_payables_aging"),
    path("reports/payables-aging/export/", PayablesAgingExportView.as_view(), name="report_payables_aging_export"),
    path("reports/payables-aging/columns/", PayablesAgingColumnsView.as_view(), name="report_payables_aging_columns"),

    path("reports/party-directory/", PartyDirectoryView.as_view(), name="report_party_directory"),
    path("reports/party-directory/export/", PartyDirectoryExportView.as_view(), name="report_party_directory_export"),
    path("reports/party-directory/columns/", PartyDirectoryColumnsView.as_view(), name="report_party_directory_columns"),
    path("reports/product-master/", ProductMasterView.as_view(), name="report_product_master"),
    path("reports/product-master/export/", ProductMasterExportView.as_view(), name="report_product_master_export"),
    path("reports/product-master/columns/", ProductMasterColumnsView.as_view(), name="report_product_master_columns"),
    path("reports/chart-of-accounts/", ChartOfAccountsView.as_view(), name="report_chart_of_accounts"),
    path("reports/chart-of-accounts/export/", ChartOfAccountsExportView.as_view(), name="report_chart_of_accounts_export"),
    path("reports/chart-of-accounts/columns/", ChartOfAccountsColumnsView.as_view(), name="report_chart_of_accounts_columns"),
    path("reports/user-access/", UserAccessView.as_view(), name="report_user_access"),
    path("reports/user-access/export/", UserAccessExportView.as_view(), name="report_user_access_export"),
    path("reports/user-access/columns/", UserAccessColumnsView.as_view(), name="report_user_access_columns"),
]
