from datetime import date
from decimal import Decimal

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django.urls import reverse

from apps.core.constants import STATUS_POSTED
from apps.core.formatting import format_amount
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


def mill_tiles():
    """Today at the mill, from the same selector as the Daily Position report."""
    from apps.core.reporting import mund

    from .selectors import daily_position

    data = daily_position(timezone.localdate())
    wheat, ground, sold, stock = data["wheat"], data["grinding"], data["sales"], data["wheat_stock"]
    daily = reverse("portal:report_daily_position")
    return [
        {"label": "Wheat Bought Today", "value": f"{mund(wheat['kg']):,.0f} md", "tone": "amber", "icon": "wheat",
         "note": f"{wheat['slips']} slips · Rs {format_amount(wheat['amount'])}", "href": f"{reverse('inventory:purchase_invoice_list')}?kind=wheat"},
        {"label": "Wheat Ground Today", "value": f"{mund(ground['wheat_kg']):,.0f} md", "tone": "violet", "icon": "grinding",
         "note": f"{ground['output_kg']:,.0f} kg produced", "href": reverse("production:grinding_list")},
        {"label": "Bags Sold Today", "value": f"{sold['bags']:,.0f}", "tone": "sky", "icon": "bardana",
         "note": f"Rs {format_amount(sold['net'])}", "href": reverse("inventory:sale_invoice_list")},
        {"label": "Wheat Stock", "value": f"{mund(stock['stock_kg']):,.0f} md", "tone": "teal", "icon": "stock",
         "note": f"{stock['days']} days of grinding" if stock["days"] is not None else "", "href": daily},
        {"label": "Receivable", "value": format_amount(data["receivables"]), "tone": "green", "icon": "receivable",
         "href": reverse("portal:report_receivables_aging")},
        {"label": "Payable", "value": format_amount(data["payables"]), "tone": "rose", "icon": "payable",
         "href": reverse("portal:report_payables_aging")},
    ]


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

        mill = mill_tiles()
        profit = statement["net_profit"]
        context["today_tiles"] = mill[:4]
        context["money_tiles"] = mill[4:6] + [
            {"label": "Cash & Bank", "value": format_amount(cash_on_hand), "tone": "sky", "icon": "cash",
             "href": reverse("finance:report_cash_book")},
            {"label": "Net Profit", "value": format_amount(profit), "tone": "rose" if profit < 0 else "violet", "icon": "chart",
             "note": f"{margin:.1f}% of Rs {format_amount(revenue)} revenue" if margin is not None else "",
             "href": reverse("finance:income_statement")},
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

        context["activity_tiles"] = [
            {"label": "Active Employees", "value": f"{Employee.objects.filter(status='active').count():,}", "tone": "slate",
             "icon": "employee", "href": reverse("hr:employee_list")},
            {"label": "Payroll Net", "value": format_amount(Payroll.objects.aggregate(net=Sum("net_salary"))["net"] or ZERO),
             "tone": "slate", "icon": "payroll", "href": reverse("payroll:payroll_list")},
            {"label": "Posted Vouchers", "value": f"{AccountVoucher.objects.filter(posted='Y').count():,}", "tone": "slate",
             "icon": "voucher", "href": reverse("finance:account_voucher_list")},
            {"label": "Sales Recorded", "value": f"{POSMaster.objects.filter(status=STATUS_POSTED).count():,}", "tone": "slate",
             "icon": "sale", "href": reverse("inventory:sale_invoice_list")},
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
