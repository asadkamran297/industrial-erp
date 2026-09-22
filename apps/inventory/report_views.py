"""Sales reporting screens (catalogue group B)."""

from decimal import Decimal

from apps.core.constants import INV_POS_STATUS_CHOICES, PAY_MODE_CHOICES
from apps.core.formatting import format_amount
from apps.core.reporting import (
    PRESET_MONTH,
    PRESET_TODAY,
    ReportColumnsView,
    ReportExportView,
    ReportView,
    delta,
    previous_period,
)
from apps.core.table_columns import Column, ColumnSet

from . import selectors

SALES_PAGE = "reports.sales"


def _money(key):
    return lambda row: format_amount(row.get(key)) if row.get(key) is not None else ""


def _qty(key, places=0):
    return lambda row: f"{Decimal(row.get(key) or 0):,.{places}f}"


def _int(key):
    return lambda row: f"{row.get(key) or 0}"


def _date(key):
    return lambda row: f"{row[key]:%d-%m-%Y}" if row.get(key) else ""


def _text(key):
    return lambda row: row.get(key) or ""


def _tile(label, value, tone="slate", icon="file", note="", change=None, href="", on=False):
    return {"label": label, "value": value, "tone": tone, "icon": icon, "note": note, "delta": change, "href": href, "on": on}


def _customer_spec():
    return ("customer", "Customer", selectors.customer_options)


def _product_spec():
    return ("product", "Product", selectors.product_options)


# ---------------------------------------------------------------------------
# 6. Sales Register
# ---------------------------------------------------------------------------

SALES_REGISTER_COLUMNS = ColumnSet("reports.sales_register", (
    Column("number", "Invoice", locked=True, export=_text("number"), kind="link", link="inventory:pos_detail"),
    Column("date", "Date", locked=True, export=_date("date"), kind="date"),
    Column("customer", "Customer", export=_text("customer"), kind="link", link="inventory:customer_detail", link_key="customer_id"),
    Column("products", "Products", export=_text("products")),
    Column("bags", "Bags", export=_qty("bags"), numeric=True, kind="qty", places=0, total=True),
    Column("kg", "Kg", default=False, export=_qty("kg", 3), numeric=True, kind="qty", places=3, total=True),
    Column("gross", "Gross", export=_money("gross"), numeric=True, kind="money", total=True),
    Column("discount", "Discount", export=_money("discount"), numeric=True, kind="money", total=True),
    Column("tax", "Tax", default=False, export=_money("tax"), numeric=True, kind="money", total=True),
    Column("net", "Net", locked=True, export=_money("net"), numeric=True, kind="money", total=True),
    Column("paid", "Paid", export=_money("paid"), numeric=True, kind="money", total=True),
    Column("balance", "Balance", export=_money("balance"), numeric=True, kind="money", total=True),
    Column("pay_mode", "Pay Mode", export=_text("pay_mode")),
    Column("status", "Status", export=_text("status_label"), kind="status"),
    Column("user", "Posted By", default=False, export=_text("user")),
))


