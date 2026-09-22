"""Owner dashboard pack: the five reports the demo opens on."""

from decimal import Decimal

from django.urls import reverse

from apps.core.constants import STATUS_ACTIVE
from apps.core.formatting import format_amount
from apps.core.reporting import (
    PRESET_MONTH,
    PRESET_TODAY,
    ReportColumnsView,
    ReportExportView,
    ReportView,
    delta,
    mund,
    previous_period,
)
from apps.core.table_columns import Column, ColumnSet
from apps.inventory.models import Customer, Supplier

from . import selectors

REPORT_PAGE = "reports.owner"


def _money(key):
    return lambda row: format_amount(row.get(key))


def _kg(key):
    return lambda row: f"{Decimal(row.get(key) or 0):,.3f}"


def _int(key):
    return lambda row: f"{row.get(key) or 0}"


def _pct(key):
    return lambda row: f"{Decimal(row.get(key) or 0):.2f}"


def _date(key):
    return lambda row: f"{row[key]:%d-%m-%Y}" if row.get(key) else ""


def _text(key):
    return lambda row: row.get(key) or ""


def _tile(label, value, tone="slate", icon="file", note="", change=None, href=""):
    return {"label": label, "value": value, "tone": tone, "icon": icon, "note": note, "delta": change, "href": href}


# ---------------------------------------------------------------------------
# 1. Daily Position
# ---------------------------------------------------------------------------

DAILY_POSITION_COLUMNS = ColumnSet("reports.daily_position", (
    Column("figure", "Figure", locked=True, export=_text("figure")),
    Column("value", "Value", locked=True, export=_text("value"), numeric=True),
    Column("unit", "Unit", export=_text("unit")),
))


class DailyPositionView(ReportView):
    page = REPORT_PAGE
    title = "Daily Position"
    template_name = "reports/daily_position.html"
    columns = DAILY_POSITION_COLUMNS
    url_name = "portal:report_daily_position"
    default_preset = PRESET_TODAY
    landscape = False
    sort_fields = {}

    def build(self):
        day = self.period().end
        data = selectors.daily_position(day)
        wheat, ground, sold, stock = data["wheat"], data["grinding"], data["sales"], data["wheat_stock"]
        rows = [
            {"figure": "Wheat purchased (kg)", "value": f"{wheat['kg']:,.3f}", "unit": "kg"},
            {"figure": "Wheat purchased (mund)", "value": f"{mund(wheat['kg']):,.3f}", "unit": "mund"},
            {"figure": "Wheat purchased (Rs)", "value": format_amount(wheat["amount"]), "unit": "Rs"},
            {"figure": "Purchase slips", "value": str(wheat["slips"]), "unit": ""},
            {"figure": "Wheat ground (kg)", "value": f"{ground['wheat_kg']:,.3f}", "unit": "kg"},
            {"figure": "Output produced (kg)", "value": f"{ground['output_kg']:,.3f}", "unit": "kg"},
        ]
        rows += [
            {"figure": f"  {row['product']}", "value": f"{row['kg']:,.3f}", "unit": "kg"} for row in data["production"]
        ]
        rows += [
            {"figure": "Bags sold", "value": f"{sold['bags']:,.0f}", "unit": "bags"},
            {"figure": "Sales (Rs)", "value": format_amount(sold["net"]), "unit": "Rs"},
            {"figure": "Sale invoices", "value": str(sold["invoices"]), "unit": ""},
            {"figure": "Cash in", "value": format_amount(data["cash"]["cash_in"]), "unit": "Rs"},
            {"figure": "Cash out", "value": format_amount(data["cash"]["cash_out"]), "unit": "Rs"},
            {"figure": "Cash & bank closing", "value": format_amount(data["cash_closing"]), "unit": "Rs"},
            {"figure": "Receivables", "value": format_amount(data["receivables"]), "unit": "Rs"},
            {"figure": "Payables", "value": format_amount(data["payables"]), "unit": "Rs"},
            {"figure": "Wheat stock (kg)", "value": f"{stock['stock_kg']:,.3f}", "unit": "kg"},
            {"figure": "Wheat stock (mund)", "value": f"{mund(stock['stock_kg']):,.3f}", "unit": "mund"},
            {"figure": "Avg daily grinding, 30 days (kg)", "value": f"{stock['per_day_kg']:,.3f}", "unit": "kg"},
            {"figure": "Wheat stock in days", "value": f"{stock['days']}" if stock["days"] is not None else "—", "unit": "days"},
        ]
        days_note = f"{stock['per_day_kg']:,.0f} kg/day" if stock["per_day_kg"] else "no grinding in 30 days"
        tiles = [
            _tile("Wheat bought", f"{mund(wheat['kg']):,.3f} md", "amber", "wheat", f"{wheat['kg']:,.0f} kg · Rs {format_amount(wheat['amount'])}"),
            _tile("Wheat ground", f"{mund(ground['wheat_kg']):,.3f} md", "violet", "settings", f"{ground['wheat_kg']:,.0f} kg in {ground['vouchers']} runs"),
            _tile("Produced", f"{ground['output_kg']:,.0f} kg", "teal", "box", f"{mund(ground['output_kg']):,.3f} md"),
            _tile("Bags sold", f"{sold['bags']:,.0f}", "sky", "receipt", f"Rs {format_amount(sold['net'])} · {sold['invoices']} invoices"),
            _tile("Cash & bank", format_amount(data["cash_closing"]), "green", "cash", f"in {format_amount(data['cash']['cash_in'])} · out {format_amount(data['cash']['cash_out'])}"),
            _tile("Receivable", format_amount(data["receivables"]), "sky", "users", "due from customers"),
            _tile("Payable", format_amount(data["payables"]), "rose", "users", "owed to suppliers"),
            _tile("Wheat stock", f"{stock['days']} days" if stock["days"] is not None else "—", "slate", "layers", f"{mund(stock['stock_kg']):,.0f} md · {days_note}"),
        ]
        return {"rows": rows, "totals": {}, "tiles": tiles, "extra": data}

    def sorted_rows(self):
        return list(self.data()["rows"]), {"sort_key": "", "sort_dir": "asc", "sort_base_query": ""}

    def footer_cells(self, columns):
        return None

    def period_label(self):
        return f"{self.period().end:%A, %d %B %Y}"


