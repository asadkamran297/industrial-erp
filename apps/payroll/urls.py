from django.urls import path

from .views import (
    EmployeeSalaryCreateView,
    EmployeeSalaryDetailView,
    EmployeeSalaryListView,
    EmployeeSalaryUpdateView,
    PayrollCreateView,
    PayrollDeleteView,
    PayrollListView,
    PayrollUpdateView,
)

app_name = "payroll"

urlpatterns = [
    path("salary-items/", EmployeeSalaryListView.as_view(), name="employee_salary_list"),
    path("salary-items/new/", EmployeeSalaryCreateView.as_view(), name="employee_salary_create"),
    path("salary-items/<int:pk>/edit/", EmployeeSalaryUpdateView.as_view(), name="employee_salary_update"),
    path("salary-items/<int:pk>/", EmployeeSalaryDetailView.as_view(), name="employee_salary_detail"),
    path("payrolls/", PayrollListView.as_view(), name="payroll_list"),
    path("payrolls/new/", PayrollCreateView.as_view(), name="payroll_create"),
    path("payrolls/<int:pk>/edit/", PayrollUpdateView.as_view(), name="payroll_update"),
    path("payrolls/<int:pk>/delete/", PayrollDeleteView.as_view(), name="payroll_delete"),
]

from . import report_views as reports  # noqa: E402

urlpatterns += [
    path("reports/employees/", reports.EmployeeRegisterView.as_view(), name="report_employees"),
    path("reports/employees/export/", reports.EmployeeRegisterExportView.as_view(), name="report_employees_export"),
    path("reports/employees/columns/", reports.EmployeeRegisterColumnsView.as_view(), name="report_employees_columns"),
    path("reports/salary-sheet/", reports.SalarySheetView.as_view(), name="report_salary_sheet"),
    path("reports/salary-sheet/export/", reports.SalarySheetExportView.as_view(), name="report_salary_sheet_export"),
    path("reports/salary-sheet/columns/", reports.SalarySheetColumnsView.as_view(), name="report_salary_sheet_columns"),
    path("reports/payroll-summary/", reports.PayrollSummaryView.as_view(), name="report_payroll_summary"),
    path("reports/payroll-summary/export/", reports.PayrollSummaryExportView.as_view(), name="report_payroll_summary_export"),
    path("reports/payroll-summary/columns/", reports.PayrollSummaryColumnsView.as_view(), name="report_payroll_summary_columns"),
    path("reports/allowance-deduction/", reports.AllowanceDeductionView.as_view(), name="report_allowance_deduction"),
    path("reports/allowance-deduction/export/", reports.AllowanceDeductionExportView.as_view(), name="report_allowance_deduction_export"),
    path("reports/allowance-deduction/columns/", reports.AllowanceDeductionColumnsView.as_view(), name="report_allowance_deduction_columns"),
]
