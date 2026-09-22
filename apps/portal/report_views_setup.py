"""Setup / master report screens (catalogue group J)."""

from apps.core.formatting import format_amount
from apps.core.reporting import ReportView
from apps.core.table_columns import ColumnSet, col
from apps.inventory.report_views import _tile
from apps.inventory.report_views_purchase import _views

from . import report_selectors_setup as sel

PAGE = "reports.setup"
STATUS = ("status", "Status", sel.status_options)


# 68 ------------------------------------------------------------------------

PARTY_COLUMNS = ColumnSet("reports.party_directory", (
    col("kind", "Type"),
    col("code", "Code", default=False),
    col("name", "Name", "link", locked=True, link="inventory:supplier_detail", link_key="supplier_id"),
    col("city", "City"),
    col("contact", "Contact"),
    col("email", "Email", default=False),
    col("ntn", "NTN", default=False),
    col("account", "Account", "muted"),
    col("opening", "Opening", "money", total=True, default=False),
    col("credit_limit", "Credit Limit", "money", total=True),
    col("credit_days", "Credit Days", "int"),
    col("balance", "Balance", "money", total=True, locked=True, tone_key="over_limit"),
    col("status", "Status", "status"),
))


class PartyDirectoryView(ReportView):
    page = PAGE
    title = "Supplier / Customer Directory"
    template_name = "reports/generic.html"
    columns = PARTY_COLUMNS
    url_name = "portal:report_party_directory"
    as_of_report = True
    default_sort = "name"
    sort_fields = {k: k for k in PARTY_COLUMNS.keys}
    filter_specs = (("kind", "Type", sel.KIND_CHOICES), ("city", "City", sel.city_options), STATUS)

    def build(self):
        f = self.filters()
        data = sel.party_directory(self.as_of(), f["kind"], f["city"] or None, f["status"])
        t = data["totals"]
        tiles = [
            _tile("Parties", str(t["parties"]), "slate", "users", f"{t['active']} active"),
            _tile("Suppliers", str(t["suppliers"]), "amber", "user", f"Rs {format_amount(t['payable'])} payable", href="?kind=supplier", on=f["kind"] == "supplier"),
            _tile("Customers", str(t["customers"]), "teal", "users", f"Rs {format_amount(t['receivable'])} receivable", href="?kind=customer", on=f["kind"] == "customer"),
            _tile("Credit limit", format_amount(t["credit_limit"]), "sky", "cash"),
            _tile("Over limit", str(t["over_limit"]), "rose" if t["over_limit"] else "green", "alert"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


PartyDirectoryExportView, PartyDirectoryColumnsView = _views(PartyDirectoryView)


# 69 ------------------------------------------------------------------------

PRODUCT_COLUMNS = ColumnSet("reports.product_master", (
    col("code", "Code", "muted"),
    col("category", "Category"),
    col("sub_group", "Sub Group"),
    col("product", "Product", "link", locked=True, link="products:product_detail", link_key="pk"),
    col("specification", "Specification"),
    col("unit", "Unit"),
    col("unit_kg", "Pack Kg", "qty", places=3),
    col("rate", "Current Rate", "money", locked=True),
    col("rate_date", "Rate Since", "date"),
    col("previous_rate", "Previous Rate", "money"),
    col("rate_change", "Change", "money", default=False),
    col("yield_pct", "Std Yield %", "pct", default=False),
    col("starting_date", "Starting", "date", default=False),
    col("status", "Status", "status"),
))


class ProductMasterView(ReportView):
    page = PAGE
    title = "Product Master with Rates"
    template_name = "reports/generic.html"
    columns = PRODUCT_COLUMNS
    url_name = "portal:report_product_master"
    as_of_report = True
    default_sort = "code"
    sort_fields = {k: k for k in PRODUCT_COLUMNS.keys}
    filter_specs = (("category", "Category", sel.product_category_options), ("specification", "Specification", sel.specification_options), STATUS)

    def build(self):
        f = self.filters()
        data = sel.product_master(f["category"] or None, f["specification"], f["status"])
        t = data["totals"]
        tiles = [
            _tile("Products", str(t["products"]), "slate", "box", f"{t['active']} active"),
            _tile("With rate", str(t["rated"]), "green", "cash"),
            _tile("No rate", str(t["unrated"]), "amber" if t["unrated"] else "green", "alert"),
            _tile("Rate changed", str(t["changed"]), "sky", "edit"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


ProductMasterExportView, ProductMasterColumnsView = _views(ProductMasterView)


# 70 ------------------------------------------------------------------------

COA_COLUMNS = ColumnSet("reports.chart_of_accounts", (
    col("code", "Code", "muted", locked=True),
    col("title", "Account", locked=True),
    col("level", "Level", "int", default=False),
    col("type", "Type"),
    col("group", "Kind", default=False),
    col("opening", "Opening", "money", total=True),
    col("movement", "Movement", "money", total=True),
    col("closing", "Closing", "money", total=True, locked=True, tone_key="negative"),
    col("status", "Status", "status", default=False),
))


class ChartOfAccountsView(ReportView):
    page = PAGE
    title = "Chart of Accounts"
    template_name = "reports/generic.html"
    columns = COA_COLUMNS
    url_name = "portal:report_chart_of_accounts"
    as_of_report = True
    default_sort = ""
    sort_fields = {}
    filter_specs = (
        ("account_type", "Type", sel.account_type_options),
        ("postable", "Show", (("1", "Accounts only"),)),
        ("nonzero", "Balance", (("1", "Non-zero only"),)),
    )

    def build(self):
        f = self.filters()
        data = sel.chart_of_accounts(f["account_type"], f["postable"] == "1", f["nonzero"] == "1")
        t = data["totals"]
        by_type = t["by_type"]
        tiles = [_tile("Accounts", str(t["accounts"]), "slate", "layers", f"{t['groups']} groups")]
        tones = {"asset": "sky", "liability": "rose", "revenue": "green", "expense": "amber", "capital": "violet"}
        for key, label in sel.FIN_COA_ACCOUNT_TYPE_CHOICES:
            tiles.append(_tile(label, format_amount(by_type.get(key, 0)), tones.get(key, "slate"), "cash", href=f"?account_type={key}", on=f["account_type"] == key))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


ChartOfAccountsExportView, ChartOfAccountsColumnsView = _views(ChartOfAccountsView)


# 71 ------------------------------------------------------------------------

USER_COLUMNS = ColumnSet("reports.user_access", (
    col("username", "Username", "muted"),
    col("name", "User", locked=True),
    col("email", "Email", default=False),
    col("user_type", "User Type", default=False),
    col("role", "Role", locked=True),
    col("organization", "Organization"),
    col("branch", "Branch"),
    col("primary", "Primary", default=False),
    col("permissions", "Permissions", "int"),
    col("superuser", "Superuser"),
    col("last_login", "Last Login", "date"),
    col("active", "Active"),
    col("status", "Status", "status", default=False),
))


class UserAccessView(ReportView):
    page = PAGE
    title = "User Access"
    template_name = "reports/generic.html"
    columns = USER_COLUMNS
    url_name = "portal:report_user_access"
    as_of_report = True
    default_sort = "name"
    sort_fields = {k: k for k in USER_COLUMNS.keys}
    filter_specs = (("role", "Role", sel.role_options), ("organization", "Organization", sel.organization_options), ("active", "Show", (("1", "Active only"),)))

    def build(self):
        f = self.filters()
        data = sel.user_access(f["role"] or None, f["organization"] or None, f["active"] == "1")
        t = data["totals"]
        tiles = [
            _tile("Users", str(t["users"]), "slate", "users", f"{t['roles']} roles"),
            _tile("Active", str(t["active"]), "green", "check", href="?active=1", on=f["active"] == "1"),
            _tile("Inactive", str(t["inactive"]), "rose" if t["inactive"] else "green", "minus"),
            _tile("Assignments", str(t["assignments"]), "sky", "layers"),
            _tile("Superusers", str(t["superusers"]), "violet", "shield"),
            _tile("No role", str(t["unassigned"]), "amber" if t["unassigned"] else "green", "alert"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


UserAccessExportView, UserAccessColumnsView = _views(UserAccessView)
