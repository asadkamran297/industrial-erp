from django.contrib import admin

from .models import EmployeeSalary, Payroll


@admin.register(EmployeeSalary)
class EmployeeSalaryAdmin(admin.ModelAdmin):
    list_display = ("employee", "allowance_deduction", "allowance_deduction_type", "amount")
    list_filter = ("allowance_deduction_type", "allowance_deduction")
    search_fields = ("employee__full_name", "employee__cnic")


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ("employee", "month", "year", "base_salary", "net_salary", "status")
    list_filter = ("month", "year", "status")
    search_fields = ("employee__full_name", "employee__cnic")
