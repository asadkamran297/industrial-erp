from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.configurations.models import (
    AllowanceDeduction,
    Bank,
    City,
    Department,
    Designation,
    JobType,
    PaymentMethod,
)
from apps.core.constants import (
    ACCOUNT_LEDGER_GENERAL,
    ACCOUNT_LEDGER_SUBSIDIARY,
    ACCOUNT_NATURE_CREDIT,
    ACCOUNT_NATURE_DEBIT,
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_LIABILITY,
    ACCOUNT_TYPE_REVENUE,
    ALLOWANCE,
    BALANCE_INCOME_BALANCE_SHEET,
    BALANCE_INCOME_INCOME_STATEMENT,
    DEDUCTION,
    STATUS_ACTIVE,
    STATUS_APPROVED,
    STATUS_CREATED,
    STATUS_PENDING,
    VOUCHER_TYPE_PAYMENT,
    VOUCHER_TYPE_RECEIPT,
)
from apps.finance.models import AccountConfiguration, AccountVoucher, FiscalYear
from apps.hr.models import Employee
from apps.organizations.models import Branch, Organization
from apps.payroll.models import EmployeeSalary, Payroll


class Command(BaseCommand):
    help = "Seed polished demo data for dashboard and module previews."

    def handle(self, *args, **options):
        today = timezone.localdate()

        org, _ = Organization.objects.update_or_create(
            code="IND-ERP",
            defaults={"title": "Industrial ERP Manufacturing Group", "status": STATUS_ACTIVE},
        )
        lahore = City.objects.filter(code="LHE").first() or City.objects.create(title="Lahore", code="LHE")
        karachi = City.objects.filter(code="KHI").first() or City.objects.create(title="Karachi", code="KHI")
        branch_data = [
            ("PLANT-01", "Lahore Production Plant", lahore),
            ("HO-KHI", "Karachi Head Office", karachi),
        ]
        branches = []
        for code, title, city in branch_data:
            branch, _ = Branch.objects.update_or_create(
                code=code,
                defaults={
                    "organization": org,
                    "city": city,
                    "title": title,
                    "address": f"{title}, Industrial Estate",
                    "phone": "+92-42-111-222-333",
                    "email": f"{code.lower()}@industrial-erp.test",
                    "status": STATUS_ACTIVE,
                },
            )
            branches.append(branch)

        departments = {
            item.code: item
            for item in Department.objects.filter(code__in=["PROD", "FIN", "HR", "IT", "STORE", "QA"])
        }
        designations = {
            item.code: item
            for item in Designation.objects.filter(code__in=["MANAGER", "OFFICER", "SUPERVISOR", "OPERATOR", "ACCOUNTANT"])
        }
        job_type = JobType.objects.filter(code="PERMANENT").first()
        bank = Bank.objects.filter(code="HBL").first() or Bank.objects.create(title="Habib Bank Limited", code="HBL")

        employees = [
            ("35202-1000001-1", "Ahsan", "Raza", "PROD", "MANAGER", Decimal("260000")),
            ("35202-1000002-2", "Maham", "Khan", "FIN", "ACCOUNTANT", Decimal("185000")),
            ("35202-1000003-3", "Bilal", "Ahmed", "STORE", "SUPERVISOR", Decimal("145000")),
            ("35202-1000004-4", "Sana", "Iqbal", "HR", "OFFICER", Decimal("160000")),
            ("35202-1000005-5", "Usman", "Ali", "IT", "OFFICER", Decimal("175000")),
            ("35202-1000006-6", "Hira", "Nawaz", "QA", "SUPERVISOR", Decimal("150000")),
            ("35202-1000007-7", "Danish", "Malik", "PROD", "OPERATOR", Decimal("95000")),
            ("35202-1000008-8", "Zoya", "Sheikh", "FIN", "OFFICER", Decimal("155000")),
        ]
        employee_objs = []
        for idx, (cnic, first, last, dept_code, desig_code, salary) in enumerate(employees, start=1):
            employee, _ = Employee.objects.update_or_create(
                cnic=cnic,
                defaults={
                    "organization": org,
                    "branch": branches[idx % len(branches)],
                    "department": departments.get(dept_code),
                    "designation": designations.get(desig_code),
                    "job_type": job_type,
                    "first_name": first,
                    "last_name": last,
                    "full_name": f"{first} {last}",
                    "email": f"{first.lower()}.{last.lower()}@industrial-erp.test",
                    "contact": f"+92-300-55500{idx:02d}",
                    "father_husband_name": "Muhammad",
                    "doj": today.replace(year=max(today.year - 2, 2020)),
                    "joining_date": today.replace(year=max(today.year - 2, 2020)),
                    "bank": bank,
                    "account_number": f"PK-ERP-2026-{idx:04d}",
                    "salary": salary,
                    "status": STATUS_ACTIVE,
                },
            )
            employee_objs.append(employee)

        house_rent = AllowanceDeduction.objects.filter(code="HOUSE_RENT").first()
        tax = AllowanceDeduction.objects.filter(code="TAX").first()
        for employee in employee_objs:
            if house_rent:
                EmployeeSalary.objects.update_or_create(
                    employee=employee,
                    allowance_deduction=house_rent,
                    defaults={"allowance_deduction_type": ALLOWANCE, "amount": employee.salary * Decimal("0.15")},
                )
            if tax:
                EmployeeSalary.objects.update_or_create(
                    employee=employee,
                    allowance_deduction=tax,
                    defaults={"allowance_deduction_type": DEDUCTION, "amount": employee.salary * Decimal("0.04")},
                )
            allowances = employee.salary * Decimal("0.15")
            deductions = employee.salary * Decimal("0.04")
            Payroll.objects.update_or_create(
                employee=employee,
                month=today.month,
                year=today.year,
                defaults={
                    "base_salary": employee.salary,
                    "total_allowances": allowances,
                    "total_deductions": deductions,
                    "net_salary": employee.salary + allowances - deductions,
                    "status": STATUS_APPROVED if employee.pk % 3 else STATUS_PENDING,
                    "generated_at": timezone.now(),
                },
            )

        fiscal_year, _ = FiscalYear.objects.update_or_create(
            code=f"FY-{today.year}",
            defaults={
                "title": f"Fiscal Year {today.year}",
                "start_date": today.replace(month=1, day=1),
                "end_date": today.replace(month=12, day=31),
                "status": STATUS_ACTIVE,
            },
        )
        fiscal_year.generate_periods()

        accounts = [
            ("1000", "CASH", "Cash in Hand", ACCOUNT_TYPE_ASSET, ACCOUNT_LEDGER_GENERAL, ACCOUNT_NATURE_DEBIT, BALANCE_INCOME_BALANCE_SHEET, None),
            ("1100", "BANK", "Bank Accounts", ACCOUNT_TYPE_ASSET, ACCOUNT_LEDGER_GENERAL, ACCOUNT_NATURE_DEBIT, BALANCE_INCOME_BALANCE_SHEET, None),
            ("4000", "SALES", "Sales Revenue", ACCOUNT_TYPE_REVENUE, ACCOUNT_LEDGER_GENERAL, ACCOUNT_NATURE_CREDIT, BALANCE_INCOME_INCOME_STATEMENT, None),
            ("5000", "EXP", "Operating Expenses", ACCOUNT_TYPE_EXPENSE, ACCOUNT_LEDGER_GENERAL, ACCOUNT_NATURE_DEBIT, BALANCE_INCOME_INCOME_STATEMENT, None),
            ("5100", "UTIL", "Utilities Expense", ACCOUNT_TYPE_EXPENSE, ACCOUNT_LEDGER_SUBSIDIARY, ACCOUNT_NATURE_DEBIT, BALANCE_INCOME_INCOME_STATEMENT, "5000"),
            ("4100", "LOCAL-SALES", "Local Sales", ACCOUNT_TYPE_REVENUE, ACCOUNT_LEDGER_SUBSIDIARY, ACCOUNT_NATURE_CREDIT, BALANCE_INCOME_INCOME_STATEMENT, "4000"),
        ]
        account_map = {}
        for account_no, code, title, account_type, ledger, nature, statement, post_to_no in accounts:
            account_map[account_no], _ = AccountConfiguration.objects.update_or_create(
                account_no=account_no,
                defaults={
                    "title": title,
                    "code": code,
                    "nature": account_type,
                    "account_type": account_type,
                    "account_ledger": ledger,
                    "balance_income": statement,
                    "account_nature": nature,
                    "post_to_account": account_map.get(post_to_no),
                    "status": STATUS_ACTIVE,
                },
            )

        cash = account_map["1000"]
        sales = account_map["4100"]
        expense = account_map["5100"]
        payment_method = PaymentMethod.objects.filter(code="BANK_TRANSFER").first()
        voucher_rows = [
            (VOUCHER_TYPE_RECEIPT, sales.account_no, Decimal("0"), Decimal("485000"), "Receipt from local customer"),
            (VOUCHER_TYPE_PAYMENT, expense.account_no, Decimal("72000"), Decimal("0"), "Utilities and plant maintenance"),
            (VOUCHER_TYPE_RECEIPT, cash.account_no, Decimal("0"), Decimal("135000"), "Cash sales counter collection"),
            (VOUCHER_TYPE_PAYMENT, expense.account_no, Decimal("44500"), Decimal("0"), "Monthly admin expenses"),
        ]
        for idx, (voucher_type, account_no, debit, credit, remarks) in enumerate(voucher_rows, start=1):
            voucher, created = AccountVoucher.objects.update_or_create(
                voucher_no=f"{'E' if voucher_type == VOUCHER_TYPE_PAYMENT else 'R'}-DEMO-{idx:03d}",
                defaults={
                    "voucher_type": voucher_type,
                    "account_no": account_no,
                    "voucher_date": today,
                    "payment_method": payment_method,
                    "debit_amount": debit,
                    "credit_amount": credit,
                    "remarks": remarks,
                    "status": STATUS_CREATED,
                    "posted": "N",
                },
            )
            if created:
                voucher.lines.create(
                    line_number=1,
                    voucher_no=voucher.voucher_no,
                    account_no=account_no,
                    voucher_date=today,
                    payment_method=payment_method,
                    debit_amount=debit,
                    credit_amount=credit,
                    remarks=remarks,
                    person_organization="Customer/Vendor",
                    person_organization_title="Demo Trading Partner",
                )

        self.stdout.write(self.style.SUCCESS("Demo ERP data seeded."))
