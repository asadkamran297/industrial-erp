from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import AutoSelectSingleChoiceMixin

from .models import EmployeeSalary, Payroll


class EmployeeSalaryForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = EmployeeSalary
        fields = ("employee", "allowance_deduction", "allowance_deduction_type", "amount")
        widgets = {
            "employee": forms.Select(attrs={"class": "form-select"}),
            "allowance_deduction": forms.Select(attrs={"class": "form-select"}),
            "allowance_deduction_type": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
        }


class PayrollForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = Payroll
        fields = ("employee", "month", "year", "base_salary", "total_allowances", "total_deductions", "net_salary", "status")
        widgets = {
            "employee": forms.Select(attrs={"class": "form-select"}),
            "month": forms.NumberInput(attrs={"class": "form-input", "min": 1, "max": 12}),
            "year": forms.NumberInput(attrs={"class": "form-input", "min": 2000, "max": 2100}),
            "base_salary": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "total_allowances": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "total_deductions": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "net_salary": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get("employee")
        month = cleaned_data.get("month")
        year = cleaned_data.get("year")
        if month and not 1 <= month <= 12:
            self.add_error("month", "Month must be between 1 and 12.")
        if employee and month and year:
            qs = Payroll.objects.filter(employee=employee, month=month, year=year)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Payroll for this employee and month already exists.")
        return cleaned_data
