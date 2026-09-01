"""Demo employees, their salary components and a payroll run."""

from decimal import Decimal

from django.utils import timezone

from apps.configurations.models import AllowanceDeduction, Bank, Department, Designation, JobType
from apps.core.constants import ALLOWANCE, DEDUCTION, STATUS_ACTIVE, STATUS_APPROVED, STATUS_PENDING
from apps.hr.models import Employee
from apps.organizations.models import Branch, Organization
from apps.payroll.models import EmployeeSalary, Payroll

FIRST_NAMES = [
    "Ahsan", "Maham", "Bilal", "Sana", "Usman", "Hira", "Danish", "Zoya",
    "Faraz", "Ayesha", "Kashif", "Nimra", "Rehan", "Sadia", "Talha", "Uzma",
    "Waleed", "Iqra", "Yousaf", "Mehwish", "Zeeshan", "Rabia", "Haris", "Anum",
    "Salman",
]
LAST_NAMES = [
    "Raza", "Khan", "Ahmed", "Iqbal", "Ali", "Nawaz", "Malik", "Sheikh",
    "Butt", "Chaudhry",
]
DEPARTMENT_CODES = ["PROD", "FIN", "HR", "IT", "STORE", "QA"]
DESIGNATION_CODES = ["MANAGER", "OFFICER", "SUPERVISOR", "OPERATOR", "ACCOUNTANT"]
# Rotated so the payroll register shows a realistic spread rather than one figure.
SALARY_STEPS = [Decimal("95000"), Decimal("145000"), Decimal("160000"), Decimal("185000"), Decimal("260000")]


def seed_demo_employees(count: int = 50) -> int:
    """Create ``count`` employees, each with allowance/deduction rows and a payroll."""
    created_count = 0
    today = timezone.localdate()

    organization = Organization.objects.order_by("pk").first()
    branches = list(Branch.objects.order_by("pk"))
    departments = {item.code: item for item in Department.objects.filter(code__in=DEPARTMENT_CODES)}
    designations = {item.code: item for item in Designation.objects.filter(code__in=DESIGNATION_CODES)}
    job_type = JobType.objects.filter(code="PERMANENT").first()
    bank = Bank.objects.filter(code="HBL").first() or Bank.objects.order_by("pk").first()
    house_rent = AllowanceDeduction.objects.filter(code="HOUSE_RENT").first()
    tax = AllowanceDeduction.objects.filter(code="TAX").first()
    joined = today.replace(year=max(today.year - 2, 2020))

    for index in range(1, count + 1):
        first = FIRST_NAMES[(index - 1) % len(FIRST_NAMES)]
        last = LAST_NAMES[(index - 1) % len(LAST_NAMES)]
        salary = SALARY_STEPS[(index - 1) % len(SALARY_STEPS)]
        employee, created = Employee.objects.update_or_create(
            cnic=f"35202-{2000000 + index}-{index % 10}",
            defaults={
                "organization": organization,
                "branch": branches[index % len(branches)] if branches else None,
                "department": departments.get(DEPARTMENT_CODES[(index - 1) % len(DEPARTMENT_CODES)]),
                "designation": designations.get(DESIGNATION_CODES[(index - 1) % len(DESIGNATION_CODES)]),
                "job_type": job_type,
                "first_name": first,
                "last_name": last,
                "full_name": f"{first} {last}",
                "email": f"{first.lower()}.{last.lower()}{index}@industrial-erp.test",
                "contact": f"+92-301-{5000000 + index}",
                "father_husband_name": "Muhammad Aslam",
                "dob": today.replace(year=today.year - 30),
                "doj": joined,
                "joining_date": joined,
                "bank": bank,
                "account_number": f"PK36HABB{10000000 + index}",
                "salary": salary,
                "status": STATUS_ACTIVE,
            },
        )
        created_count += int(created)

        allowance_amount = (salary * Decimal("0.15")).quantize(Decimal("0.01"))
        deduction_amount = (salary * Decimal("0.04")).quantize(Decimal("0.01"))

        if house_rent:
            _, made = EmployeeSalary.objects.update_or_create(
                employee=employee,
                allowance_deduction=house_rent,
                defaults={"allowance_deduction_type": ALLOWANCE, "amount": allowance_amount},
            )
            created_count += int(made)
        if tax:
            _, made = EmployeeSalary.objects.update_or_create(
                employee=employee,
                allowance_deduction=tax,
                defaults={"allowance_deduction_type": DEDUCTION, "amount": deduction_amount},
            )
            created_count += int(made)

        _, made = Payroll.objects.update_or_create(
            employee=employee,
            month=today.month,
            year=today.year,
            defaults={
                "base_salary": salary,
                "total_allowances": allowance_amount,
                "total_deductions": deduction_amount,
                "net_salary": salary + allowance_amount - deduction_amount,
                # A third sit unapproved so the approval screen has something to do.
                "status": STATUS_PENDING if index % 3 == 0 else STATUS_APPROVED,
                "generated_at": timezone.now(),
            },
        )
        created_count += int(made)

    return created_count
