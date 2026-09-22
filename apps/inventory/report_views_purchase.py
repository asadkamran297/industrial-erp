"""Purchase reporting screens (catalogue group C)."""

from decimal import Decimal

from apps.core.constants import INV_PURCHASE_INVOICE_STATUS_CHOICES, INV_PURCHASE_ORDER_STATUS_CHOICES
from apps.core.formatting import format_amount
from apps.core.reporting import (
    GROUP_DAY,
    GROUP_WEEK,
    ReportColumnsView,
    ReportExportView,
    ReportView,
    delta,
    previous_period,
)
from apps.core.table_columns import Column, ColumnSet, col

from . import selectors_purchase as sel
from .report_views import _tile

PAGE = "reports.purchase"


def _views(screen):
    """Export and columns views for a report screen, built once."""
    export = type(f"{screen.__name__}Export", (ReportExportView,), {"page": screen.page, "report_view": screen})
    columns = type(f"{screen.__name__}Columns", (ReportColumnsView,), {"page": screen.page, "report_view": screen})
    return export, columns


SUPPLIER = ("supplier", "Supplier", sel.supplier_options)
ARHTI = ("supplier", "Arhti", sel.wheat_supplier_options)


# 14 ------------------------------------------------------------------------

WHEAT_REGISTER_COLUMNS = ColumnSet("reports.wheat_register", (
    col("number", "Slip", "link", locked=True, link="inventory:purchase_invoice_detail"),
    col("date", "Date", "date", locked=True),
    col("supplier", "Arhti", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("vehicle", "Vehicle"),
    col("broker", "Broker", default=False),
    col("product", "Wheat", default=False),
    col("party_weight", "Party Wt", "qty", places=3),
    col("mill_weight", "Mill Wt", "qty", places=3),
    col("selected_weight", "Selected", "qty", places=3, default=False),
    col("weight_source", "Wt Source"),
    col("katla", "Katla", "qty", places=3),
    col("impurities", "Impurities", "qty", places=3),
    col("moisture", "Moisture", "qty", places=3),
    col("sack_deduction", "Sack Ded.", "qty", places=3, default=False),
    col("credit_kg", "Credit Kg", "qty", places=3, total=True, locked=True),
    col("credit_mund", "Mund", "qty", places=3, total=True),
    col("rate_per_mund", "Rate/Mund", "money", total=True),
    col("goods_amount", "Goods", "money", total=True),
    col("freight", "Freight", "money", total=True),
    col("freight_payer", "Freight By", default=False),
    col("brokerage", "Brokerage", "money", total=True, default=False),
    col("brokerage_bearer", "Brokerage By", default=False),
    col("wht", "WHT", "money", total=True),
    col("net_payable", "Net Payable", "money", total=True, locked=True),
    col("paid", "Paid", "money", total=True),
    col("balance", "Balance", "money", total=True),
    col("status", "Status", "status"),
))


class WheatRegisterView(ReportView):
    page = PAGE
    title = "Wheat Purchase Register"
    template_name = "reports/generic.html"
    columns = WHEAT_REGISTER_COLUMNS
    url_name = "inventory:report_purchase"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in WHEAT_REGISTER_COLUMNS.keys if k not in ("number",)} | {"number": "pk"}
    filter_specs = (ARHTI, ("vehicle", "Vehicle", sel.vehicle_options), ("broker", "Broker", sel.broker_options),
                    ("weight_source", "Weight", sel.WEIGHT_SOURCE_CHOICES), ("status", "Status", INV_PURCHASE_INVOICE_STATUS_CHOICES))

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.wheat_register(p.start, p.end, f["supplier"] or None, f["vehicle"], f["broker"] or None, f["weight_source"], f["status"])
        t = data["totals"]
        tiles = [
            _tile("Slips", str(t["slips"]), "slate", "receipt"),
            _tile("Credit weight", f"{t['credit_mund']:,.3f} md", "amber", "wheat", f"{t['credit_kg']:,.0f} kg"),
            _tile("Avg rate / mund", format_amount(t["rate_per_mund"]), "violet", "chart"),
            _tile("Net payable", format_amount(t["net_payable"]), "sky", "cash", f"WHT {format_amount(t['wht'])}"),
            _tile("Balance", format_amount(t["balance"]), "rose", "alert", f"paid {format_amount(t['paid'])}"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


WheatRegisterExportView, WheatRegisterColumnsView = _views(WheatRegisterView)


# 15 ------------------------------------------------------------------------

PURCHASE_SUMMARY_COLUMNS = ColumnSet("reports.purchase_summary", (
    col("label", "Period", locked=True),
    col("slips", "Slips", "int", total=True),
    col("kg", "Kg", "qty", places=3, total=True),
    col("mund", "Mund", "qty", places=3, total=True),
    col("avg_rate", "Avg Rate/Mund", "money", total=True),
    col("amount", "Goods", "money", total=True, locked=True),
    col("freight", "Freight", "money", total=True),
    col("brokerage", "Brokerage", "money", total=True),
    col("wht", "WHT", "money", total=True),
    col("total", "Invoice Total", "money", total=True, default=False),
    col("paid", "Paid", "money", total=True),
    col("balance", "Balance", "money", total=True),
))


class PurchaseSummaryView(ReportView):
    page = PAGE
    title = "Purchase Summary"
    template_name = "reports/generic.html"
    columns = PURCHASE_SUMMARY_COLUMNS
    url_name = "inventory:report_purchase_summary"
    group_toggle = True
    default_sort = "label"
    sort_fields = {k: k for k in PURCHASE_SUMMARY_COLUMNS.keys} | {"label": "period"}
    filter_specs = (ARHTI,)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.purchase_summary(p.start, p.end, self.group(), f["supplier"] or None)
        t = data["totals"]
        before = previous_period(p)
        last = sel.purchase_totals(before.start, before.end)
        tiles = [
            _tile("Slips", str(t["slips"]), "slate", "receipt", change=delta(t["slips"], last["slips"])),
            _tile("Mund", f"{t['mund']:,.0f}", "amber", "wheat", change=delta(t["mund"], last["mund"])),
            _tile("Avg rate", format_amount(t["avg_rate"]), "violet", "chart", change=delta(t["avg_rate"], last["avg_rate"])),
            _tile("Goods", format_amount(t["amount"]), "sky", "cash", change=delta(t["amount"], last["amount"])),
            _tile("Balance", format_amount(t["balance"]), "rose", "alert"),
        ]
        for tile in tiles:
            tile["delta_label"] = f"vs {before.label}"
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


PurchaseSummaryExportView, PurchaseSummaryColumnsView = _views(PurchaseSummaryView)


# 16 ------------------------------------------------------------------------

SUPPLIER_PURCHASE_COLUMNS = ColumnSet("reports.supplier_purchases", (
    col("supplier", "Arhti", "link", locked=True, link="inventory:supplier_detail", link_key="supplier_id"),
    col("slips", "Slips", "int", total=True),
    col("kg", "Credit Kg", "qty", places=3, total=True),
    col("mund", "Mund", "qty", places=3, total=True),
    col("avg_rate", "Avg Rate/Mund", "money", total=True),
    col("amount", "Goods", "money", total=True, locked=True),
    col("wht", "WHT", "money", total=True, default=False),
    col("paid", "Paid", "money", total=True),
    col("balance", "Balance", "money", total=True),
    col("avg_impurities", "Impurities %", "pct"),
    col("avg_moisture", "Moisture %", "pct"),
    col("sacks_held", "Sacks Held", "qty", total=True),
))


class SupplierPurchasesView(ReportView):
    page = PAGE
    title = "Arhti-wise Purchase"
    template_name = "reports/generic.html"
    columns = SUPPLIER_PURCHASE_COLUMNS
    url_name = "inventory:report_supplier_purchases"
    default_sort = "amount"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in SUPPLIER_PURCHASE_COLUMNS.keys}
    filter_specs = (ARHTI,)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.supplier_purchases(p.start, p.end, f["supplier"] or None)
        t = data["totals"]
        tiles = [
            _tile("Arhtis", str(len(data["rows"])), "slate", "users"),
            _tile("Mund", f"{t['mund']:,.0f}", "amber", "wheat", f"{t['slips']} slips"),
            _tile("Goods", format_amount(t["amount"]), "sky", "cash", f"avg {format_amount(t['avg_rate'])}/md"),
            _tile("Balance", format_amount(t["balance"]), "rose", "alert"),
            _tile("Sacks held", f"{t['sacks_held']:,.0f}", "teal", "box"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


SupplierPurchasesExportView, SupplierPurchasesColumnsView = _views(SupplierPurchasesView)


# 17 ------------------------------------------------------------------------

WHEAT_QUALITY_COLUMNS = ColumnSet("reports.wheat_quality", (
    col("number", "Slip", "link", locked=True, link="inventory:purchase_invoice_detail"),
    col("date", "Date", "date", locked=True),
    col("supplier", "Arhti", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("vehicle", "Vehicle", default=False),
    col("weight", "Weight Kg", "qty", places=3, total=True),
    col("katla", "Katla", "qty", places=3, total=True),
    col("impurities_kg", "Impurities Kg", "qty", places=3, total=True, default=False),
    col("impurities", "Impurities %", "pct", total=True, tone_key="flagged"),
    col("moisture_kg", "Moisture Kg", "qty", places=3, total=True, default=False),
    col("moisture", "Moisture %", "pct", total=True, tone_key="flagged"),
    col("sack_deduction", "Sack Ded.", "qty", places=3, total=True),
    col("deductions", "Deductions Kg", "qty", places=3, total=True),
    col("deduction_pct", "Deduction %", "pct", total=True),
    col("credit_kg", "Credit Kg", "qty", places=3, total=True, locked=True),
))


class WheatQualityView(ReportView):
    page = PAGE
    title = "Wheat Quality"
    template_name = "reports/wheat_quality.html"
    columns = WHEAT_QUALITY_COLUMNS
    url_name = "inventory:report_wheat_quality"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in WHEAT_QUALITY_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (ARHTI,)

    def threshold(self):
        try:
            return Decimal(self.request.GET.get("threshold") or "")
        except Exception:
            return None

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.wheat_quality(p.start, p.end, f["supplier"] or None, self.threshold())
        t = data["totals"]
        tiles = [
            _tile("Slips", str(t["slips"]), "slate", "receipt"),
            _tile("Mill avg impurities", f"{t['impurities'] or 0}%", "amber", "alert"),
            _tile("Mill avg moisture", f"{t['moisture'] or 0}%", "sky", "alert"),
            _tile("Deductions", f"{t['deductions']:,.0f} kg", "rose", "minus", f"{t['deduction_pct'] or 0}% of weight"),
            _tile("Above threshold", str(t["flagged"]), "violet", "alert"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles, "extra": {"averages": data["averages"], "threshold": self.threshold()}}

    def filter_summary(self):
        base = super().filter_summary()
        if self.threshold() is not None:
            base = " · ".join(part for part in (base, f"Threshold {self.threshold()}%") if part)
        return base


WheatQualityExportView, WheatQualityColumnsView = _views(WheatQualityView)


# 18 ------------------------------------------------------------------------

RATE_TREND_COLUMNS = ColumnSet("reports.wheat_rate_trend", (
    col("label", "Period", locked=True),
    col("slips", "Slips", "int", total=True),
    col("mund", "Mund", "qty", places=3, total=True),
    col("kg", "Kg", "qty", places=3, total=True, default=False),
    col("avg_rate", "Avg Rate/Mund", "money", total=True, locked=True),
    col("min_rate", "Min", "money", total=True),
    col("max_rate", "Max", "money", total=True),
    col("amount", "Goods", "money", total=True),
))


class WheatRateTrendView(ReportView):
    page = PAGE
    title = "Wheat Rate Trend"
    template_name = "reports/generic.html"
    columns = RATE_TREND_COLUMNS
    url_name = "inventory:report_wheat_rate_trend"
    group_toggle = True
    default_sort = "label"
    sort_fields = {k: k for k in RATE_TREND_COLUMNS.keys} | {"label": "period"}

    def build(self):
        p = self.period()
        data = sel.rate_trend(p.start, p.end, self.group())
        t = data["totals"]
        rows = data["rows"]
        first, last = (rows[0]["avg_rate"], rows[-1]["avg_rate"]) if rows else (None, None)
        tiles = [
            _tile("Avg rate / mund", format_amount(t["avg_rate"]), "violet", "chart", f"{t['mund']:,.0f} md"),
            _tile("Lowest", format_amount(t["min_rate"]), "green", "sort-down"),
            _tile("Highest", format_amount(t["max_rate"]), "rose", "sort-up"),
            _tile("Trend", format_amount(last) if last is not None else "—", "amber", "chart", change=delta(last, first) if rows else None, ),
        ]
        tiles[-1]["delta_label"] = "since period start"
        return {"rows": rows, "totals": t, "tiles": tiles}


WheatRateTrendExportView, WheatRateTrendColumnsView = _views(WheatRateTrendView)


# 19 ------------------------------------------------------------------------

FREIGHT_COLUMNS = ColumnSet("reports.freight_brokerage", (
    col("number", "Slip", "link", locked=True, link="inventory:purchase_invoice_detail"),
    col("date", "Date", "date", locked=True),
    col("supplier", "Arhti", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("vehicle", "Vehicle"),
    col("broker", "Broker"),
    col("credit_mund", "Mund", "qty", places=3, total=True),
    col("freight", "Freight", "money", total=True),
    col("freight_payer", "Freight By"),
    col("freight_mill", "Mill Paid", "money", total=True, default=False),
    col("freight_supplier", "Supplier Paid", "money", total=True, default=False),
    col("brokerage_rate", "Brokerage /100kg", "money", default=False),
    col("brokerage", "Brokerage", "money", total=True),
    col("brokerage_bearer", "Brokerage By"),
    col("brokerage_mill", "Mill Bears", "money", total=True, default=False),
    col("brokerage_supplier", "Supplier Bears", "money", total=True, default=False),
))


class FreightBrokerageView(ReportView):
    page = PAGE
    title = "Freight & Brokerage"
    template_name = "reports/generic.html"
    columns = FREIGHT_COLUMNS
    url_name = "inventory:report_freight_brokerage"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in FREIGHT_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (ARHTI, ("broker", "Broker", sel.broker_options))

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.freight_brokerage(p.start, p.end, f["supplier"] or None, f["broker"] or None)
        t = data["totals"]
        tiles = [
            _tile("Freight", format_amount(t["freight"]), "sky", "cash", f"{t['invoices']} slips"),
            _tile("Freight mill paid", format_amount(t["freight_mill"]), "rose", "cash"),
            _tile("Freight supplier paid", format_amount(t["freight_supplier"]), "green", "cash"),
            _tile("Brokerage", format_amount(t["brokerage"]), "violet", "users"),
            _tile("Brokerage mill bears", format_amount(t["brokerage_mill"]), "amber", "users"),
            _tile("Brokerage supplier bears", format_amount(t["brokerage_supplier"]), "teal", "users"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


FreightBrokerageExportView, FreightBrokerageColumnsView = _views(FreightBrokerageView)


# 20 ------------------------------------------------------------------------

WHT_COLUMNS = ColumnSet("reports.wht_register", (
    col("number", "Slip", "link", locked=True, link="inventory:purchase_invoice_detail"),
    col("date", "Date", "date", locked=True),
    col("month", "Month"),
    col("supplier", "Supplier", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("ntn", "NTN"),
    col("cnic", "CNIC / STRN", default=False),
    col("credit_mund", "Mund", "qty", places=3, total=True),
    col("goods_amount", "Goods", "money", total=True),
    col("rate", "WHT / 40kg", "money"),
    col("wht", "WHT Deducted", "money", total=True, locked=True),
))


class WhtRegisterView(ReportView):
    page = PAGE
    title = "Withholding Tax Register"
    template_name = "reports/generic.html"
    columns = WHT_COLUMNS
    url_name = "inventory:report_wht"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in WHT_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (ARHTI,)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.wht_register(p.start, p.end, f["supplier"] or None)
        t = data["totals"]
        tiles = [_tile("WHT deducted", format_amount(t["wht"]), "violet", "shield", f"{t['invoices']} slips · {t['credit_mund']:,.0f} md")]
        for month, amount in list(data["by_month"].items())[:5]:
            tiles.append(_tile(month, format_amount(amount), "slate", "calendar"))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


WhtRegisterExportView, WhtRegisterColumnsView = _views(WhtRegisterView)


# 21 ------------------------------------------------------------------------

STORES_COLUMNS = ColumnSet("reports.stores_register", (
    col("number", "Invoice", "link", locked=True, link="inventory:purchase_invoice_detail"),
    col("date", "Date", "date", locked=True),
    col("supplier", "Supplier", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("supplier_invoice", "Supplier Ref", default=False),
    col("item", "Item", "link", link="inventory:item_detail", link_key="item_id"),
    col("category", "Category"),
    col("uom", "UOM", default=False),
    col("qty", "Qty", "qty", places=3, total=True),
    col("rate", "Rate", "money"),
    col("discount", "Discount", "money", total=True, default=False),
    col("tax", "Tax", "money", total=True, default=False),
    col("amount", "Amount", "money", total=True, locked=True),
    col("po", "PO", "link", link="inventory:purchase_order_detail", link_key="po_pk"),
    col("match", "Match"),
))


class StoresRegisterView(ReportView):
    page = PAGE
    title = "Stores Purchase Register"
    template_name = "reports/generic.html"
    columns = STORES_COLUMNS
    url_name = "inventory:report_stores_purchases"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in STORES_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (SUPPLIER, ("item_class", "Category", sel.class_options), ("item", "Item", sel.item_options))

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.stores_register(p.start, p.end, f["supplier"] or None, f["item_class"] or None, f["item"] or None)
        t = data["totals"]
        against = sum(1 for r in data["rows"] if r["match"] == "Against order")
        tiles = [
            _tile("Invoices", str(t["invoices"]), "slate", "receipt", f"{t['lines']} lines"),
            _tile("Amount", format_amount(t["amount"]), "sky", "cash", f"tax {format_amount(t['tax'])}"),
            _tile("Against order", str(against), "green", "check"),
            _tile("Direct", str(t["lines"] - against), "amber", "file"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


StoresRegisterExportView, StoresRegisterColumnsView = _views(StoresRegisterView)


# 22 ------------------------------------------------------------------------

ORDER_COLUMNS = ColumnSet("reports.order_fulfilment", (
    col("number", "Order", "link", locked=True, link="inventory:purchase_order_detail"),
    col("date", "Date", "date", locked=True),
    col("expected", "Expected", "date"),
    col("supplier", "Supplier", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("lines", "Lines", "int", default=False),
    col("ordered", "Ordered", "qty", places=3, total=True),
    col("invoiced", "Received", "qty", places=3, total=True),
    col("pending", "Pending", "qty", places=3, total=True, locked=True),
    col("fulfilled_pct", "Fulfilled %", "pct"),
    col("value", "Order Value", "money", total=True),
    col("pending_value", "Pending Value", "money", total=True),
    col("age", "Age (days)", "int"),
    col("status", "Status", "status"),
))


class OrderFulfilmentView(ReportView):
    page = PAGE
    title = "Purchase Orders — Pending / Fulfilment"
    template_name = "reports/generic.html"
    columns = ORDER_COLUMNS
    url_name = "inventory:report_pending_orders"
    default_preset = "year"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in ORDER_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (SUPPLIER, ("status", "Status", INV_PURCHASE_ORDER_STATUS_CHOICES))

    def build(self):
        from django.utils import timezone

        p, f = self.period(), self.filters()
        data = sel.order_fulfilment(p.start, p.end, f["supplier"] or None, f["status"], timezone.localdate())
        t = data["totals"]
        base = p.query + (f"&supplier={f['supplier']}" if f["supplier"] else "")
        tiles = [
            _tile("Orders", str(t["orders"]), "slate", "file", href=f"?{base}"),
            _tile("Open", str(t["open"]), "amber", "clock", href=f"?{base}&status=submitted", on=f["status"] == "submitted"),
            _tile("Overdue", str(t["overdue"]), "rose", "alert"),
            _tile("Pending qty", f"{t['pending']:,.0f}", "violet", "box", f"of {t['ordered']:,.0f} ordered"),
            _tile("Pending value", format_amount(t["pending_value"]), "sky", "cash", f"of {format_amount(t['value'])}"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


OrderFulfilmentExportView, OrderFulfilmentColumnsView = _views(OrderFulfilmentView)


# 23 ------------------------------------------------------------------------

PURCHASE_RETURNS_COLUMNS = ColumnSet("reports.purchase_returns", (
    col("number", "Return", "link", locked=True, link="inventory:purchase_return_detail"),
    col("date", "Date", "date", locked=True),
    col("supplier", "Supplier", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("invoice", "Against Invoice", "link", link="inventory:purchase_invoice_detail", link_key="invoice_pk"),
    col("invoice_date", "Invoice Date", "date", default=False),
    col("items", "Items"),
    col("qty", "Qty", "qty", places=3, total=True),
    col("invoice_amount", "Invoice Amount", "money", total=True, default=False),
    col("returned", "Returned", "money", total=True, locked=True),
    col("adjusted", "Adjusted", "money", total=True),
    col("remarks", "Remarks", default=False),
    col("status", "Status", "status"),
))


class PurchaseReturnsView(ReportView):
    page = PAGE
    title = "Purchase Returns"
    template_name = "reports/generic.html"
    columns = PURCHASE_RETURNS_COLUMNS
    url_name = "inventory:report_purchase_return"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in PURCHASE_RETURNS_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (SUPPLIER, ("item", "Item", sel.item_options))

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.purchase_returns(p.start, p.end, f["supplier"] or None, f["item"] or None)
        t = data["totals"]
        tiles = [
            _tile("Returns", str(t["returns"]), "slate", "reverse"),
            _tile("Qty", f"{t['qty']:,.0f}", "teal", "box"),
            _tile("Returned", format_amount(t["returned"]), "rose", "cash"),
            _tile("Adjusted", format_amount(t["adjusted"]), "amber", "cash"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


PurchaseReturnsExportView, PurchaseReturnsColumnsView = _views(PurchaseReturnsView)


# 24 ------------------------------------------------------------------------

PAYMENT_STATUS_COLUMNS = ColumnSet("reports.supplier_payment_status", (
    col("supplier", "Supplier", "link", locked=True, link="inventory:supplier_detail", link_key="supplier_id"),
    col("kind", "Type"),
    col("invoices", "Invoices", "int", total=True),
    col("invoiced", "Invoiced", "money", total=True),
    col("paid", "Paid", "money", total=True),
    col("balance", "Balance", "money", total=True, locked=True),
    col("oldest_unpaid", "Oldest Unpaid", "date"),
    col("days_outstanding", "Days", "int"),
    col("due_in_7", "Due in 7 Days", "int", total=True),
    col("last_invoice", "Last Invoice", "date", default=False),
))


class SupplierPaymentStatusView(ReportView):
    page = PAGE
    title = "Supplier Payment Status"
    template_name = "reports/generic.html"
    columns = PAYMENT_STATUS_COLUMNS
    url_name = "inventory:report_supplier_payments"
    as_of_report = True
    default_sort = "balance"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in PAYMENT_STATUS_COLUMNS.keys}
    filter_specs = (("kind", "Type", (("arhti", "Arhti (wheat)"), ("bardana", "Bardana"), ("stores", "Stores"))),)

    def build(self):
        f = self.filters()
        data = sel.supplier_payment_status(self.as_of(), f["kind"])
        t = data["totals"]
        tiles = [
            _tile("Suppliers", str(t["suppliers"]), "slate", "users"),
            _tile("Invoiced", format_amount(t["invoiced"]), "sky", "receipt"),
            _tile("Paid", format_amount(t["paid"]), "green", "cash"),
            _tile("Balance", format_amount(t["balance"]), "rose", "alert"),
            _tile("Due in 7 days", str(t["due_in_7"]), "amber", "clock"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


SupplierPaymentStatusExportView, SupplierPaymentStatusColumnsView = _views(SupplierPaymentStatusView)