class DailyPositionExportView(ReportExportView):
    page = REPORT_PAGE
    report_view = DailyPositionView
    print_template = "reports/daily_position_print.html"

    def _paper(self, request, header, rows):
        paper = super()._paper(request, header, rows)
        paper["data"] = self.screen().data()
        paper["tiles"] = paper["data"]["tiles"]
        return paper


class DailyPositionColumnsView(ReportColumnsView):
    page = REPORT_PAGE
    report_view = DailyPositionView


# ---------------------------------------------------------------------------
# 2. Month at a Glance
# ---------------------------------------------------------------------------

MONTH_GLANCE_COLUMNS = ColumnSet("reports.month_glance", (
    Column("date", "Date", locked=True, export=_date("date")),
    Column("purchase_kg", "Purchase Kg", export=_kg("purchase_kg"), numeric=True),
    Column("purchase_mund", "Purchase Mund", default=False, export=lambda r: f"{mund(r['purchase_kg']):,.3f}", numeric=True),
    Column("purchase_amount", "Purchase Rs", export=_money("purchase_amount"), numeric=True),
    Column("grinding_kg", "Grinding Kg", export=_kg("grinding_kg"), numeric=True),
    Column("production_kg", "Production Kg", export=_kg("production_kg"), numeric=True),
    Column("sales", "Sales Rs", export=_money("sales"), numeric=True),
    Column("cash_in", "Cash In", export=_money("cash_in"), numeric=True),
    Column("cash_out", "Cash Out", export=_money("cash_out"), numeric=True),
    Column("closing_cash", "Closing Cash", export=_money("closing_cash"), numeric=True),
))


