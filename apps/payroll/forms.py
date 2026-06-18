from django import forms
from django.core.exceptions import ValidationError

from apps.configurations.models import AllowanceDeduction
from apps.core.constants import STATUS_ACTIVE
from apps.core.forms import AutoSelectSingleChoiceMixin
from apps.hr.models import Employee

from .models import EmployeeSalary, Payroll


class EmployeeSalaryForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = EmployeeSalary
        fields = ("employee", "allowance_deduction", "amount")
        widgets = {
            "employee": forms.Select(attrs={"class": "form-select"}),
            "allowance_deduction": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(status=STATUS_ACTIVE).order_by("full_name")
        self.fields["allowance_deduction"].queryset = AllowanceDeduction.objects.filter(status=STATUS_ACTIVE).order_by("type", "title")
        if not self.instance.pk:
            self.initial.setdefault("amount", 0)

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get("employee")
        allowance_deduction = cleaned_data.get("allowance_deduction")
        if employee and allowance_deduction:
            qs = EmployeeSalary.objects.filter(employee=employee, allowance_deduction=allowance_deduction, deleted_at__isnull=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("allowance_deduction", "This allowance/deduction is already added for this employee.")
        return cleaned_data

    def save(self, commit=True):
        self.instance.allowance_deduction_type = self.cleaned_data["allowance_deduction"].type
        return super().save(commit)


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
