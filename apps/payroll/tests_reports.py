from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.configurations.models import AllowanceDeduction, Bank, Department, Designation
from apps.core.constants import ALLOWANCE, DEDUCTION, STATUS_APPROVED, STATUS_INACTIVE, STATUS_PENDING
from apps.hr.models import Employee

from . import report_selectors as sel
from .models import EmployeeSalary, Payroll


class PayrollReportFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("owner", "owner@example.com", "pass12345")
        cls.mill = Department.objects.create(title="Mill")
        cls.office = Department.objects.create(title="Office")
        operator = Designation.objects.create(title="Operator")
        clerk = Designation.objects.create(title="Clerk")
        bank = Bank.objects.create(title="HBL")
        cls.ali = Employee.objects.create(first_name="Ali", full_name="Ali Khan", cnic="1", department=cls.mill, designation=operator, doj=date(2024, 3, 1), salary=Decimal("30000"), bank=bank, account_number="123")
        cls.bilal = Employee.objects.create(first_name="Bilal", full_name="Bilal Shah", cnic="2", department=cls.office, designation=clerk, joining_date=date(2025, 1, 15), salary=Decimal("25000"))
        cls.gone = Employee.objects.create(first_name="Gone", full_name="Gone Away", cnic="3", department=cls.mill, doj=date(2023, 1, 1), salary=Decimal("10000"), status=STATUS_INACTIVE)
        house = AllowanceDeduction.objects.create(title="House Rent", type=ALLOWANCE)
        eobi = AllowanceDeduction.objects.create(title="EOBI", type=DEDUCTION)
        EmployeeSalary.objects.create(employee=cls.ali, allowance_deduction=house, allowance_deduction_type=ALLOWANCE, amount=Decimal("5000"))
        EmployeeSalary.objects.create(employee=cls.ali, allowance_deduction=eobi, allowance_deduction_type=DEDUCTION, amount=Decimal("500"))
        EmployeeSalary.objects.create(employee=cls.bilal, allowance_deduction=house, allowance_deduction_type=ALLOWANCE, amount=Decimal("3000"))
        Payroll.objects.create(employee=cls.ali, month=7, year=2026, base_salary=Decimal("30000"), total_allowances=Decimal("5000"), total_deductions=Decimal("500"), net_salary=Decimal("34500"), status=STATUS_APPROVED)
        Payroll.objects.create(employee=cls.ali, month=8, year=2026, base_salary=Decimal("30000"), total_allowances=Decimal("5000"), total_deductions=Decimal("500"), net_salary=Decimal("34500"), status=STATUS_APPROVED)
        Payroll.objects.create(employee=cls.bilal, month=8, year=2026, base_salary=Decimal("25000"), total_allowances=Decimal("3000"), total_deductions=Decimal("0"), net_salary=Decimal("28000"), status=STATUS_PENDING)


