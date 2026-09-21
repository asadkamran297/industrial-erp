from datetime import date
from decimal import Decimal

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.constants import STATUS_POSTED
from apps.core.mixins import PagePermissionRequiredMixin
from apps.finance.models import AccountVoucher
from apps.finance.services import (
    account_balances,
    cash_bank_account_codes,
    income_statement,
    ledger_integrity,
)
from apps.hr.models import Employee
from apps.inventory.models import POSDetail, POSMaster, PurchaseInvoice
from apps.payroll.models import Payroll

from .services import toggle_favourite

ZERO = Decimal("0.00")
TREND_MONTHS = 12


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _recent_months(count: int) -> list[date]:
    """First-of-month dates for the last ``count`` months, oldest first."""
    today = timezone.localdate().replace(day=1)
    months, year, month = [], today.year, today.month
    for _ in range(count):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def _with_share(rows) -> list[dict]:
    """Add each row's share of the largest ``amount``, as a percentage."""
    rows = list(rows)
    largest = max((row["amount"] or ZERO for row in rows), default=ZERO)
    for row in rows:
        row["share"] = float((row["amount"] or ZERO) / largest * 100) if largest else 0.0
    return rows


class DashboardView(PagePermissionRequiredMixin, TemplateView):
    """Headline trading position: what was earned, spent, kept and held.

    Every figure is read from the ledger rather than counted off the
    operational tables, so the dashboard cannot disagree with the financial
    statements.
    """

    page = "dashboard"
    template_name = "portal/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        statement = income_statement()
        balances = account_balances()
        cash_on_hand = sum(
            (balances.get(code, {}).get("closing", ZERO) for code in cash_bank_account_codes()),
            ZERO,
        )
        revenue = statement["total_revenue"]
        margin = (statement["net_profit"] / revenue * 100) if revenue else None

        context["kpis"] = [
            {"key": "revenue", "label": "Total Revenue", "value": revenue, "tone": "green", "icon": "sum",
             "note": "Net of discounts and returns"},
            {"key": "expense", "label": "Total Expense", "value": statement["total_expense"], "tone": "amber", "icon": "cash",
             "note": "Cost of sales and running costs"},
            {"key": "profit", "label": "Net Profit", "value": statement["net_profit"],
             "tone": "rose" if statement["net_profit"] < 0 else "violet", "icon": "chart",
             "note": f"{margin:.1f}% margin" if margin is not None else "No revenue yet",
             "signed": True},
            {"key": "cash", "label": "Cash & Bank", "value": cash_on_hand, "tone": "sky", "icon": "cash",
             "note": "Available balance"},
        ]

        months = _recent_months(TREND_MONTHS)
        sales_by_month = {_month_key(m): ZERO for m in months}
        purchases_by_month = dict(sales_by_month)

        for row in (
            POSMaster.objects.filter(status=STATUS_POSTED, sale_date__gte=months[0])
            .values("sale_date")
            .annotate(total=Sum("net_amount"))
        ):
            key = _month_key(row["sale_date"])
            if key in sales_by_month:
                sales_by_month[key] += row["total"] or ZERO

        for row in (
            PurchaseInvoice.objects
            .filter(invoice_date__gte=months[0], status=STATUS_POSTED)
            .values("invoice_date", "total_amount")
        ):
            key = _month_key(row["invoice_date"])
            if key in purchases_by_month:
                purchases_by_month[key] += row["total_amount"] or ZERO

        first = next(
            (i for i, m in enumerate(months)
             if sales_by_month[_month_key(m)] or purchases_by_month[_month_key(m)]),
            0,
        )
        months = months[min(first, max(0, len(months) - 6)):]

        context["trend"] = {
            "labels": [m.strftime("%b %Y") for m in months],
            "sales": [float(sales_by_month[_month_key(m)]) for m in months],
            "purchases": [float(purchases_by_month[_month_key(m)]) for m in months],
        }
        context["trend_rows"] = [
            {
                "label": m.strftime("%b %Y"),
                "sales": sales_by_month[_month_key(m)],
                "purchases": purchases_by_month[_month_key(m)],
            }
            for m in months
        ]

        context["top_products"] = _with_share(
            POSDetail.objects.filter(pos_master__status=STATUS_POSTED)
            .values("item_name")
            .annotate(qty=Sum("quantity"), amount=Sum("net_total"))
            .order_by("-amount")[:6]
        )
        context["top_customers"] = _with_share(
            POSMaster.objects.filter(status=STATUS_POSTED, customer__isnull=False)
            .values("customer__customer_name")
            .annotate(amount=Sum("net_amount"), orders=Count("id"))
            .order_by("-amount")[:6]
        )

        context["recent_sales"] = (
            POSMaster.objects.filter(status=STATUS_POSTED)
            .select_related("customer")
            .order_by("-sale_date", "-id")[:5]
        )
        context["recent_vouchers"] = AccountVoucher.objects.order_by("-voucher_date", "-id")[:5]

        context["secondary"] = [
            {"label": "Active Employees", "value": Employee.objects.filter(status="active").count(), "icon": "users"},
            {"label": "Payroll Net", "value": Payroll.objects.aggregate(net=Sum("net_salary"))["net"] or ZERO,
             "money": True, "icon": "cash"},
            {"label": "Posted Vouchers", "value": AccountVoucher.objects.filter(posted="Y").count(), "icon": "file"},
            {"label": "Sales Recorded", "value": POSMaster.objects.filter(status=STATUS_POSTED).count(), "icon": "layers"},
        ]

        context["integrity"] = ledger_integrity()
        context["breadcrumbs"] = [("Dashboard", "")]
        return context


class FavouriteToggleView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            href = (json.loads(request.body or b"{}").get("href") or "").strip()
        except ValueError:
            href = ""
        if not href.startswith("/") or len(href) > 255:
            return JsonResponse({"errors": ["Invalid menu link."]}, status=400)
        return JsonResponse({"on": toggle_favourite(request.user, href)})
