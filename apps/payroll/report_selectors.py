"""HR / payroll reporting reads (catalogue group I)."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.configurations.models import AllowanceDeduction, Department, Designation
from apps.core.constants import ALLOWANCE, DEDUCTION, STATUS_ACTIVE, STATUS_INACTIVE
from apps.core.reporting import ZERO, delta, money
from apps.hr.models import Employee

from .models import EmployeeSalary, Payroll

MONEY = DecimalField(max_digits=18, decimal_places=2)


def _sum(field):
    return Coalesce(Sum(field), Value(Decimal("0")), output_field=MONEY)


def _ym(day: date) -> int:
    return day.year * 100 + day.month


def _month_label(year: int, month: int) -> str:
    return f"{date(year, month, 1):%b %Y}"


def department_options():
    return Department.objects.filter(status=STATUS_ACTIVE).order_by("title").values_list("pk", "title")


def designation_options():
    return Designation.objects.filter(status=STATUS_ACTIVE).order_by("title").values_list("pk", "title")


def item_options():
    return AllowanceDeduction.objects.filter(status=STATUS_ACTIVE).order_by("type", "title").values_list("pk", "title")


def _pay_mode(employee):
    if employee.bank_id:
        return f"{employee.bank.title} {employee.account_number}".strip()
    return "Cash"


# ---------------------------------------------------------------------------
# 64. Employee Register
# ---------------------------------------------------------------------------

def employee_register(as_of, status=None, department=None, designation=None):
    qs = Employee.objects.select_related("department", "designation", "bank").filter(
        Q(doj__lte=as_of) | Q(doj__isnull=True, joining_date__lte=as_of) | Q(doj__isnull=True, joining_date__isnull=True)
    )
    if status:
        qs = qs.filter(status=status)
    if department:
        qs = qs.filter(department_id=department)
    if designation:
        qs = qs.filter(designation_id=designation)
    rows = []
    for e in qs.order_by("full_name"):
        joined = e.doj or e.joining_date
        rows.append({
            "pk": e.pk, "name": e.full_name, "father": e.father_husband_name, "cnic": e.cnic, "contact": e.contact,
            "department": e.department.title if e.department_id else "", "designation": e.designation.title if e.designation_id else "",
            "joined": joined, "service_days": (as_of - joined).days if joined else None, "salary": money(e.salary), "pay_mode": _pay_mode(e),
            "status": e.status, "status_label": e.get_status_display(),
        })
    active = [r for r in rows if r["status"] == STATUS_ACTIVE]
    totals = {
        "salary": sum((r["salary"] for r in active), ZERO), "employees": len(rows), "active": len(active),
        "inactive": sum(1 for r in rows if r["status"] == STATUS_INACTIVE), "departments": len({r["department"] for r in rows if r["department"]}),
    }
    by_department = defaultdict(int)
    for r in active:
        by_department[r["department"] or "—"] += 1
    return {"rows": rows, "totals": totals, "by_department": dict(by_department)}


# ---------------------------------------------------------------------------
# 65. Salary Sheet
# ---------------------------------------------------------------------------

def salary_sheet(year, month, department=None, status=None):
    qs = Payroll.objects.filter(year=year, month=month).select_related("employee__department", "employee__designation", "employee__bank")
    if department:
        qs = qs.filter(employee__department_id=department)
    if status:
        qs = qs.filter(status=status)
    rows = []
    for p in qs.order_by("employee__full_name"):
        e = p.employee
        rows.append({
            "pk": p.pk, "employee_id": e.pk, "employee": e.full_name, "department": e.department.title if e.department_id else "",
            "designation": e.designation.title if e.designation_id else "", "base": money(p.base_salary), "allowances": money(p.total_allowances),
            "deductions": money(p.total_deductions), "net": money(p.net_salary), "pay_mode": _pay_mode(e), "bank": e.bank.title if e.bank_id else "",
            "account": e.account_number, "status": p.status, "status_label": p.get_status_display(), "signature": "",
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("base", "allowances", "deductions", "net")}
    totals["employees"] = len(rows)
    totals["bank"] = sum((r["net"] for r in rows if r["bank"]), ZERO)
    totals["cash"] = sum((r["net"] for r in rows if not r["bank"]), ZERO)
    totals["approved"] = sum(1 for r in rows if r["status"] == "approved")
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 66. Payroll Summary
# ---------------------------------------------------------------------------

def _month_figures(start, end, department=None):
    qs = Payroll.objects.annotate(ym=F("year") * 100 + F("month")).filter(ym__gte=_ym(start), ym__lte=_ym(end))
    if department:
        qs = qs.filter(employee__department_id=department)
    return {
        (r["year"], r["month"]): r for r in qs.values("year", "month").annotate(
            headcount=Count("pk"), base=_sum("base_salary"), allowances=_sum("total_allowances"), deductions=_sum("total_deductions"), net=_sum("net_salary"),
        )
    }


def payroll_summary(start, end, department=None):
    """One row per month in the period; ``vs last month`` reads the month before, even outside the period."""
    prior_start = date(start.year - 1, 12, 1) if start.month == 1 else date(start.year, start.month - 1, 1)
    figures = _month_figures(prior_start, end, department)
    rows = []
    previous = None
    for key in sorted(figures):
        f = figures[key]
        if key < (start.year, start.month):
            previous = f
            continue
        cost = money(f["base"] + f["allowances"])
        net = money(f["net"])
        change = delta(net, previous["net"]) if previous else None
        rows.append({
            "ym": key[0] * 100 + key[1], "month": _month_label(*key), "headcount": f["headcount"], "base": money(f["base"]), "allowances": money(f["allowances"]),
            "deductions": money(f["deductions"]), "cost": cost, "net": net, "avg_salary": money(net / f["headcount"]) if f["headcount"] else ZERO,
            "change": money(change["value"]) if change else None, "change_pct": change["percent"] if change else None,
        })
        previous = f
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("base", "allowances", "deductions", "cost", "net")}
    totals["months"] = len(rows)
    totals["headcount"] = rows[-1]["headcount"] if rows else 0
    totals["avg_salary"] = money(totals["net"] / sum(r["headcount"] for r in rows)) if rows and sum(r["headcount"] for r in rows) else ZERO
    totals["latest"] = rows[-1] if rows else None
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 67. Allowance / Deduction Breakdown
# ---------------------------------------------------------------------------

def allowance_deduction_breakdown(start, end, kind=None, item=None, department=None):
    """Item totals per payroll month: the employee's current salary items applied to each month that employee was paid.

    Payroll stores only totals, so item-wise figures are not snapshotted per month.
    """
    payrolls = Payroll.objects.annotate(ym=F("year") * 100 + F("month")).filter(ym__gte=_ym(start), ym__lte=_ym(end))
    if department:
        payrolls = payrolls.filter(employee__department_id=department)
    paid = defaultdict(set)
    for year, month, employee_id in payrolls.values_list("year", "month", "employee_id"):
        paid[(year, month)].add(employee_id)
    employees = set().union(*paid.values()) if paid else set()
    items = EmployeeSalary.objects.filter(employee_id__in=employees).select_related("allowance_deduction")
    if kind:
        items = items.filter(allowance_deduction_type=kind)
    if item:
        items = items.filter(allowance_deduction_id=item)
    per_employee = defaultdict(list)
    for s in items:
        per_employee[s.employee_id].append(s)
    grouped = {}
    for (year, month), ids in sorted(paid.items()):
        for employee_id in ids:
            for s in per_employee.get(employee_id, ()):
                key = (year, month, s.allowance_deduction_id)
                g = grouped.setdefault(key, {
                    "ym": year * 100 + month, "month": _month_label(year, month), "item": s.allowance_deduction.title, "kind": s.allowance_deduction_type,
                    "kind_label": s.get_allowance_deduction_type_display(), "employees": 0, "amount": ZERO,
                })
                g["employees"] += 1
                g["amount"] += s.amount
    rows = []
    for g in grouped.values():
        g["amount"] = money(g["amount"])
        g["allowance"] = g["amount"] if g["kind"] == ALLOWANCE else ZERO
        g["deduction"] = g["amount"] if g["kind"] == DEDUCTION else ZERO
        rows.append(g)
    rows.sort(key=lambda r: (r["ym"], r["kind"], r["item"]))
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("amount", "allowance", "deduction")}
    totals["items"] = len({r["item"] for r in rows})
    totals["months"] = len(paid)
    by_item = defaultdict(Decimal)
    for r in rows:
        by_item[(r["kind"], r["item"])] += r["amount"]
    totals["top"] = sorted(by_item.items(), key=lambda x: -x[1])[:4]
    return {"rows": rows, "totals": totals}
