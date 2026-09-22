"""Stock reporting screens (catalogue group G)."""

from apps.core.formatting import format_amount
from apps.core.reporting import PRESET_MONTH, ReportView
from apps.core.table_columns import ColumnSet, col

from . import selectors_stock as sel
from .report_views import _tile
from .report_views_purchase import _views

PAGE = "reports.stock"
GODOWN = ("godown", "Godown", sel.godown_options)
CLASS = ("item_class", "Category", sel.class_options)
TONES = ("amber", "teal", "sky", "violet", "green", "rose")


# 41 ------------------------------------------------------------------------

MILL_STOCK_COLUMNS = ColumnSet("reports.mill_stock", (
    col("product", "Product", locked=True),
    col("family", "Category"),
    col("unit", "Unit", default=False),
    col("godown", "Godown"),
    col("opening", "Opening", "qty", total=True),
    col("qty_in", "In", "qty", total=True),
    col("qty_out", "Out", "qty", total=True),
    col("closing", "Closing", "qty", total=True, locked=True),
    col("closing_kg", "Closing Kg", "qty", places=3, total=True),
    col("closing_mund", "Mund", "qty", places=3, total=True, default=False),
    col("rate", "Rate", "money"),
    col("value", "Value", "money", total=True),
))


class MillStockView(ReportView):
    page = PAGE
    title = "Mill Product Stock"
    template_name = "reports/generic.html"
    columns = MILL_STOCK_COLUMNS
    url_name = "inventory:report_mill_stock"
    default_sort = "product"
    sort_fields = {k: k for k in MILL_STOCK_COLUMNS.keys}
    filter_specs = (("family", "Category", sel.family_options), ("product", "Product", sel.product_options), GODOWN)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.mill_stock(p.start, p.end, f["product"] or None, f["godown"] or None, f["family"] or None)
        t = data["totals"]
        tiles = [_tile("Stock value", format_amount(t["value"]), "slate", "cash", f"{t['closing_kg']:,.0f} kg")]
        for index, (family, figures) in enumerate(sorted(data["families"].items(), key=lambda x: -x[1]["closing_kg"])[:5]):
            tiles.append(_tile(family, f"{figures['closing_kg']:,.0f} kg", TONES[index], "box", f"Rs {format_amount(figures['value'])}"))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


MillStockExportView, MillStockColumnsView = _views(MillStockView)


# 42 ------------------------------------------------------------------------

STORES_STOCK_COLUMNS = ColumnSet("reports.stores_stock", (
    col("code", "Code", default=False),
    col("item", "Item", "link", locked=True, link="inventory:item_detail", link_key="item_id"),
    col("category", "Category"),
    col("uom", "UOM", default=False),
    col("opening", "Opening", "qty", places=3, total=True),
    col("qty_in", "In", "qty", places=3, total=True),
    col("qty_out", "Out", "qty", places=3, total=True),
    col("closing", "Closing", "qty", places=3, total=True, locked=True, tone_key="negative"),
    col("on_hand", "On Hand Now", "qty", places=3, total=True, default=False),
    col("rate", "Rate", "money"),
    col("value", "Value", "money", total=True),
    col("last_movement", "Last Movement", "date"),
    col("idle_days", "Idle Days", "int"),
))


