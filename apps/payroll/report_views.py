"""HR / payroll reporting screens (catalogue group I)."""

from apps.core.constants import ALLOWANCE_DEDUCTION_TYPE_CHOICES, RECORD_STATUS_CHOICES, STATUS_ACTIVE, STATUS_INACTIVE, WORKFLOW_STATUS_CHOICES
from apps.core.formatting import format_amount
from apps.core.reporting import PRESET_FISCAL, PRESET_MONTH, ReportExportView, ReportView, delta
from apps.core.table_columns import ColumnSet, col
from apps.inventory.report_views import _tile
from apps.inventory.report_views_purchase import _views

from . import report_selectors as sel

PAGE = "reports.hr"
DEPARTMENT = ("department", "Department", sel.department_options)
DESIGNATION = ("designation", "Designation", sel.designation_options)
TONES = ("amber", "teal", "sky", "violet")


# 64 ------------------------------------------------------------------------

EMPLOYEE_COLUMNS = ColumnSet("reports.employees", (
    col("name", "Employee", "link", locked=True, link="hr:employee_detail", link_key="pk"),
    col("father", "Father / Husband", default=False),
    col("cnic", "CNIC", default=False),
    col("contact", "Contact", default=False),
    col("department", "Department"),
    col("designation", "Designation"),
    col("joined", "Joined", "date"),
    col("service_days", "Service Days", "int", default=False),
    col("salary", "Salary", "money", total=True, locked=True),
    col("pay_mode", "Bank / Cash"),
    col("status", "Status", "status"),
))


class EmployeeRegisterView(ReportView):
    page = PAGE
    title = "Employee Register"
    template_name = "reports/generic.html"
    columns = EMPLOYEE_COLUMNS
    url_name = "payroll:report_employees"
    as_of_report = True
    default_sort = "name"
    sort_fields = {k: k for k in EMPLOYEE_COLUMNS.keys}
    filter_specs = (("status", "Status", RECORD_STATUS_CHOICES), DEPARTMENT, DESIGNATION)

    def build(self):
        f = self.filters()
        data = sel.employee_register(self.as_of(), f["status"] or None, f["department"] or None, f["designation"] or None)
        t = data["totals"]
        base = f"as_of={self.as_of():%Y-%m-%d}&department={f['department']}&designation={f['designation']}"
        tiles = [
            _tile("Employees", str(t["employees"]), "slate", "users", f"{t['departments']} departments", href=f"?{base}", on=not f["status"]),
            _tile("Active", str(t["active"]), "green", "user", href=f"?{base}&status={STATUS_ACTIVE}", on=f["status"] == STATUS_ACTIVE),
            _tile("Inactive", str(t["inactive"]), "rose", "deactivate", href=f"?{base}&status={STATUS_INACTIVE}", on=f["status"] == STATUS_INACTIVE),
            _tile("Monthly salary", format_amount(t["salary"]), "sky", "cash", "active employees"),
        ]
        for index, (department, count) in enumerate(sorted(data["by_department"].items(), key=lambda x: -x[1])[:2]):
            tiles.append(_tile(department, str(count), TONES[index], "layers"))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


EmployeeRegisterExportView, EmployeeRegisterColumnsView = _views(EmployeeRegisterView)


# 65 ------------------------------------------------------------------------

SALARY_SHEET_COLUMNS = ColumnSet("reports.salary_sheet", (
    col("employee", "Employee", "link", locked=True, link="hr:employee_detail", link_key="employee_id"),
    col("department", "Department"),
    col("designation", "Designation", default=False),
    col("base", "Base", "money", total=True),
    col("allowances", "Allowances", "money", total=True),
    col("deductions", "Deductions", "money", total=True),
    col("net", "Net", "money", total=True, locked=True),
    col("pay_mode", "Bank / Cash"),
    col("status", "Status", "status"),
    col("signature", "Signature", locked=True),
))