class MonthGlanceView(ReportView):
    page = REPORT_PAGE
    title = "Month at a Glance"
    template_name = "reports/month_glance.html"
    columns = MONTH_GLANCE_COLUMNS
    url_name = "portal:report_month_glance"
    default_preset = PRESET_MONTH
    default_sort = "date"
    sort_fields = {
        "date": "date", "purchase_kg": "purchase_kg", "purchase_amount": "purchase_amount", "grinding_kg": "grinding_kg",
        "production_kg": "production_kg", "sales": "sales", "cash_in": "cash_in", "cash_out": "cash_out", "closing_cash": "closing_cash",
    }

    def build(self):
        period = self.period()
        data = selectors.month_glance(period.start, period.end)
        before = previous_period(period)
        last = selectors.month_glance_totals(before.start, before.end)
        totals = data["totals"]
        label = f"vs {before.label}"
        tiles = [
            _tile("Wheat bought", f"{mund(totals['purchase_kg']):,.0f} md", "amber", "wheat", change=delta(totals["purchase_kg"], last["purchase_kg"])),
            _tile("Wheat ground", f"{mund(totals['grinding_kg']):,.0f} md", "violet", "settings", change=delta(totals["grinding_kg"], last["grinding_kg"])),
            _tile("Produced", f"{totals['production_kg']:,.0f} kg", "teal", "box", change=delta(totals["production_kg"], last["production_kg"])),
            _tile("Sales", format_amount(totals["sales"]), "sky", "receipt", change=delta(totals["sales"], last["sales"])),
            _tile("Cash in", format_amount(totals["cash_in"]), "green", "cash", change=delta(totals["cash_in"], last["cash_in"])),
            _tile("Cash out", format_amount(totals["cash_out"]), "rose", "cash", change=delta(totals["cash_out"], last["cash_out"])),
            _tile("Closing cash", format_amount(totals["closing_cash"]), "slate", "ledger", f"opened at {format_amount(totals['opening_cash'])}"),
        ]
        for tile in tiles:
            if tile["delta"]:
                tile["delta_label"] = label
        return {"rows": data["rows"], "totals": totals, "tiles": tiles, "extra": {"previous": before}}


class MonthGlanceExportView(ReportExportView):
    page = REPORT_PAGE
    report_view = MonthGlanceView


class MonthGlanceColumnsView(ReportColumnsView):
    page = REPORT_PAGE
    report_view = MonthGlanceView


# ---------------------------------------------------------------------------
# 3. Profitability by Product
# ---------------------------------------------------------------------------

PRODUCT_PROFIT_COLUMNS = ColumnSet("reports.product_profit", (
    Column("product", "Product", locked=True, export=_text("product")),
    Column("family", "Category", export=_text("family")),
    Column("invoices", "Invoices", default=False, export=_int("invoices"), numeric=True),
    Column("qty", "Qty Sold", export=_kg("qty"), numeric=True),
    Column("kg", "Kg", default=False, export=_kg("kg"), numeric=True),
    Column("net", "Sales Rs", export=_money("net"), numeric=True),
    Column("avg_rate", "Avg Rate", export=_money("avg_rate"), numeric=True),
    Column("cost_rate", "Cost Rate", export=_money("cost_rate"), numeric=True),
    Column("cogs", "COGS", export=_money("cogs"), numeric=True),
    Column("margin", "Gross Margin", export=_money("margin"), numeric=True),
    Column("margin_pct", "Margin %", export=_pct("margin_pct"), numeric=True),
    Column("share", "Share %", default=False, export=_pct("share"), numeric=True),
))

TONES = ("sky", "teal", "violet", "amber", "green", "sky")


class ProductProfitView(ReportView):
    page = REPORT_PAGE
    title = "Profitability by Product"
    template_name = "reports/product_profit.html"
    columns = PRODUCT_PROFIT_COLUMNS
    url_name = "portal:report_product_profit"
    default_sort = "net"
    default_sort_dir = "desc"
    sort_fields = {
        "product": "product", "family": "family", "invoices": "invoices", "qty": "qty", "kg": "kg", "net": "net",
        "avg_rate": "avg_rate", "cost_rate": "cost_rate", "cogs": "cogs", "margin": "margin", "margin_pct": "margin_pct", "share": "share",
    }

    def build(self):
        period = self.period()
        data = selectors.product_profit(period.start, period.end)
        totals = data["totals"]
        tiles = [
            _tile("Sales", format_amount(totals["net"]), "sky", "receipt", f"{totals['qty']:,.0f} units"),
            _tile("Gross margin", format_amount(totals["margin"]), "green", "cash", f"{totals['margin_pct']}%"),
        ]
        for index, row in enumerate(data["rows"][:4]):
            tiles.append(_tile(row["product"], f"{row['margin_pct']}%", TONES[index % len(TONES)], "box", f"Rs {format_amount(row['margin'])} on {format_amount(row['net'])}"))
        return {"rows": data["rows"], "totals": totals, "tiles": tiles}


