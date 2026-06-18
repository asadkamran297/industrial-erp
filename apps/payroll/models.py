from django.conf import settings
from django.db import models

from apps.core.constants import ALLOWANCE_DEDUCTION_TYPE_CHOICES, STATUS_PENDING, WORKFLOW_STATUS_CHOICES
from apps.core.models import BaseModel


class EmployeeSalary(BaseModel):
    employee = models.ForeignKey("hr.Employee", related_name="salary_items", on_delete=models.CASCADE, db_column="hr_employee_id")
    allowance_deduction = models.ForeignKey(
        "configurations.AllowanceDeduction", related_name="employee_salary_items", on_delete=models.PROTECT, db_column="conf_allowance_deduction_id"
    )
    allowance_deduction_type = models.CharField(max_length=20, choices=ALLOWANCE_DEDUCTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "hr_employee_salaries"
        ordering = ["employee", "allowance_deduction_type"]

    def __str__(self) -> str:
        return f"{self.employee} - {self.allowance_deduction}"


class Payroll(BaseModel):
    employee = models.ForeignKey("hr.Employee", related_name="payrolls", on_delete=models.PROTECT, db_column="hr_employee_id")
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    base_salary = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_allowances = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=WORKFLOW_STATUS_CHOICES, default=STATUS_PENDING)
    generated_at = models.DateTimeField(null=True, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="generated_payrolls", on_delete=models.SET_NULL
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="approved_payrolls", on_delete=models.SET_NULL
    )

    class Meta:
        db_table = "hr_payrolls"
        ordering = ["-year", "-month", "employee"]
        unique_together = ("employee", "month", "year")

    def __str__(self) -> str:
        return f"{self.employee} - {self.month}/{self.year}"