class StoresStockView(ReportView):
    page = PAGE
    title = "Stores Stock"
    template_name = "reports/generic.html"
    columns = STORES_STOCK_COLUMNS
    url_name = "inventory:report_stores_stock"
    default_sort = "item"
    sort_fields = {k: k for k in STORES_STOCK_COLUMNS.keys}
    filter_specs = (CLASS, ("negative", "Show", (("1", "Negative stock only"),)))

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.stores_stock(p.start, p.end, f["item_class"] or None, f["negative"] == "1")
        t = data["totals"]
        tiles = [
            _tile("Items", str(t["items"]), "slate", "box"),
            _tile("Closing value", format_amount(t["value"]), "sky", "cash"),
            _tile("In", f"{t['qty_in']:,.0f}", "green", "plus"),
            _tile("Out", f"{t['qty_out']:,.0f}", "rose", "minus"),
            _tile("Negative stock", str(t["negative"]), "amber" if t["negative"] else "green", "alert", href=f"?{p.query}&negative=1", on=f["negative"] == "1"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


StoresStockExportView, StoresStockColumnsView = _views(StoresStockView)


# 44 ------------------------------------------------------------------------

SLOW_COLUMNS = ColumnSet("reports.slow_moving", (
    col("book", "Book"),
    col("item", "Item", locked=True),
    col("category", "Category"),
    col("on_hand", "On Hand", "qty", places=3),
    col("rate", "Rate", "money"),
    col("value", "Value", "money", total=True, locked=True),
    col("last_movement", "Last Movement", "date"),
    col("idle_days", "Idle Days", "int"),
    col("bucket", "Bucket"),
))


class SlowMovingView(ReportView):
    page = PAGE
    title = "Stock Ageing / Slow Moving"
    template_name = "reports/generic.html"
    columns = SLOW_COLUMNS
    url_name = "inventory:report_slow_moving"
    as_of_report = True
    default_sort = "idle_days"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in SLOW_COLUMNS.keys}
    filter_specs = (("book", "Book", (("stores", "Stores"), ("mill", "Mill products"))), CLASS)

    def build(self):
        f = self.filters()
        data = sel.slow_moving(self.as_of(), f["book"], f["item_class"] or None)
        t = data["totals"]
        tiles = [
            _tile("Idle items", str(t["items"]), "slate", "clock", f"Rs {format_amount(t['value'])}"),
            _tile("30–59 days", format_amount(t["30-59"]), "amber", "clock"),
            _tile("60–89 days", format_amount(t["60-89"]), "rose", "clock"),
            _tile("90+ days", format_amount(t["90+"]), "violet", "alert"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


SlowMovingExportView, SlowMovingColumnsView = _views(SlowMovingView)


# 45 ------------------------------------------------------------------------

ADJUSTMENT_COLUMNS = ColumnSet("reports.stock_adjustments", (
    col("date", "Date", "date", locked=True),
    col("transaction", "Transaction"),
    col("item", "Item", "link", locked=True, link="inventory:item_detail", link_key="item_id"),
    col("qty_in", "Qty +", "qty", places=3, total=True),
    col("qty_out", "Qty −", "qty", places=3, total=True),
    col("rate", "Rate", "money"),
    col("value", "Value", "money", total=True),
    col("reason", "Reason"),
    col("supplier", "Supplier", default=False),
    col("user", "User"),
    col("status", "Status", "status"),
))


class AdjustmentRegisterView(ReportView):
    page = PAGE
    title = "Stock Adjustment Register"
    template_name = "reports/generic.html"
    columns = ADJUSTMENT_COLUMNS
    url_name = "inventory:report_stock_adjustments"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in ADJUSTMENT_COLUMNS.keys}
    filter_specs = (("item", "Item", sel.adjusted_item_options), ("user", "User", sel.adjusting_user_options))

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.adjustment_register(p.start, p.end, f["item"] or None, f["user"] or None)
        t = data["totals"]
        tiles = [
            _tile("Adjustments", str(t["entries"]), "slate", "edit"),
            _tile("Added", f"{t['qty_in']:,.0f}", "green", "plus"),
            _tile("Removed", f"{t['qty_out']:,.0f}", "rose", "minus"),
            _tile("Value", format_amount(t["value"]), "sky", "cash"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


AdjustmentRegisterExportView, AdjustmentRegisterColumnsView = _views(AdjustmentRegisterView)


# 46 ------------------------------------------------------------------------

GODOWN_COLUMNS = ColumnSet("reports.godown_stock", (
    col("godown", "Godown", locked=True),
    col("wheat_kg", "Wheat Kg", "qty", places=3, total=True),
    col("wheat_mund", "Wheat Mund", "qty", places=3, total=True),
    col("families", "Products"),
    col("products_kg", "Products Kg", "qty", places=3, total=True),
    col("empty_bags", "Empty Bags", "qty", total=True),
    col("value", "Value", "money", total=True, locked=True),
))


class GodownStockView(ReportView):
    page = PAGE
    title = "Godown-wise Stock"
    template_name = "reports/generic.html"
    columns = GODOWN_COLUMNS
    url_name = "inventory:report_godown_stock"
    as_of_report = True
    default_sort = "godown"
    sort_fields = {k: k for k in GODOWN_COLUMNS.keys}

    def build(self):
        data = sel.godown_stock(self.as_of())
        t = data["totals"]
        tiles = [
            _tile("Wheat", f"{t['wheat_mund']:,.0f} md", "amber", "wheat", f"{t['wheat_kg']:,.0f} kg"),
            _tile("Products", f"{t['products_kg']:,.0f} kg", "teal", "box"),
            _tile("Empty bags", f"{t['empty_bags']:,.0f}", "violet", "layers"),
            _tile("Mill stock value", format_amount(t["value"]), "sky", "cash"),
            _tile("Stores value", format_amount(t["stores_value"]), "slate", "cash", "all godowns"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


GodownStockExportView, GodownStockColumnsView = _views(GodownStockView)


# 47 ------------------------------------------------------------------------

WHEAT_DAYS_COLUMNS = ColumnSet("reports.wheat_days", (
    col("date", "Date", "date", locked=True),
    col("stock_kg", "Wheat Stock Kg", "qty", places=3),
    col("stock_mund", "Mund", "qty", places=3),
    col("ground_kg", "Ground That Day", "qty", places=3),
    col("per_day_kg", "Avg Daily Grinding (30d)", "qty", places=3),
    col("days", "Days of Stock", "qty", places=1, locked=True),
))


class WheatDaysView(ReportView):
    page = PAGE
    title = "Wheat Stock in Days"
    template_name = "reports/generic.html"
    columns = WHEAT_DAYS_COLUMNS
    url_name = "inventory:report_wheat_days"
    as_of_report = True
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in WHEAT_DAYS_COLUMNS.keys}

    def build(self):
        data = sel.wheat_days_trend(self.as_of())
        latest, first = data["latest"], data["first"]
        from apps.core.reporting import delta

        tiles = [
            _tile("Wheat stock in days", f"{latest['days']}" if latest["days"] is not None else "—", "amber", "wheat", f"{latest['stock_mund']:,.0f} md on hand", change=delta(latest["days"], first["days"]) if latest["days"] is not None and first["days"] is not None else None),
            _tile("Wheat stock", f"{latest['stock_kg']:,.0f} kg", "teal", "layers"),
            _tile("Avg daily grinding", f"{latest['per_day_kg']:,.0f} kg", "violet", "settings", "last 30 days"),
        ]
        tiles[0]["delta_label"] = "vs 30 days ago"
        return {"rows": data["rows"], "totals": {}, "tiles": tiles}


WheatDaysExportView, WheatDaysColumnsView = _views(WheatDaysView)
