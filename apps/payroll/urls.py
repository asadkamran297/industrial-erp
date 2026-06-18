from django.urls import path

from .views import (
    EmployeeSalaryCreateView,
    EmployeeSalaryDeleteView,
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
    path("salary-items/<int:pk>/delete/", EmployeeSalaryDeleteView.as_view(), name="employee_salary_delete"),
    path("payrolls/", PayrollListView.as_view(), name="payroll_list"),
    path("payrolls/new/", PayrollCreateView.as_view(), name="payroll_create"),
    path("payrolls/<int:pk>/edit/", PayrollUpdateView.as_view(), name="payroll_update"),
    path("payrolls/<int:pk>/delete/", PayrollDeleteView.as_view(), name="payroll_delete"),
]
