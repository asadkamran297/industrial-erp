"""Bardana reporting screens (catalogue group E)."""

from apps.core.constants import INV_BARDANA_OWNERSHIP_CHOICES
from apps.core.reporting import ReportView
from apps.core.table_columns import ColumnSet, col
from apps.inventory.report_views import _tile
from apps.inventory.report_views_purchase import _views

from . import report_selectors as sel

PAGE = "reports.bardana"
ITEM = ("item", "Sack / Bag", sel.bardana_item_options)
GODOWN = ("godown", "Godown", sel.godown_options)
PARTY = ("party", "Party", sel.party_options)


BARDANA_STOCK_COLUMNS = ColumnSet("reports.bardana_stock", (
    col("item", "Sack / Bag", locked=True),
    col("kind", "Kind"),
    col("godown", "Godown"),
    col("opening", "Opening", "qty", total=True),
    col("purchased", "Purchased", "qty", total=True),
    col("returned_in", "Returned by Party", "qty", total=True),
    col("other_in", "Other In", "qty", total=True, default=False),
    col("total_in", "In", "qty", total=True),
    col("packed", "Issued to Packing", "qty", total=True),
    col("returned_out", "Returned to Party", "qty", total=True),
    col("other_out", "Other Out", "qty", total=True, default=False),
    col("total_out", "Out", "qty", total=True),
    col("closing", "Closing", "qty", total=True, locked=True),
))


class BardanaStockView(ReportView):
    page = PAGE
    title = "Bardana Stock (Mill)"
    template_name = "reports/generic.html"
    columns = BARDANA_STOCK_COLUMNS
    url_name = "products:report_bardana_stock"
    default_sort = "item"
    sort_fields = {k: k for k in BARDANA_STOCK_COLUMNS.keys}
    filter_specs = (ITEM, GODOWN)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.bardana_stock(p.start, p.end, f["item"] or None, f["godown"] or None)
        t = data["totals"]
        tiles = [
            _tile("Opening", f"{t['opening']:,.0f}", "slate", "box"),
            _tile("In", f"{t['total_in']:,.0f}", "green", "plus", f"purchased {t['purchased']:,.0f}"),
            _tile("Out", f"{t['total_out']:,.0f}", "rose", "minus", f"packing {t['packed']:,.0f}"),
            _tile("Closing", f"{t['closing']:,.0f}", "amber", "layers"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


BardanaStockExportView, BardanaStockColumnsView = _views(BardanaStockView)


PARTY_BALANCE_COLUMNS = ColumnSet("reports.party_bardana", (
    col("party", "Party", "link", locked=True, link="inventory:supplier_detail", link_key="party_id"),
    col("item", "Sack"),
    col("ownership", "Ownership"),
    col("received", "Received", "qty", total=True),
    col("returned", "Returned", "qty", total=True),
    col("held", "Held by Mill", "qty", total=True, locked=True),
    col("returnable", "Returnable Due", "qty", total=True),
    col("entries", "Entries", "int", default=False),
    col("last_movement", "Last Movement", "date"),
))


class PartyBardanaBalancesView(ReportView):
    page = PAGE
    title = "Party Bardana Balances"
    template_name = "reports/generic.html"
    columns = PARTY_BALANCE_COLUMNS
    url_name = "products:report_party_bardana"
    as_of_report = True
    default_sort = "held"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in PARTY_BALANCE_COLUMNS.keys}
    filter_specs = (PARTY, ("ownership", "Ownership", INV_BARDANA_OWNERSHIP_CHOICES))

    def build(self):
        f = self.filters()
        data = sel.party_balances(self.as_of(), f["party"] or None, f["ownership"])
        t = data["totals"]
        tiles = [
            _tile("Parties", str(t["parties"]), "slate", "users"),
            _tile("Received", f"{t['received']:,.0f}", "green", "plus"),
            _tile("Returned", f"{t['returned']:,.0f}", "sky", "minus"),
            _tile("Held by mill", f"{t['held']:,.0f}", "amber", "layers"),
            _tile("Returnable due", f"{t['returnable']:,.0f}", "rose", "alert"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


PartyBardanaBalancesExportView, PartyBardanaBalancesColumnsView = _views(PartyBardanaBalancesView)


MOVEMENT_COLUMNS = ColumnSet("reports.bardana_movements", (
    col("date", "Date", "date", locked=True),
    col("book", "Book"),
    col("party", "Party", "link", link="inventory:supplier_detail", link_key="party_id"),
    col("item", "Sack / Bag", locked=True),
    col("source", "Source"),
    col("reference", "Document"),
    col("qty_in", "In", "qty", total=True),
    col("qty_out", "Out", "qty", total=True),
    col("ownership", "Ownership"),
    col("godown", "Godown", default=False),
    col("remarks", "Remarks", default=False),
))


class BardanaMovementView(ReportView):
    page = PAGE
    title = "Bardana Movement Register"
    template_name = "reports/generic.html"
    columns = MOVEMENT_COLUMNS
    url_name = "products:report_bardana_movements"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in MOVEMENT_COLUMNS.keys}
    filter_specs = (("book", "Book", (("party", "Party sacks"), ("mill", "Mill stock"))), PARTY, ("source", "Source", sel.source_options), ITEM)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.movement_register(p.start, p.end, f["party"] or None, f["source"], f["item"] or None, f["book"])
        t = data["totals"]
        tiles = [
            _tile("Entries", str(t["entries"]), "slate", "ledger"),
            _tile("In", f"{t['qty_in']:,.0f}", "green", "plus"),
            _tile("Out", f"{t['qty_out']:,.0f}", "rose", "minus"),
            _tile("Net", f"{t['net']:,.0f}", "amber", "layers"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


BardanaMovementExportView, BardanaMovementColumnsView = _views(BardanaMovementView)


PACKING_COLUMNS = ColumnSet("reports.packing_consumption", (
    col("number", "Voucher", "link", locked=True, link="production:grinding_detail"),
    col("date", "Date", "date", locked=True),
    col("product", "Product"),
    col("pack", "Bag Used"),
    col("output_units", "Output Bags", "qty", total=True),
    col("output_kg", "Output Kg", "qty", places=3, total=True, default=False),
    col("bags_used", "Bags Consumed", "qty", total=True, locked=True),
    col("variance", "Variance", "qty", total=True),
    col("variance_pct", "Variance %", "pct", total=True),
))


class PackingConsumptionView(ReportView):
    page = PAGE
    title = "Packing Consumption"
    template_name = "reports/generic.html"
    columns = PACKING_COLUMNS
    url_name = "products:report_packing_consumption"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in PACKING_COLUMNS.keys} | {"number": "pk"}
    filter_specs = (("product", "Product", sel.output_product_options),)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.packing_consumption(p.start, p.end, f["product"] or None)
        t = data["totals"]
        tiles = [
            _tile("Output bags", f"{t['output_units']:,.0f}", "teal", "box", f"{t['output_kg']:,.0f} kg"),
            _tile("Bags consumed", f"{t['bags_used']:,.0f}", "amber", "layers"),
            _tile("Variance", f"{t['variance']:,.0f}", "rose" if t["variance"] else "green", "alert", f"{t['variance_pct'] or 0}%"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


PackingConsumptionExportView, PackingConsumptionColumnsView = _views(PackingConsumptionView)
