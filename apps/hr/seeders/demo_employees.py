"""Demo mill staff, their salary components and a payroll run."""

from decimal import Decimal

from django.utils import timezone

from apps.configurations.models import AllowanceDeduction, Bank, Department, Designation, JobType
from apps.core.constants import ALLOWANCE, DEDUCTION, STATUS_ACTIVE, STATUS_APPROVED, STATUS_PENDING
from apps.hr.models import Employee
from apps.organizations.models import Branch, Organization
from apps.payroll.models import EmployeeSalary, Payroll

FIRST_NAMES = [
    "Muhammad Aslam", "Ghulam Rasool", "Allah Ditta", "Abdul Rehman", "Nasir", "Shafqat",
    "Riaz", "Zafar", "Imtiaz", "Sajid", "Tariq", "Mushtaq", "Ramzan", "Irfan", "Shahid",
    "Asif", "Waqas", "Naveed", "Amjad", "Rizwan", "Sultan", "Fayyaz", "Ilyas", "Qaiser",
    "Saima", "Nabeela", "Kausar", "Farzana", "Rukhsana", "Bushra",
]
LAST_NAMES = [
    "Gondal", "Cheema", "Bhatti", "Awan", "Malik", "Ranjha", "Tarar", "Sial",
    "Baloch", "Arain",
]

# (department, designation, salary) — the mill's floor, gate, store and office
ROLES = [
    ("PROD", "OPERATOR", Decimal("42000")),
    ("PROD", "HELPER", Decimal("32000")),
    ("PROD", "OPERATOR", Decimal("45000")),
    ("PROD", "SUPERVISOR", Decimal("65000")),
    ("PROD", "HELPER", Decimal("32000")),
    ("STORE", "STORE_KEEPER", Decimal("48000")),
    ("STORE", "HELPER", Decimal("32000")),
    ("MAINT", "TECHNICIAN", Decimal("55000")),
    ("MAINT", "HELPER", Decimal("33000")),
    ("QC", "OFFICER", Decimal("58000")),
    ("FIN", "ACCOUNTANT", Decimal("70000")),
    ("SALES", "OFFICER", Decimal("60000")),
    ("SEC", "SECURITY_GUARD", Decimal("35000")),
    ("ADMIN", "MANAGER", Decimal("145000")),
    ("PROD", "MANAGER", Decimal("160000")),
]


def seed_demo_employees(count: int = 50) -> int:
    """Create ``count`` employees, each with allowance/deduction rows and a payroll."""
    created_count = 0
    today = timezone.localdate()

    organization = Organization.objects.order_by("pk").first()
    branches = list(Branch.objects.order_by("pk"))
    departments = {item.code: item for item in Department.objects.all()}
    designations = {item.code: item for item in Designation.objects.all()}
    job_type = JobType.objects.filter(code="PERMANENT").first()
    bank = Bank.objects.filter(code="HBL").first() or Bank.objects.order_by("pk").first()
    house_rent = AllowanceDeduction.objects.filter(code="HOUSE_RENT").first()
    tax = AllowanceDeduction.objects.filter(code="TAX").first()
    joined = today.replace(year=max(today.year - 2, 2020))

    for index in range(1, count + 1):
        first = FIRST_NAMES[(index - 1) % len(FIRST_NAMES)]
        last = LAST_NAMES[(index - 1) % len(LAST_NAMES)]
        department_code, designation_code, salary = ROLES[(index - 1) % len(ROLES)]
        employee, created = Employee.objects.update_or_create(
            cnic=f"35202-{2000000 + index}-{index % 10}",
            defaults={
                "organization": organization,
                "branch": branches[index % len(branches)] if branches else None,
                "department": departments.get(department_code),
                "designation": designations.get(designation_code),
                "job_type": job_type,
                "first_name": first,
                "last_name": last,
                "full_name": f"{first} {last}",
                "email": f"{first.split()[0].lower()}.{last.lower()}{index}@zafaranflour.test",
                "contact": f"+92-301-{5000000 + index}",
                "father_husband_name": f"{FIRST_NAMES[index % len(FIRST_NAMES)]} {last}",
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
                "status": STATUS_PENDING if index % 3 == 0 else STATUS_APPROVED,
                "generated_at": timezone.now(),
            },
        )
        created_count += int(made)

    return created_count
