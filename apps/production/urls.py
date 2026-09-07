from django.urls import path

from .views import (
    ConversionDeleteView,
    ConversionDetailView,
    ConversionFormView,
    ConversionListView,
    ConversionUpdateView,
    DailyGrindingReportView,
    GrindingDeleteView,
    GrindingDetailView,
    GrindingFormView,
    GrindingListView,
    GrindingOptionsView,
    GrindingPrintView,
    GrindingUpdateView,
    ProductionSummaryReportView,
    YieldTrendReportView,
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

    path("reports/daily-grinding/", DailyGrindingReportView.as_view(), name="report_daily_grinding"),
    path("reports/yield-trend/", YieldTrendReportView.as_view(), name="report_yield_trend"),
    path("reports/production-summary/", ProductionSummaryReportView.as_view(), name="report_production_summary"),
]
