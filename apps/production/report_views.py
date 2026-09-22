"""Production reporting screens (catalogue group F)."""

from decimal import Decimal

from apps.core.formatting import format_amount
from apps.core.reporting import GROUP_MONTH, GROUP_WEEK, PRESET_MONTH, PRESET_YEAR, ReportView
from apps.core.table_columns import ColumnSet, col
from apps.inventory.report_views import _tile
from apps.inventory.report_views_purchase import _views

from . import report_selectors as sel

PAGE = "production.reports"
GODOWN = ("godown", "Godown", sel.godown_options)


def _decimal(raw):
    try:
        return Decimal(raw)
    except Exception:
        return None


# 33 ------------------------------------------------------------------------

GRINDING_COLUMNS = ColumnSet("reports.grinding_register", (
    col("number", "Voucher", "link", locked=True, link="production:grinding_detail"),
    col("date", "Date", "date", locked=True),
    col("shift", "From–To"),
    col("wheat", "Wheat"),
    col("godown", "Godown", default=False),
    col("wheat_kg", "Wheat Kg", "qty", places=3, total=True),
    col("wheat_mund", "Mund", "qty", places=3, total=True, default=False),
    col("bags_issued", "Bags Issued", "qty", total=True, default=False),
    col("outputs", "Output by Product"),
    col("output_kg", "Output Kg", "qty", places=3, total=True, locked=True),
    col("yield_pct", "Yield %", "pct", total=True, tone_key="below"),
    col("standard_pct", "Standard %", "pct"),
    col("shortage_kg", "Shortage Kg", "qty", places=3, total=True),
    col("shortage_pct", "Shortage %", "pct", total=True),
    col("prepared_by", "Prepared By"),
))