class SalesRegisterView(ReportView):
    page = SALES_PAGE
    title = "Sales Register"
    template_name = "reports/generic.html"
    columns = SALES_REGISTER_COLUMNS
    url_name = "inventory:report_sale"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {
        "number": "pk", "date": "date", "customer": "customer", "bags": "bags", "kg": "kg", "gross": "gross", "discount": "discount",
        "tax": "tax", "net": "net", "paid": "paid", "balance": "balance", "pay_mode": "pay_mode", "status": "status",
    }
    filter_specs = (
        _customer_spec(),
        _product_spec(),
        ("pay_mode", "Pay Mode", PAY_MODE_CHOICES),
        ("status", "Status", INV_POS_STATUS_CHOICES),
    )

    def build(self):
        period, f = self.period(), self.filters()
        data = selectors.sales_register(period.start, period.end, f["customer"] or None, f["product"] or None, f["pay_mode"], f["status"])
        t = data["totals"]
        base = period.query + "".join(f"&{k}={v}" for k, v in f.items() if v and k != "pay_mode")
        tiles = [
            _tile("Invoices", str(t["invoices"]), "slate", "receipt", href=f"?{base}"),
            _tile("Bags", f"{t['bags']:,.0f}", "teal", "box", f"{t['kg']:,.0f} kg"),
            _tile("Net", format_amount(t["net"]), "sky", "cash", f"gross {format_amount(t['gross'])}"),
            _tile("Cash", format_amount(t["cash"]), "green", "cash", href=f"?{base}&pay_mode=cash", on=f["pay_mode"] == "cash"),
            _tile("Credit", format_amount(t["credit"]), "amber", "users", href=f"?{base}&pay_mode=credit", on=f["pay_mode"] == "credit"),
            _tile("Balance", format_amount(t["balance"]), "rose", "alert", f"paid {format_amount(t['paid'])}"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


class SalesRegisterExportView(ReportExportView):
    page = SALES_PAGE
    report_view = SalesRegisterView


class SalesRegisterColumnsView(ReportColumnsView):
    page = SALES_PAGE
    report_view = SalesRegisterView


# ---------------------------------------------------------------------------
# 7. Sales Summary
# ---------------------------------------------------------------------------

SALES_SUMMARY_COLUMNS = ColumnSet("reports.sales_summary", (
    Column("label", "Period", locked=True, export=_text("label")),
    Column("invoices", "Invoices", export=_int("invoices"), numeric=True, kind="int", total=True),
    Column("bags", "Bags", export=_qty("bags"), numeric=True, kind="qty", places=0, total=True),
    Column("kg", "Kg", export=_qty("kg", 3), numeric=True, kind="qty", places=3, total=True),
    Column("gross", "Gross", export=_money("gross"), numeric=True, kind="money", total=True),
    Column("discount", "Discount", export=_money("discount"), numeric=True, kind="money", total=True),
    Column("net", "Net", locked=True, export=_money("net"), numeric=True, kind="money", total=True),
    Column("cash", "Cash", export=_money("cash"), numeric=True, kind="money", total=True),
    Column("credit", "Credit", export=_money("credit"), numeric=True, kind="money", total=True),
    Column("card", "Card", default=False, export=_money("card"), numeric=True, kind="money", total=True),
    Column("online", "Online", default=False, export=_money("online"), numeric=True, kind="money", total=True),
    Column("returns", "Returns", export=_money("returns"), numeric=True, kind="money", total=True),
    Column("net_of_returns", "Net of Returns", export=_money("net_of_returns"), numeric=True, kind="money", total=True),
))


class SalesSummaryView(ReportView):
    page = SALES_PAGE
    title = "Sales Summary"
    template_name = "reports/generic.html"
    columns = SALES_SUMMARY_COLUMNS
    url_name = "inventory:report_sales_summary"
    group_toggle = True
    default_sort = "label"
    sort_fields = {
        "label": "period", "invoices": "invoices", "bags": "bags", "kg": "kg", "gross": "gross", "discount": "discount", "net": "net",
        "cash": "cash", "credit": "credit", "card": "card", "online": "online", "returns": "returns", "net_of_returns": "net_of_returns",
    }
    filter_specs = (_customer_spec(),)

    def build(self):
        period, f = self.period(), self.filters()
        data = selectors.sales_summary(period.start, period.end, self.group(), f["customer"] or None)
        t = data["totals"]
        before = previous_period(period)
        last = selectors.sales_totals(before.start, before.end)
        label = f"vs {before.label}"
        tiles = [
            _tile("Invoices", str(t["invoices"]), "slate", "receipt", change=delta(t["invoices"], last["invoices"])),
            _tile("Bags", f"{t['bags']:,.0f}", "teal", "box", change=delta(t["bags"], last["bags"])),
            _tile("Net", format_amount(t["net"]), "sky", "cash", change=delta(t["net"], last["net"])),
            _tile("Cash", format_amount(t["cash"]), "green", "cash", change=delta(t["cash"], last["cash"])),
            _tile("Credit", format_amount(t["credit"]), "amber", "users", change=delta(t["credit"], last["credit"])),
            _tile("Returns", format_amount(t["returns"]), "rose", "reverse", change=delta(t["returns"], last["returns"])),
        ]
        for tile in tiles:
            tile["delta_label"] = label
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


class SalesSummaryExportView(ReportExportView):
    page = SALES_PAGE
    report_view = SalesSummaryView


class SalesSummaryColumnsView(ReportColumnsView):
    page = SALES_PAGE
    report_view = SalesSummaryView


# ---------------------------------------------------------------------------
# 8. Party-wise Sales
# ---------------------------------------------------------------------------

CUSTOMER_SALES_COLUMNS = ColumnSet("reports.customer_sales", (
    Column("customer", "Customer", locked=True, export=_text("customer"), kind="link", link="inventory:customer_detail", link_key="customer_id"),
    Column("city", "City", export=_text("city")),
    Column("phone", "Phone", default=False, export=_text("phone")),
    Column("invoices", "Invoices", export=_int("invoices"), numeric=True, kind="int", total=True),
    Column("bags", "Bags", export=_qty("bags"), numeric=True, kind="qty", places=0, total=True),
    Column("net", "Net Sales", locked=True, export=_money("net"), numeric=True, kind="money", total=True),
    Column("returns", "Returns", export=_money("returns"), numeric=True, kind="money", total=True),
    Column("received", "Received", export=_money("received"), numeric=True, kind="money", total=True),
    Column("balance", "Closing Balance", export=_money("balance"), numeric=True, kind="money", total=True),
    Column("credit_days", "Credit Days", default=False, export=_int("credit_days"), numeric=True, kind="int", total=True),
    Column("last_sale", "Last Sale", export=_date("last_sale"), kind="date"),
))


class CustomerSalesView(ReportView):
    page = SALES_PAGE
    title = "Party-wise Sales"
    template_name = "reports/generic.html"
    columns = CUSTOMER_SALES_COLUMNS
    url_name = "inventory:report_customer_sales"
    default_sort = "net"
    default_sort_dir = "desc"
    sort_fields = {
        "customer": "customer", "city": "city", "invoices": "invoices", "bags": "bags", "net": "net", "returns": "returns",
        "received": "received", "balance": "balance", "credit_days": "credit_days", "last_sale": "last_sale",
    }
    filter_specs = (_customer_spec(), ("city", "City", selectors.city_options))

    def build(self):
        period, f = self.period(), self.filters()
        data = selectors.customer_sales(period.start, period.end, f["customer"] or None, f["city"] or None)
        t = data["totals"]
        tiles = [
            _tile("Customers", str(len(data["rows"])), "slate", "users"),
            _tile("Invoices", str(t["invoices"]), "slate", "receipt", f"{t['bags']:,.0f} bags"),
            _tile("Net sales", format_amount(t["net"]), "sky", "cash"),
            _tile("Returns", format_amount(t["returns"]), "rose", "reverse"),
            _tile("Received", format_amount(t["received"]), "green", "cash"),
            _tile("Outstanding", format_amount(t["balance"]), "amber", "alert"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


class CustomerSalesExportView(ReportExportView):
    page = SALES_PAGE
    report_view = CustomerSalesView


class CustomerSalesColumnsView(ReportColumnsView):
    page = SALES_PAGE
    report_view = CustomerSalesView


# ---------------------------------------------------------------------------
# 9. Product-wise Sales
# ---------------------------------------------------------------------------

PRODUCT_SALES_COLUMNS = ColumnSet("reports.product_sales", (
    Column("product", "Product", locked=True, export=_text("product"), kind="text"),
    Column("family", "Category", export=_text("family")),
    Column("invoices", "Invoices", default=False, export=_int("invoices"), numeric=True, kind="int", total=True),
    Column("bags", "Bags", export=_qty("bags"), numeric=True, kind="qty", places=0, total=True),
    Column("kg", "Kg", export=_qty("kg", 3), numeric=True, kind="qty", places=3, total=True),
    Column("net", "Net Sales", locked=True, export=_money("net"), numeric=True, kind="money", total=True),
    Column("avg_rate", "Avg Rate / Bag", export=_money("avg_rate"), numeric=True, kind="money", total=True),
    Column("rate_per_kg", "Rate / Kg", default=False, export=_money("rate_per_kg"), numeric=True, kind="money", total=True),
    Column("share", "Share %", export=_qty("share", 2), numeric=True, kind="qty", places=2),
))

TONES = ("sky", "teal", "violet", "amber", "green", "rose")


class ProductSalesView(ReportView):
    page = SALES_PAGE
    title = "Product-wise Sales"
    template_name = "reports/generic.html"
    columns = PRODUCT_SALES_COLUMNS
    url_name = "inventory:report_product_sales"
    default_sort = "net"
    default_sort_dir = "desc"
    sort_fields = {
        "product": "product", "family": "family", "invoices": "invoices", "bags": "bags", "kg": "kg", "net": "net",
        "avg_rate": "avg_rate", "rate_per_kg": "rate_per_kg", "share": "share",
    }
    filter_specs = (("family", "Category", selectors.family_options), _product_spec(), _customer_spec())

    def build(self):
        period, f = self.period(), self.filters()
        data = selectors.product_sales(period.start, period.end, f["family"] or None, f["product"] or None, f["customer"] or None)
        t = data["totals"]
        tiles = [_tile("Net sales", format_amount(t["net"]), "sky", "cash", f"{t['bags']:,.0f} bags · {t['kg']:,.0f} kg")]
        for index, (family, figures) in enumerate(sorted(data["families"].items(), key=lambda item: -item[1]["net"])[:5]):
            tiles.append(_tile(family or "—", format_amount(figures["net"]), TONES[index % len(TONES)], "box", f"{figures['bags']:,.0f} bags"))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


class ProductSalesExportView(ReportExportView):
    page = SALES_PAGE
    report_view = ProductSalesView


class ProductSalesColumnsView(ReportColumnsView):
    page = SALES_PAGE
    report_view = ProductSalesView


# ---------------------------------------------------------------------------
# 10. Sale Rate History
# ---------------------------------------------------------------------------

RATE_HISTORY_COLUMNS = ColumnSet("reports.rate_history", (
    Column("date", "Date", locked=True, export=_date("date"), kind="date"),
    Column("number", "Invoice", locked=True, export=_text("number"), kind="link", link="inventory:pos_detail"),
    Column("customer", "Customer", export=_text("customer")),
    Column("product", "Product", locked=True, export=_text("product"), kind="text"),
    Column("qty", "Qty", export=_qty("qty"), numeric=True, kind="qty", places=0, total=True),
    Column("billed", "Billed Rate", locked=True, export=_money("billed"), numeric=True, kind="money", total=True),
    Column("list_rate", "List Rate", export=_money("list_rate"), numeric=True, kind="money", total=True),
    Column("variance", "Variance", export=_money("variance"), numeric=True, kind="money", total=True),
    Column("variance_pct", "Variance %", default=False, export=_qty("variance_pct", 2), numeric=True, kind="qty", places=2),
    Column("net", "Net", default=False, export=_money("net"), numeric=True, kind="money", total=True),
))


class RateHistoryView(ReportView):
    page = SALES_PAGE
    title = "Sale Rate History"
    template_name = "reports/generic.html"
    columns = RATE_HISTORY_COLUMNS
    url_name = "inventory:report_rate_history"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {
        "date": "date", "number": "pk", "customer": "customer", "product": "product", "qty": "qty", "billed": "billed",
        "list_rate": "list_rate", "variance": "variance", "variance_pct": "variance_pct", "net": "net",
    }
    filter_specs = (_product_spec(), _customer_spec())

    def build(self):
        period, f = self.period(), self.filters()
        data = selectors.rate_history(period.start, period.end, f["product"] or None, f["customer"] or None)
        t = data["totals"]
        tiles = [
            _tile("Lines", str(t["lines"]), "slate", "receipt", f"{t['qty']:,.0f} bags"),
            _tile("Net", format_amount(t["net"]), "sky", "cash"),
            _tile("Below list", str(t["below_list"]), "rose", "alert", f"Rs {format_amount(-t['given_away'])} under list"),
        ]
        return {"rows": data["rows"], "totals": {"qty": t["qty"], "net": t["net"]}, "tiles": tiles}


class RateHistoryExportView(ReportExportView):
    page = SALES_PAGE
    report_view = RateHistoryView


class RateHistoryColumnsView(ReportColumnsView):
    page = SALES_PAGE
    report_view = RateHistoryView


# ---------------------------------------------------------------------------
# 11. Sale Returns
# ---------------------------------------------------------------------------

SALE_RETURNS_COLUMNS = ColumnSet("reports.sale_returns", (
    Column("number", "Return", locked=True, export=_text("number"), kind="link", link="inventory:pos_return_detail"),
    Column("date", "Date", locked=True, export=_date("date"), kind="date"),
    Column("customer", "Customer", export=_text("customer")),
    Column("sale_number", "Against Invoice", export=_text("sale_number"), kind="link", link="inventory:pos_detail", link_key="sale_pk"),
    Column("sale_date", "Invoice Date", default=False, export=_date("sale_date"), kind="date"),
    Column("products", "Products", export=_text("products")),
    Column("qty", "Qty", export=_qty("qty"), numeric=True, kind="qty", places=0, total=True),
    Column("kg", "Kg", default=False, export=_qty("kg", 3), numeric=True, kind="qty", places=3, total=True),
    Column("invoice_amount", "Invoice Amount", default=False, export=_money("invoice_amount"), numeric=True, kind="money", total=True),
    Column("returned", "Returned", locked=True, export=_money("returned"), numeric=True, kind="money", total=True),
    Column("adjusted", "Adjusted", export=_money("adjusted"), numeric=True, kind="money", total=True),
    Column("pay_mode", "Refund Mode", export=_text("pay_mode")),
    Column("status", "Status", export=_text("status_label"), kind="status"),
    Column("remarks", "Remarks", default=False, export=_text("remarks")),
))


class SaleReturnsView(ReportView):
    page = SALES_PAGE
    title = "Sale Returns"
    template_name = "reports/generic.html"
    columns = SALE_RETURNS_COLUMNS
    url_name = "inventory:report_sale_return"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {
        "number": "pk", "date": "date", "customer": "customer", "sale_number": "sale_pk", "qty": "qty", "kg": "kg",
        "invoice_amount": "invoice_amount", "returned": "returned", "adjusted": "adjusted", "pay_mode": "pay_mode", "status": "status",
    }
    filter_specs = (_customer_spec(), _product_spec())

    def build(self):
        period, f = self.period(), self.filters()
        data = selectors.sale_returns(period.start, period.end, f["customer"] or None, f["product"] or None)
        t = data["totals"]
        tiles = [
            _tile("Returns", str(t["returns"]), "slate", "reverse"),
            _tile("Qty", f"{t['qty']:,.0f}", "teal", "box", f"{t['kg']:,.0f} kg"),
            _tile("Returned", format_amount(t["returned"]), "rose", "cash"),
            _tile("Adjusted", format_amount(t["adjusted"]), "amber", "cash"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


class SaleReturnsExportView(ReportExportView):
    page = SALES_PAGE
    report_view = SaleReturnsView


class SaleReturnsColumnsView(ReportColumnsView):
    page = SALES_PAGE
    report_view = SaleReturnsView


# ---------------------------------------------------------------------------
# 12. POS Cash Sales Day Sheet
# ---------------------------------------------------------------------------

DAY_SHEET_COLUMNS = ColumnSet("reports.day_sheet", (
    Column("number", "Invoice", locked=True, export=_text("number"), kind="link", link="inventory:pos_detail"),
    Column("date", "Date", export=_date("date"), kind="date"),
    Column("time", "Time", export=lambda r: f"{r['time']:%H:%M}" if r.get("time") else "", kind="time"),
    Column("customer", "Customer", export=_text("customer")),
    Column("cashier", "Cashier", export=_text("cashier")),
    Column("gross", "Gross", export=_money("gross"), numeric=True, kind="money", total=True),
    Column("discount", "Discount", export=_money("discount"), numeric=True, kind="money", total=True),
    Column("cash", "Cash", export=_money("cash"), numeric=True, kind="money", total=True),
    Column("card", "Card", export=_money("card"), numeric=True, kind="money", total=True),
    Column("online", "Online", export=_money("online"), numeric=True, kind="money", total=True),
    Column("net", "Total", locked=True, export=_money("net"), numeric=True, kind="money", total=True),
))


class DaySheetView(ReportView):
    page = SALES_PAGE
    title = "POS Day Sheet"
    template_name = "reports/generic.html"
    columns = DAY_SHEET_COLUMNS
    url_name = "inventory:report_day_sheet"
    default_preset = PRESET_TODAY
    default_sort = "time"
    sort_fields = {"number": "pk", "date": "date", "time": "pk", "customer": "customer", "cashier": "cashier", "gross": "gross", "discount": "discount", "cash": "cash", "card": "card", "online": "online", "net": "net"}
    filter_specs = (("cashier", "Cashier", selectors.cashier_options),)

    def build(self):
        period, f = self.period(), self.filters()
        data = selectors.day_sheet(period.start, period.end, f["cashier"] or None)
        t = data["totals"]
        tiles = [
            _tile("Cash", format_amount(t["cash"]), "green", "cash"),
            _tile("Card", format_amount(t["card"]), "sky", "cash"),
            _tile("Online", format_amount(t["online"]), "violet", "cash"),
            _tile("Total", format_amount(t["net"]), "slate", "receipt", f"{t['invoices']} invoices · discount {format_amount(t['discount'])}"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


class DaySheetExportView(ReportExportView):
    page = SALES_PAGE
    report_view = DaySheetView


class DaySheetColumnsView(ReportColumnsView):
    page = SALES_PAGE
    report_view = DaySheetView