class ProductProfitExportView(ReportExportView):
    page = REPORT_PAGE
    report_view = ProductProfitView


class ProductProfitColumnsView(ReportColumnsView):
    page = REPORT_PAGE
    report_view = ProductProfitView


# ---------------------------------------------------------------------------
# 4. Receivables Aging
# ---------------------------------------------------------------------------

RECEIVABLES_AGING_COLUMNS = ColumnSet("reports.receivables_aging", (
    Column("party", "Customer", locked=True, export=_text("party")),
    Column("city", "City", default=False, export=_text("city")),
    Column("phone", "Phone", default=False, export=_text("phone")),
    Column("b0", "0-30", export=_money("b0"), numeric=True),
    Column("b1", "31-60", export=_money("b1"), numeric=True),
    Column("b2", "61-90", export=_money("b2"), numeric=True),
    Column("b3", "90+", export=_money("b3"), numeric=True),
    Column("balance", "Balance", locked=True, export=_money("balance"), numeric=True),
    Column("credit_limit", "Credit Limit", export=lambda r: format_amount(r["credit_limit"]) if r.get("credit_limit") is not None else "", numeric=True),
    Column("over_by", "Over Limit By", export=lambda r: format_amount(r["over_by"]) if r.get("over_limit") else "", numeric=True),
    Column("last_sale", "Last Sale", default=False, export=_date("last_sale")),
))


class ReceivablesAgingView(ReportView):
    page = REPORT_PAGE
    title = "Receivables Aging"
    template_name = "reports/receivables_aging.html"
    columns = RECEIVABLES_AGING_COLUMNS
    url_name = "portal:report_receivables_aging"
    as_of_report = True
    default_sort = "balance"
    default_sort_dir = "desc"
    sort_fields = {
        "party": "party", "city": "city", "b0": "b0", "b1": "b1", "b2": "b2", "b3": "b3", "balance": "balance",
        "credit_limit": "credit_limit", "over_by": "over_by", "last_sale": "last_sale",
    }

    def filters(self):
        return {
            "customer": (self.request.GET.get("customer") or "").strip(),
            "over_limit": self.request.GET.get("over_limit") == "1",
        }

    def build(self):
        filters = self.filters()
        data = selectors.receivables_aging(
            self.as_of(), customer_id=filters["customer"] or None, over_limit_only=filters["over_limit"],
        )
        totals = data["totals"]
        base = f"as_of={self.as_of():%Y-%m-%d}"
        if filters["customer"]:
            base += f"&customer={filters['customer']}"
        tiles = [
            _tile("Receivable", format_amount(totals["balance"]), "sky", "users", f"{len(data['rows'])} customers", href=f"?{base}"),
            _tile("0-30", format_amount(totals["b0"]), "green", "clock"),
            _tile("31-60", format_amount(totals["b1"]), "amber", "clock"),
            _tile("61-90", format_amount(totals["b2"]), "amber", "clock"),
            _tile("90+", format_amount(totals["b3"]), "rose", "alert"),
            _tile("Over limit", str(totals["over_limit"]), "violet", "alert", f"Rs {format_amount(totals['over_by'])} over", href=f"?{base}&over_limit=1"),
        ]
        tiles[-1]["on"] = filters["over_limit"]
        return {"rows": data["rows"], "totals": totals, "tiles": tiles}

    def filter_summary(self):
        filters = self.filters()
        parts = []
        if filters["customer"]:
            customer = Customer.objects.filter(pk=filters["customer"]).first()
            parts.append(f"Customer: {customer.customer_name if customer else filters['customer']}")
        if filters["over_limit"]:
            parts.append("Over limit only")
        return " · ".join(parts)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = self.filters()
        context["customer_options"] = Customer.objects.filter(status=STATUS_ACTIVE).only("pk", "customer_name")
        context["ledger_url_name"] = "inventory:customer_ledger_list"
        return context