class GrindingRegisterView(ReportView):
    page = PAGE
    title = "Grinding Register"
    template_name = "reports/generic.html"
    columns = GRINDING_COLUMNS
    url_name = "production:report_grinding_register"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in GRINDING_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (GODOWN, ("prepared_by", "Prepared By", sel.preparer_options))

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.grinding_register(p.start, p.end, f["godown"] or None, f["prepared_by"] or None)
        t = data["totals"]
        tiles = [
            _tile("Vouchers", str(t["vouchers"]), "slate", "receipt"),
            _tile("Wheat ground", f"{t['wheat_mund']:,.0f} md", "amber", "wheat", f"{t['wheat_kg']:,.0f} kg"),
            _tile("Output", f"{t['output_kg']:,.0f} kg", "teal", "box"),
            _tile("Avg yield", f"{t['yield_pct']}%", "green" if t["below"] == 0 else "rose", "chart", f"{t['below']} below standard"),
            _tile("Shortage", f"{t['shortage_kg']:,.0f} kg", "violet", "minus", f"{t['shortage_pct']}%"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


GrindingRegisterExportView, GrindingRegisterColumnsView = _views(GrindingRegisterView)


# 34 ------------------------------------------------------------------------

DAILY_COLUMNS = ColumnSet("reports.daily_grinding", (
    col("date", "Date", "date", locked=True),
    col("day", "Day"),
    col("runs", "Runs", "int", total=True),
    col("wheat_kg", "Wheat Kg", "qty", places=3, total=True),
    col("wheat_mund", "Mund", "qty", places=3, total=True, default=False),
    col("outputs", "Output by Product"),
    col("output_kg", "Output Kg", "qty", places=3, total=True, locked=True),
    col("yield_pct", "Yield %", "pct", total=True),
    col("shortage_kg", "Shortage Kg", "qty", places=3, total=True),
))


class DailyGrindingView(ReportView):
    page = PAGE
    title = "Daily Grinding"
    template_name = "reports/generic.html"
    columns = DAILY_COLUMNS
    url_name = "production:report_daily_grinding"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in DAILY_COLUMNS.keys}
    filter_specs = (GODOWN,)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.daily_grinding(p.start, p.end, f["godown"] or None)
        t = data["totals"]
        for row in data["rows"]:
            row["status"] = "reversed" if row["downtime"] else "posted"
            row["status_label"] = "No grinding" if row["downtime"] else "Ran"
        tiles = [
            _tile("Days", str(t["days"]), "slate", "calendar", f"{t['runs']} runs"),
            _tile("Downtime days", str(t["downtime_days"]), "rose" if t["downtime_days"] else "green", "alert"),
            _tile("Wheat ground", f"{t['wheat_mund']:,.0f} md", "amber", "wheat", f"{t['wheat_kg']:,.0f} kg"),
            _tile("Output", f"{t['output_kg']:,.0f} kg", "teal", "box"),
            _tile("Yield", f"{t['yield_pct'] or 0}%", "violet", "chart"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


DailyGrindingExportView, DailyGrindingColumnsView = _views(DailyGrindingView)


# 35 ------------------------------------------------------------------------

YIELD_COLUMNS = ColumnSet("reports.yield_trend", (
    col("label", "Period", locked=True),
    col("runs", "Runs", "int", total=True),
    col("wheat_kg", "Wheat Kg", "qty", places=3, total=True),
    col("output_kg", "Output Kg", "qty", places=3, total=True),
    col("yield_pct", "Yield %", "pct", total=True, locked=True, tone_key="below"),
    col("standard_pct", "Standard %", "pct"),
    col("variance_pct", "Variance", "pct"),
    col("moving_avg", "Moving Avg %", "pct"),
))


class YieldTrendView(ReportView):
    page = PAGE
    title = "Yield Trend"
    template_name = "reports/generic.html"
    columns = YIELD_COLUMNS
    url_name = "production:report_yield_trend"
    group_toggle = True
    default_group = GROUP_WEEK
    default_preset = PRESET_YEAR
    default_sort = "label"
    sort_fields = {k: k for k in YIELD_COLUMNS.keys} | {"label": "period"}

    def build(self):
        p = self.period()
        data = sel.yield_trend(p.start, p.end, self.group())
        t = data["totals"]
        tiles = [
            _tile("Avg yield", f"{t['yield_pct'] or 0}%", "violet", "chart", f"{t['runs']} runs"),
            _tile("Best day", f"{data['best'][1]}%" if data["best"] else "—", "green", "sort-up", f"{data['best'][0]:%d %b %Y}" if data["best"] else ""),
            _tile("Worst day", f"{data['worst'][1]}%" if data["worst"] else "—", "rose", "sort-down", f"{data['worst'][0]:%d %b %Y}" if data["worst"] else ""),
            _tile("Below standard", str(sum(1 for r in data["rows"] if r["below"])), "amber", "alert", "periods"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


YieldTrendExportView, YieldTrendColumnsView = _views(YieldTrendView)


# 36 ------------------------------------------------------------------------

MIX_COLUMNS = ColumnSet("reports.output_mix", (
    col("product", "Product", locked=True),
    col("family", "Category"),
    col("runs", "Runs", "int", default=False),
    col("units", "Units", "qty", total=True),
    col("kg", "Kg", "qty", places=3, total=True, locked=True),
    col("share_pct", "Share of Output %", "pct", total=True),
    col("of_wheat_pct", "Of Wheat %", "pct", total=True),
    col("target_pct", "Target %", "pct"),
    col("variance_pct", "Variance", "pct"),
))


class OutputMixView(ReportView):
    page = PAGE
    title = "Product Output Mix"
    template_name = "reports/generic.html"
    columns = MIX_COLUMNS
    url_name = "production:report_output_mix"
    default_sort = "kg"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in MIX_COLUMNS.keys}
    filter_specs = (GODOWN,)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.output_mix(p.start, p.end, f["godown"] or None)
        t = data["totals"]
        tiles = [_tile("Wheat in", f"{t['wheat_kg']:,.0f} kg", "amber", "wheat"), _tile("Output", f"{t['kg']:,.0f} kg", "teal", "box", f"{t['of_wheat_pct'] or 0}% of wheat")]
        for index, row in enumerate(data["rows"][:4]):
            tiles.append(_tile(row["product"], f"{row['share_pct']}%", ("sky", "violet", "green", "rose")[index], "box", f"{row['kg']:,.0f} kg"))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


OutputMixExportView, OutputMixColumnsView = _views(OutputMixView)


# 37 ------------------------------------------------------------------------

SHORTAGE_COLUMNS = ColumnSet("reports.shortage", (
    col("number", "Voucher", "link", locked=True, link="production:grinding_detail"),
    col("date", "Date", "date", locked=True),
    col("wheat", "Wheat", default=False),
    col("wheat_kg", "Wheat Kg", "qty", places=3, total=True),
    col("output_kg", "Output Kg", "qty", places=3, total=True),
    col("shortage_kg", "Shortage Kg", "qty", places=3, total=True, locked=True),
    col("shortage_pct", "Shortage %", "pct", total=True),
    col("standard_shortage_kg", "Standard Kg", "qty", places=3, total=True),
    col("excess_kg", "Beyond Standard", "qty", places=3, total=True, tone_key="beyond"),
    col("cost", "Cost of Shortage", "money", total=True),
    col("excess_cost", "Cost Beyond Standard", "money", total=True),
    col("prepared_by", "Prepared By", default=False),
))


class ShortageReportView(ReportView):
    page = PAGE
    title = "Shortage / Refraction"
    template_name = "reports/threshold.html"
    columns = SHORTAGE_COLUMNS
    url_name = "production:report_shortage"
    default_sort = "excess_kg"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in SHORTAGE_COLUMNS.keys} | {"number": "pk"}
    threshold_label = "Shortage ≥ %"

    def threshold(self):
        return _decimal(self.request.GET.get("threshold") or "")

    def build(self):
        p = self.period()
        data = sel.shortage_report(p.start, p.end, self.threshold())
        t = data["totals"]
        tiles = [
            _tile("Vouchers", str(t["vouchers"]), "slate", "receipt", f"{t['beyond']} beyond standard"),
            _tile("Shortage", f"{t['shortage_kg']:,.0f} kg", "amber", "minus", f"{t['shortage_pct'] or 0}%"),
            _tile("Beyond standard", f"{t['excess_kg']:,.0f} kg", "rose", "alert"),
            _tile("Cost", format_amount(t["cost"]), "violet", "cash", f"@ {format_amount(t['rate'])}/kg wheat"),
            _tile("Cost beyond standard", format_amount(t["excess_cost"]), "sky", "cash"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles, "extra": {"threshold": self.threshold(), "threshold_label": self.threshold_label}}


ShortageReportExportView, ShortageReportColumnsView = _views(ShortageReportView)


# 38 ------------------------------------------------------------------------

CONVERSION_COLUMNS = ColumnSet("reports.conversions", (
    col("number", "Voucher", "link", locked=True, link="production:conversion_detail"),
    col("date", "Date", "date", locked=True),
    col("from_product", "From"),
    col("from_units", "From Units", "qty", total=True),
    col("from_kg", "From Kg", "qty", places=3, total=True),
    col("to_products", "To"),
    col("to_units", "To Units", "qty", total=True),
    col("to_kg", "To Kg", "qty", places=3, total=True, locked=True),
    col("variance_kg", "Variance Kg", "qty", places=3, total=True),
    col("godown", "Godown", default=False),
    col("prepared_by", "Prepared By", default=False),
))


class ConversionRegisterView(ReportView):
    page = PAGE
    title = "Product Conversion Register"
    template_name = "reports/generic.html"
    columns = CONVERSION_COLUMNS
    url_name = "production:report_conversions"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in CONVERSION_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (("product", "Product", sel.conversion_product_options), GODOWN)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.conversion_register(p.start, p.end, f["product"] or None, f["godown"] or None)
        t = data["totals"]
        tiles = [
            _tile("Conversions", str(t["conversions"]), "slate", "refresh"),
            _tile("From", f"{t['from_kg']:,.0f} kg", "amber", "box", f"{t['from_units']:,.0f} units"),
            _tile("To", f"{t['to_kg']:,.0f} kg", "teal", "box", f"{t['to_units']:,.0f} units"),
            _tile("Variance", f"{t['variance_kg']:,.0f} kg", "rose" if t["variance_kg"] else "green", "alert"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


ConversionRegisterExportView, ConversionRegisterColumnsView = _views(ConversionRegisterView)


# 39 ------------------------------------------------------------------------

COST_COLUMNS = ColumnSet("reports.cost_per_bag", (
    col("product", "Product", locked=True),
    col("family", "Category"),
    col("units", "Bags Produced", "qty", total=True),
    col("kg", "Kg", "qty", places=3, total=True, default=False),
    col("share_pct", "Share %", "pct"),
    col("wheat_cost", "Wheat Cost", "money", total=True),
    col("bardana_cost", "Bardana Cost", "money", total=True),
    col("expense_cost", "Direct Expenses", "money", total=True),
    col("total_cost", "Total Cost", "money", total=True, locked=True),
    col("cost_per_bag", "Cost / Bag", "money", total=True, locked=True),
    col("cost_per_kg", "Cost / Kg", "money", total=True),
))


class CostPerBagView(ReportView):
    page = PAGE
    title = "Production Cost per Bag"
    template_name = "reports/generic.html"
    columns = COST_COLUMNS
    url_name = "production:report_cost_per_bag"
    default_preset = PRESET_MONTH
    default_sort = "total_cost"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in COST_COLUMNS.keys}

    def build(self):
        p = self.period()
        data = sel.cost_per_bag(p.start, p.end)
        t = data["totals"]
        tiles = [
            _tile("Wheat cost", format_amount(t["wheat_cost"]), "amber", "wheat", f"{t['wheat_kg']:,.0f} kg @ {format_amount(t['wheat_rate'])}"),
            _tile("Bardana cost", format_amount(t["bardana_cost"]), "teal", "box", f"@ {format_amount(t['bag_rate'])}/bag"),
            _tile("Direct expenses", format_amount(t["expense_cost"]), "violet", "cash", f"{t['expense_accounts']} linked accounts"),
            _tile("Total cost", format_amount(t["total_cost"]), "sky", "sum"),
            _tile("Cost / bag", format_amount(t["cost_per_bag"]), "green", "receipt", f"{format_amount(t['cost_per_kg'])}/kg"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


CostPerBagExportView, CostPerBagColumnsView = _views(CostPerBagView)


# 40 ------------------------------------------------------------------------

SUMMARY_COLUMNS = ColumnSet("reports.production_summary", (
    col("label", "Period", locked=True),
    col("days", "Days Run", "int", total=True),
    col("runs", "Runs", "int", total=True),
    col("wheat_kg", "Wheat Kg", "qty", places=3, total=True),
    col("wheat_mund", "Mund", "qty", places=3, total=True),
    col("per_day_kg", "Kg / Day", "qty"),
    col("bags_issued", "Bags Issued", "qty", total=True, default=False),
    col("families", "Output by Category"),
    col("output_kg", "Output Kg", "qty", places=3, total=True, locked=True),
    col("yield_pct", "Yield %", "pct", total=True),
    col("shortage_kg", "Shortage Kg", "qty", places=3, total=True),
    col("shortage_pct", "Shortage %", "pct", total=True),
))


class ProductionSummaryView(ReportView):
    page = PAGE
    title = "Production Summary"
    template_name = "reports/generic.html"
    columns = SUMMARY_COLUMNS
    url_name = "production:report_production_summary"
    group_toggle = True
    default_group = GROUP_MONTH
    default_preset = PRESET_YEAR
    default_sort = "label"
    sort_fields = {k: k for k in SUMMARY_COLUMNS.keys} | {"label": "period"}
    filter_specs = (GODOWN,)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.production_summary(p.start, p.end, self.group(), f["godown"] or None)
        t = data["totals"]
        tiles = [
            _tile("Days run", str(t["days"]), "slate", "calendar", f"{t['runs']} runs"),
            _tile("Wheat ground", f"{t['wheat_mund']:,.0f} md", "amber", "wheat", f"{t['wheat_kg']:,.0f} kg"),
            _tile("Output", f"{t['output_kg']:,.0f} kg", "teal", "box"),
            _tile("Yield", f"{t['yield_pct'] or 0}%", "violet", "chart"),
            _tile("Shortage", f"{t['shortage_kg']:,.0f} kg", "rose", "minus", f"{t['shortage_pct'] or 0}%"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


ProductionSummaryExportView, ProductionSummaryColumnsView = _views(ProductionSummaryView)