class SalarySheetView(ReportView):
    page = PAGE
    title = "Salary Sheet"
    template_name = "reports/generic.html"
    columns = SALARY_SHEET_COLUMNS
    url_name = "payroll:report_salary_sheet"
    default_preset = PRESET_MONTH
    default_sort = "employee"
    sort_fields = {k: k for k in SALARY_SHEET_COLUMNS.keys}
    filter_specs = (DEPARTMENT, ("status", "Status", WORKFLOW_STATUS_CHOICES))

    def month(self):
        # The sheet covers the calendar month the period ends in.
        end = self.period().end
        return end.year, end.month

    def period_label(self):
        year, month = self.month()
        return f"{sel._month_label(year, month)}"

    def build(self):
        f = self.filters()
        year, month = self.month()
        data = sel.salary_sheet(year, month, f["department"] or None, f["status"] or None)
        t = data["totals"]
        tiles = [
            _tile("Employees", str(t["employees"]), "slate", "users", f"{t['approved']} approved"),
            _tile("Base", format_amount(t["base"]), "teal", "cash"),
            _tile("Allowances", format_amount(t["allowances"]), "green", "plus"),
            _tile("Deductions", format_amount(t["deductions"]), "rose", "minus"),
            _tile("Net payable", format_amount(t["net"]), "sky", "sum", f"bank {format_amount(t['bank'])} · cash {format_amount(t['cash'])}"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


class SalarySheetExportView(ReportExportView):
    page = PAGE
    report_view = SalarySheetView
    print_template = "reports/salary_sheet_print.html"


SalarySheetColumnsView = _views(SalarySheetView)[1]


# 66 ------------------------------------------------------------------------

PAYROLL_SUMMARY_COLUMNS = ColumnSet("reports.payroll_summary", (
    col("month", "Month", locked=True),
    col("headcount", "Headcount", "int"),
    col("base", "Base", "money", total=True),
    col("allowances", "Allowances", "money", total=True),
    col("cost", "Total Cost", "money", total=True, locked=True),
    col("deductions", "Deductions", "money", total=True),
    col("net", "Net Paid", "money", total=True),
    col("avg_salary", "Avg Salary", "money"),
    col("change", "vs Last Month", "money"),
    col("change_pct", "Change %", "pct"),
))


class PayrollSummaryView(ReportView):
    page = PAGE
    title = "Payroll Summary"
    template_name = "reports/generic.html"
    columns = PAYROLL_SUMMARY_COLUMNS
    url_name = "payroll:report_payroll_summary"
    default_preset = PRESET_FISCAL
    default_sort = "ym"
    sort_fields = {**{k: k for k in PAYROLL_SUMMARY_COLUMNS.keys}, "month": "ym"}
    filter_specs = (DEPARTMENT,)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.payroll_summary(p.start, p.end, f["department"] or None)
        t = data["totals"]
        latest = t["latest"]
        tiles = [
            _tile("Total cost", format_amount(t["cost"]), "sky", "cash", f"{t['months']} months"),
            _tile("Net paid", format_amount(t["net"]), "teal", "sum"),
            _tile("Headcount", str(t["headcount"]), "slate", "users", latest["month"] if latest else ""),
            _tile("Avg salary", format_amount(t["avg_salary"]), "violet", "user"),
        ]
        if latest and latest["change"] is not None:
            tiles.append(_tile("vs last month", format_amount(latest["net"]), "amber", "chart", change=delta(latest["net"], latest["net"] - latest["change"])))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


PayrollSummaryExportView, PayrollSummaryColumnsView = _views(PayrollSummaryView)


# 67 ------------------------------------------------------------------------

BREAKDOWN_COLUMNS = ColumnSet("reports.allowance_deduction", (
    col("month", "Month", locked=True),
    col("item", "Item", locked=True),
    col("kind_label", "Type"),
    col("employees", "Employees", "int"),
    col("allowance", "Allowance", "money", total=True),
    col("deduction", "Deduction", "money", total=True),
    col("amount", "Amount", "money", total=True, locked=True),
))


class AllowanceDeductionView(ReportView):
    page = PAGE
    title = "Allowance / Deduction Breakdown"
    template_name = "reports/generic.html"
    columns = BREAKDOWN_COLUMNS
    url_name = "payroll:report_allowance_deduction"
    default_preset = PRESET_FISCAL
    default_sort = "ym"
    sort_fields = {**{k: k for k in BREAKDOWN_COLUMNS.keys}, "month": "ym"}
    filter_specs = (("kind", "Type", ALLOWANCE_DEDUCTION_TYPE_CHOICES), ("item", "Item", sel.item_options), DEPARTMENT)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.allowance_deduction_breakdown(p.start, p.end, f["kind"] or None, f["item"] or None, f["department"] or None)
        t = data["totals"]
        base = f"{p.query}&item={f['item']}&department={f['department']}"
        tiles = [
            _tile("Allowances", format_amount(t["allowance"]), "green", "plus", href=f"?{base}&kind=allowance", on=f["kind"] == "allowance"),
            _tile("Deductions", format_amount(t["deduction"]), "rose", "minus", href=f"?{base}&kind=deduction", on=f["kind"] == "deduction"),
            _tile("Items", str(t["items"]), "slate", "layers", f"{t['months']} months"),
        ]
        for index, ((kind, item), amount) in enumerate(t["top"][:3]):
            tiles.append(_tile(item, format_amount(amount), TONES[index], "receipt", dict(ALLOWANCE_DEDUCTION_TYPE_CHOICES).get(kind, "")))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


AllowanceDeductionExportView, AllowanceDeductionColumnsView = _views(AllowanceDeductionView)