class ReceivablesAgingExportView(ReportExportView):
    page = REPORT_PAGE
    report_view = ReceivablesAgingView


class ReceivablesAgingColumnsView(ReportColumnsView):
    page = REPORT_PAGE
    report_view = ReceivablesAgingView


# ---------------------------------------------------------------------------
# 5. Payables Aging
# ---------------------------------------------------------------------------

PAYABLES_AGING_COLUMNS = ColumnSet("reports.payables_aging", (
    Column("party", "Supplier", locked=True, export=_text("party")),
    Column("kind", "Type", export=_text("kind")),
    Column("city", "City", default=False, export=_text("city")),
    Column("phone", "Phone", default=False, export=_text("phone")),
    Column("invoices", "Invoices", default=False, export=_int("invoices"), numeric=True),
    Column("b0", "0-30", export=_money("b0"), numeric=True),
    Column("b1", "31-60", export=_money("b1"), numeric=True),
    Column("b2", "61-90", export=_money("b2"), numeric=True),
    Column("b3", "90+", export=_money("b3"), numeric=True),
    Column("balance", "Balance", locked=True, export=_money("balance"), numeric=True),
    Column("oldest", "Oldest Unpaid", export=_date("oldest")),
    Column("last_invoice", "Last Invoice", default=False, export=_date("last_invoice")),
))


class PayablesAgingView(ReportView):
    page = REPORT_PAGE
    title = "Payables Aging"
    template_name = "reports/payables_aging.html"
    columns = PAYABLES_AGING_COLUMNS
    url_name = "portal:report_payables_aging"
    as_of_report = True
    default_sort = "balance"
    default_sort_dir = "desc"
    sort_fields = {
        "party": "party", "kind": "kind", "city": "city", "invoices": "invoices", "b0": "b0", "b1": "b1", "b2": "b2", "b3": "b3",
        "balance": "balance", "oldest": "oldest", "last_invoice": "last_invoice",
    }

    def filters(self):
        return {
            "supplier": (self.request.GET.get("supplier") or "").strip(),
            "kind": (self.request.GET.get("kind") or "").strip(),
        }

    def build(self):
        filters = self.filters()
        data = selectors.payables_aging(self.as_of(), supplier_id=filters["supplier"] or None, kind=filters["kind"])
        totals = data["totals"]
        base = f"as_of={self.as_of():%Y-%m-%d}"
        tiles = [
            _tile("Payable", format_amount(totals["balance"]), "rose", "users", f"{len(data['rows'])} suppliers", href=f"?{base}"),
            _tile("0-30", format_amount(totals["b0"]), "green", "clock"),
            _tile("31-60", format_amount(totals["b1"]), "amber", "clock"),
            _tile("61-90", format_amount(totals["b2"]), "amber", "clock"),
            _tile("90+", format_amount(totals["b3"]), "rose", "alert"),
        ]
        for key, label in selectors.SUPPLIER_KIND_CHOICES:
            tiles.append(_tile(label, "", "slate", "users", href=f"?{base}&kind={key}"))
            tiles[-1]["on"] = filters["kind"] == key
        return {"rows": data["rows"], "totals": totals, "tiles": tiles}

    def filter_summary(self):
        filters = self.filters()
        parts = []
        if filters["supplier"]:
            supplier = Supplier.objects.filter(pk=filters["supplier"]).first()
            parts.append(f"Supplier: {supplier.name if supplier else filters['supplier']}")
        if filters["kind"]:
            parts.append(dict(selectors.SUPPLIER_KIND_CHOICES).get(filters["kind"], filters["kind"]))
        return " · ".join(parts)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = self.filters()
        context["supplier_options"] = Supplier.objects.filter(status=STATUS_ACTIVE).only("pk", "name")
        context["kind_choices"] = selectors.SUPPLIER_KIND_CHOICES
        return context


class PayablesAgingExportView(ReportExportView):
    page = REPORT_PAGE
    report_view = PayablesAgingView


class PayablesAgingColumnsView(ReportColumnsView):
    page = REPORT_PAGE
    report_view = PayablesAgingView
