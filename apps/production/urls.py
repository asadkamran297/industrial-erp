from django.urls import path

from . import report_views as rv

from .views import (
    ConversionDeleteView,
    ConversionDetailView,
    ConversionFormView,
    ConversionListView,
    ConversionUpdateView,
    GrindingDeleteView,
    GrindingDetailView,
    GrindingFormView,
    GrindingListView,
    GrindingOptionsView,
    GrindingPrintView,
    GrindingUpdateView,
)

app_name = "production"

urlpatterns = [
    path("grinding/", GrindingListView.as_view(), name="grinding_list"),
    path("grinding/new/", GrindingFormView.as_view(), name="grinding_create"),
    path("grinding/options/", GrindingOptionsView.as_view(), name="grinding_options"),
    path("grinding/<int:pk>/", GrindingDetailView.as_view(), name="grinding_detail"),
    path("grinding/<int:pk>/edit/", GrindingUpdateView.as_view(), name="grinding_update"),
    path("grinding/<int:pk>/print/", GrindingPrintView.as_view(), name="grinding_print"),
    path("grinding/<int:pk>/delete/", GrindingDeleteView.as_view(), name="grinding_delete"),

    path("conversions/", ConversionListView.as_view(), name="conversion_list"),
    path("conversions/new/", ConversionFormView.as_view(), name="conversion_create"),
    path("conversions/<int:pk>/", ConversionDetailView.as_view(), name="conversion_detail"),
    path("conversions/<int:pk>/edit/", ConversionUpdateView.as_view(), name="conversion_update"),
    path("conversions/<int:pk>/delete/", ConversionDeleteView.as_view(), name="conversion_delete"),

    path("reports/grinding-register/", rv.GrindingRegisterView.as_view(), name="report_grinding_register"),
    path("reports/grinding-register/export/", rv.GrindingRegisterExportView.as_view(), name="report_grinding_register_export"),
    path("reports/grinding-register/columns/", rv.GrindingRegisterColumnsView.as_view(), name="report_grinding_register_columns"),
    path("reports/daily-grinding/", rv.DailyGrindingView.as_view(), name="report_daily_grinding"),
    path("reports/daily-grinding/export/", rv.DailyGrindingExportView.as_view(), name="report_daily_grinding_export"),
    path("reports/daily-grinding/columns/", rv.DailyGrindingColumnsView.as_view(), name="report_daily_grinding_columns"),
    path("reports/yield-trend/", rv.YieldTrendView.as_view(), name="report_yield_trend"),
    path("reports/yield-trend/export/", rv.YieldTrendExportView.as_view(), name="report_yield_trend_export"),
    path("reports/yield-trend/columns/", rv.YieldTrendColumnsView.as_view(), name="report_yield_trend_columns"),
    path("reports/output-mix/", rv.OutputMixView.as_view(), name="report_output_mix"),
    path("reports/output-mix/export/", rv.OutputMixExportView.as_view(), name="report_output_mix_export"),
    path("reports/output-mix/columns/", rv.OutputMixColumnsView.as_view(), name="report_output_mix_columns"),
    path("reports/shortage/", rv.ShortageReportView.as_view(), name="report_shortage"),
    path("reports/shortage/export/", rv.ShortageReportExportView.as_view(), name="report_shortage_export"),
    path("reports/shortage/columns/", rv.ShortageReportColumnsView.as_view(), name="report_shortage_columns"),
    path("reports/conversions/", rv.ConversionRegisterView.as_view(), name="report_conversions"),
    path("reports/conversions/export/", rv.ConversionRegisterExportView.as_view(), name="report_conversions_export"),
    path("reports/conversions/columns/", rv.ConversionRegisterColumnsView.as_view(), name="report_conversions_columns"),
    path("reports/cost-per-bag/", rv.CostPerBagView.as_view(), name="report_cost_per_bag"),
    path("reports/cost-per-bag/export/", rv.CostPerBagExportView.as_view(), name="report_cost_per_bag_export"),
    path("reports/cost-per-bag/columns/", rv.CostPerBagColumnsView.as_view(), name="report_cost_per_bag_columns"),
    path("reports/production-summary/", rv.ProductionSummaryView.as_view(), name="report_production_summary"),
    path("reports/production-summary/export/", rv.ProductionSummaryExportView.as_view(), name="report_production_summary_export"),
    path("reports/production-summary/columns/", rv.ProductionSummaryColumnsView.as_view(), name="report_production_summary_columns"),
]