class PayrollSelectorTests(PayrollReportFixture):
    def test_employee_register(self):
        data = sel.employee_register(date(2026, 8, 31))
        self.assertEqual(data["totals"]["employees"], 3)
        self.assertEqual(data["totals"]["active"], 2)
        self.assertEqual(data["totals"]["inactive"], 1)
        self.assertEqual(data["totals"]["salary"], Decimal("55000.00"))
        ali = next(r for r in data["rows"] if r["name"] == "Ali Khan")
        self.assertEqual(ali["pay_mode"], "HBL 123")
        self.assertEqual(ali["joined"], date(2024, 3, 1))
        bilal = next(r for r in data["rows"] if r["name"] == "Bilal Shah")
        self.assertEqual(bilal["pay_mode"], "Cash")
        self.assertEqual(bilal["joined"], date(2025, 1, 15))
        self.assertEqual(sel.employee_register(date(2024, 12, 31))["totals"]["employees"], 2)
        self.assertEqual(sel.employee_register(date(2026, 8, 31), department=self.office.pk)["totals"]["employees"], 1)

    def test_salary_sheet(self):
        data = sel.salary_sheet(2026, 8)
        t = data["totals"]
        self.assertEqual(t["employees"], 2)
        self.assertEqual(t["net"], Decimal("62500.00"))
        self.assertEqual(t["bank"], Decimal("34500.00"))
        self.assertEqual(t["cash"], Decimal("28000.00"))
        self.assertEqual(t["approved"], 1)
        self.assertEqual(data["rows"][0]["signature"], "")
        self.assertEqual(sel.salary_sheet(2026, 8, department=self.mill.pk)["totals"]["net"], Decimal("34500.00"))

    def test_payroll_summary(self):
        data = sel.payroll_summary(date(2026, 7, 1), date(2026, 8, 31))
        rows = data["rows"]
        self.assertEqual([r["month"] for r in rows], ["Jul 2026", "Aug 2026"])
        self.assertEqual(rows[1]["headcount"], 2)
        self.assertEqual(rows[1]["cost"], Decimal("63000.00"))
        self.assertEqual(rows[1]["avg_salary"], Decimal("31250.00"))
        self.assertEqual(rows[1]["change"], Decimal("28000.00"))
        self.assertIsNone(rows[0]["change"])
        self.assertEqual(data["totals"]["net"], Decimal("97000.00"))
        august_only = sel.payroll_summary(date(2026, 8, 1), date(2026, 8, 31))["rows"]
        self.assertEqual(august_only[0]["change"], Decimal("28000.00"))

    def test_allowance_deduction_breakdown(self):
        data = sel.allowance_deduction_breakdown(date(2026, 7, 1), date(2026, 8, 31))
        by_key = {(r["month"], r["item"]): r for r in data["rows"]}
        self.assertEqual(by_key[("Jul 2026", "House Rent")]["amount"], Decimal("5000.00"))
        self.assertEqual(by_key[("Aug 2026", "House Rent")]["amount"], Decimal("8000.00"))
        self.assertEqual(by_key[("Aug 2026", "House Rent")]["employees"], 2)
        self.assertEqual(by_key[("Aug 2026", "EOBI")]["deduction"], Decimal("500.00"))
        self.assertEqual(data["totals"]["allowance"], Decimal("13000.00"))
        self.assertEqual(data["totals"]["deduction"], Decimal("1000.00"))
        self.assertEqual(sel.allowance_deduction_breakdown(date(2026, 7, 1), date(2026, 8, 31), kind=DEDUCTION)["totals"]["allowance"], Decimal("0"))


class PayrollScreenTests(PayrollReportFixture):
    REPORTS = ("report_employees", "report_salary_sheet", "report_payroll_summary", "report_allowance_deduction")

    def setUp(self):
        self.client.force_login(self.user)

    def test_every_hr_report_renders_and_exports(self):
        query = {"date_from": "2026-07-01", "date_to": "2026-08-31", "as_of": "2026-08-31"}
        for name in self.REPORTS:
            with self.subTest(report=name):
                response = self.client.get(reverse(f"payroll:{name}"), query)
                self.assertEqual(response.status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    self.assertEqual(self.client.get(reverse(f"payroll:{name}_export"), {"format": fmt, **query}).status_code, 200, f"{name} {fmt}")

    def test_salary_sheet_print_has_signature_column(self):
        response = self.client.get(reverse("payroll:report_salary_sheet_export"), {"format": "pdf", "date_from": "2026-08-01", "date_to": "2026-08-31"})
        self.assertContains(response, "Signature")
        self.assertContains(response, "Aug 2026")

    def test_query_counts(self):
        query = {"date_from": "2026-07-01", "date_to": "2026-08-31", "as_of": "2026-08-31"}
        for name in self.REPORTS:
            with self.subTest(report=name), transaction.atomic(), CaptureQueriesContext(connection) as captured:
                self.assertEqual(self.client.get(reverse(f"payroll:{name}"), query).status_code, 200)
                transaction.set_rollback(True)
                self.assertLess(len(captured), 20, f"{name}: {len(captured)} queries")
