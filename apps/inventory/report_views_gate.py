"""Weighbridge / gate reporting screens (catalogue group D)."""

from decimal import Decimal

from apps.core.formatting import format_amount
from apps.core.reporting import PRESET_TODAY, ReportView
from apps.core.table_columns import ColumnSet, col

from . import selectors_purchase as sel
from .report_views import _tile
from .report_views_purchase import ARHTI, _views

PAGE = "reports.weighbridge"
VEHICLE = ("vehicle", "Vehicle", sel.vehicle_options)


def _decimal(raw):
    try:
        return Decimal(raw)
    except Exception:
        return None


WEIGHBRIDGE_COLUMNS = ColumnSet("reports.weighbridge", (
    col("number", "Slip", "link", locked=True, link="inventory:purchase_invoice_detail"),
    col("date", "Date", "date", locked=True),
    col("time", "Time", "time"),
    col("vehicle", "Vehicle"),
    col("party", "Party", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("direction", "Direction"),
    col("product", "Product", default=False),
    col("party_gross", "Party Gross", "qty", places=3, default=False),
    col("party_tare", "Party Tare", "qty", places=3, default=False),
    col("mill_gross", "Mill Gross", "qty", places=3),
    col("mill_tare", "Mill Tare", "qty", places=3),
    col("party_weight", "Party Net", "qty", places=3, total=True),
    col("mill_weight", "Mill Net", "qty", places=3, total=True),
    col("difference", "Difference", "qty", places=3, total=True, locked=True),
    col("difference_pct", "Diff %", "pct", default=False),
    col("selected_weight", "Selected", "qty", places=3),
    col("weight_source", "Source"),
    col("katla", "Katla", "qty", places=3, default=False),
    col("credit_kg", "Credit Kg", "qty", places=3, total=True),
    col("posted_by", "Clerk", default=False),
))


class WeighbridgeRegisterView(ReportView):
    page = PAGE
    title = "Weighbridge Register"
    template_name = "reports/weighbridge_register.html"
    columns = WEIGHBRIDGE_COLUMNS
    url_name = "inventory:report_weighbridge"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in WEIGHBRIDGE_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (VEHICLE, ARHTI, ("direction", "Direction", (("in", "In (wheat)"), ("out", "Out (dispatch)"))))

    def min_difference(self):
        return _decimal(self.request.GET.get("min_difference") or "")

    def build(self):
        p, f = self.period(), self.filters()
        if f["direction"] == "out":
            data = {"rows": [], "totals": {"slips": 0, "vehicles": 0, "party_weight": Decimal("0"), "mill_weight": Decimal("0"), "difference": Decimal("0"), "credit_kg": Decimal("0"), "avg_difference": Decimal("0"), "cost_impact": Decimal("0")}}
        else:
            data = sel.weighbridge_register(p.start, p.end, f["vehicle"], f["supplier"] or None, self.min_difference())
        t = data["totals"]
        tiles = [
            _tile("Vehicles", str(t["vehicles"]), "slate", "users", f"{t['slips']} weighments"),
            _tile("In (kg)", f"{t['credit_kg']:,.0f}", "amber", "wheat", f"{t['credit_kg'] / 40:,.0f} md"),
            _tile("Out (kg)", "0", "teal", "box", "no outbound weighing"),
            _tile("Avg difference", f"{t['avg_difference']:,.3f} kg", "rose" if t["avg_difference"] < 0 else "green", "chart", "mill − party"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles, "extra": {"min_difference": self.min_difference()}}

    def filter_summary(self):
        base = super().filter_summary()
        if self.min_difference() is not None:
            base = " · ".join(part for part in (base, f"Difference ≥ {self.min_difference()} kg") if part)
        return base


WeighbridgeRegisterExportView, WeighbridgeRegisterColumnsView = _views(WeighbridgeRegisterView)


VEHICLE_COLUMNS = ColumnSet("reports.vehicles", (
    col("vehicle", "Vehicle", locked=True),
    col("trips", "Trips", "int", total=True),
    col("net_kg", "Net Kg", "qty", places=3, total=True, locked=True),
    col("net_mund", "Mund", "qty", places=3, total=True),
    col("avg_difference", "Avg Difference", "qty", places=3),
    col("parties", "Parties"),
    col("last_visit", "Last Visit", "date"),
))


class VehicleReportView(ReportView):
    page = PAGE
    title = "Vehicle-wise Report"
    template_name = "reports/generic.html"
    columns = VEHICLE_COLUMNS
    url_name = "inventory:report_vehicles"
    default_sort = "net_kg"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in VEHICLE_COLUMNS.keys}
    filter_specs = (VEHICLE,)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.vehicle_report(p.start, p.end, f["vehicle"])
        t = data["totals"]
        tiles = [
            _tile("Vehicles", str(t["vehicles"]), "slate", "users"),
            _tile("Trips", str(t["trips"]), "sky", "receipt"),
            _tile("Net weight", f"{t['net_mund']:,.0f} md", "amber", "wheat", f"{t['net_kg']:,.0f} kg"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


VehicleReportExportView, VehicleReportColumnsView = _views(VehicleReportView)


VARIANCE_COLUMNS = ColumnSet("reports.weight_variance", (
    col("number", "Slip", "link", locked=True, link="inventory:purchase_invoice_detail"),
    col("date", "Date", "date", locked=True),
    col("vehicle", "Vehicle"),
    col("party", "Arhti", "link", link="inventory:supplier_detail", link_key="supplier_id"),
    col("party_weight", "Party Net", "qty", places=3, total=True),
    col("mill_weight", "Mill Net", "qty", places=3, total=True),
    col("difference", "Difference Kg", "qty", places=3, total=True, locked=True),
    col("difference_pct", "Diff %", "pct"),
    col("weight_source", "Selected"),
    col("rate_per_mund", "Rate/Mund", "money"),
    col("cost_impact", "Cost Impact", "money", total=True),
    col("posted_by", "Clerk"),
))


class WeightVarianceView(ReportView):
    page = PAGE
    title = "Weight Variance"
    template_name = "reports/weighbridge_register.html"
    columns = VARIANCE_COLUMNS
    url_name = "inventory:report_weight_variance"
    default_sort = "difference"
    sort_fields = {k: k for k in VARIANCE_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (ARHTI,)

    def tolerance(self):
        return _decimal(self.request.GET.get("min_difference") or "") or Decimal("10")

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.weighbridge_register(p.start, p.end, "", f["supplier"] or None, self.tolerance())
        t = data["totals"]
        party = sum(1 for r in data["rows"] if r["weight_source"] == "Party")
        tiles = [
            _tile("Beyond tolerance", str(t["slips"]), "rose", "alert", f"± {self.tolerance()} kg"),
            _tile("Net difference", f"{t['difference']:,.3f} kg", "amber", "chart", "mill − party"),
            _tile("Party weight taken", str(party), "violet", "users", f"mill weight taken {t['slips'] - party}"),
            _tile("Cost impact", format_amount(t["cost_impact"]), "sky", "cash", "difference × rate"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles, "extra": {"min_difference": self.tolerance()}}

    def filter_summary(self):
        base = super().filter_summary()
        return " · ".join(part for part in (base, f"Tolerance {self.tolerance()} kg") if part)


WeightVarianceExportView, WeightVarianceColumnsView = _views(WeightVarianceView)


GATE_COLUMNS = ColumnSet("reports.gate_sheet", (
    col("time", "Time", "time", locked=True),
    col("number", "Slip", "link", locked=True, link="inventory:purchase_invoice_detail"),
    col("vehicle", "Vehicle"),
    col("party", "Party"),
    col("direction", "Direction"),
    col("product", "Product"),
    col("mill_gross", "Gross", "qty", places=3),
    col("mill_tare", "Tare", "qty", places=3),
    col("mill_weight", "Net", "qty", places=3, total=True, locked=True),
    col("credit_kg", "Credit Kg", "qty", places=3, total=True),
    col("posted_by", "Clerk"),
))


class GateSheetView(ReportView):
    page = PAGE
    title = "Daily Gate Sheet"
    template_name = "reports/generic.html"
    columns = GATE_COLUMNS
    url_name = "inventory:report_gate_sheet"
    default_preset = PRESET_TODAY
    default_sort = "time"
    sort_fields = {"time": "time", "number": "pk", "vehicle": "vehicle", "party": "party", "mill_weight": "mill_weight", "credit_kg": "credit_kg"}
    landscape = False

    def build(self):
        p = self.period()
        data = sel.gate_sheet(p.start, p.end)
        t = data["totals"]
        tiles = [
            _tile("Vehicles in", str(t["vehicles"]), "slate", "users", f"{t['slips']} slips"),
            _tile("Wheat in", f"{t['credit_kg'] / 40:,.0f} md", "amber", "wheat", f"{t['credit_kg']:,.0f} kg"),
            _tile("Vehicles out", "0", "teal", "box", "no outbound weighing"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}

    def sorted_rows(self):
        return list(self.data()["rows"]), {"sort_key": "time", "sort_dir": "asc", "sort_base_query": ""}


GateSheetExportView, GateSheetColumnsView = _views(GateSheetView)
