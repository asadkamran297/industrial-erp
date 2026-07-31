"""Single source of truth for page-level access-control permissions.

Every navigable page defines a ``key`` (``module.page``) and the set of CRUD
actions it supports. Permission codes are ``<key>.<action>`` (e.g.
``inventory.items.add``). The seeder, nav, views and templates all derive their
codes from this registry so there is exactly one place to add a page.
"""

from dataclasses import dataclass, field

from apps.core.constants import (
    ACTION_ADD,
    ACTION_DELETE,
    ACTION_EDIT,
    ACTION_INDEX,
    ACTION_LABELS,
    ACTION_VIEW,
    PAGE_ACTIONS,
)

CRUD = PAGE_ACTIONS
LIST_ONLY = (ACTION_INDEX,)
READ_ONLY = (ACTION_INDEX, ACTION_VIEW)
MASTER = (ACTION_INDEX, ACTION_ADD, ACTION_EDIT, ACTION_DELETE)
MASTER_NO_DELETE = (ACTION_INDEX, ACTION_ADD, ACTION_EDIT)


@dataclass(frozen=True)
class Page:
    key: str
    label: str
    group: str
    actions: tuple[str, ...] = field(default=CRUD)


_STATIC_PAGES: tuple[Page, ...] = (
    # Workspace
    Page("dashboard", "Dashboard", "Workspace", LIST_ONLY),
    Page("operations", "Production", "Operations", LIST_ONLY),
    Page("reports", "Reports", "Analytics", LIST_ONLY),
    Page("settings", "System Settings", "Setup", LIST_ONLY),
    Page("help", "Help Desk", "Support", LIST_ONLY),
    # Inventory
    Page("inventory.classes", "Inventory Classes", "Inventory", MASTER_NO_DELETE),
    Page("inventory.uoms", "UOMs", "Inventory", MASTER_NO_DELETE),
    Page("inventory.uom_conversions", "UOM Conversions", "Inventory", MASTER_NO_DELETE),
    Page("inventory.vendors", "Vendors", "Inventory", MASTER_NO_DELETE),
    Page("inventory.items", "Items", "Inventory", MASTER_NO_DELETE),
    Page("inventory.stock", "Current Stock", "Inventory", READ_ONLY),
    Page("inventory.item_ledger", "Item Ledger", "Inventory", READ_ONLY),
    Page("inventory.customer_ledger", "Customer Ledger", "Inventory", READ_ONLY),
    Page("inventory.purchase_orders", "Purchase Orders", "Inventory", CRUD),
    Page("inventory.grn", "GRN", "Inventory", READ_ONLY + (ACTION_EDIT,)),
    Page("inventory.manual_transaction", "Manual Transaction", "Inventory", CRUD),
    Page("inventory.customers", "Customers", "Inventory", MASTER_NO_DELETE),
    Page("inventory.pos_sales", "POS Sales", "Inventory", (ACTION_INDEX, ACTION_VIEW, ACTION_ADD, ACTION_EDIT)),
    Page("inventory.pos_returns", "POS Returns", "Inventory", (ACTION_INDEX, ACTION_VIEW, ACTION_ADD, ACTION_EDIT)),
    Page("inventory.purchase_returns", "Purchase Returns", "Inventory", (ACTION_INDEX, ACTION_VIEW, ACTION_ADD, ACTION_EDIT)),
    Page("inventory.purchase_report", "Purchase Report", "Inventory", READ_ONLY),
    # Finance
    Page("finance.fiscal_years", "Fiscal Years", "Finance", MASTER_NO_DELETE),
    Page("finance.accounts", "Chart of Accounts", "Finance", MASTER_NO_DELETE),
    Page("finance.chart_of_accounts", "Chart of Accounts Tree", "Finance", MASTER),
    Page("finance.vouchers", "Vouchers", "Finance", CRUD),
    Page("finance.opening_balances", "Opening Balances", "Finance", MASTER_NO_DELETE),
    Page("finance.trial_balance", "Trial Balance", "Finance", LIST_ONLY),
    Page("finance.income_statement", "Income Statement", "Finance", LIST_ONLY),
    Page("finance.balance_sheet", "Balance Sheet", "Finance", LIST_ONLY),
    Page("finance.cash_flow", "Cash Flow", "Finance", LIST_ONLY),
    Page("finance.period_close", "Period Close", "Finance", (ACTION_INDEX, ACTION_ADD)),
    # Workforce
    Page("hr.employees", "Employees", "Workforce", CRUD),
    Page("payroll.salary_items", "Salary Items", "Workforce", MASTER),
    Page("payroll.runs", "Payroll Runs", "Workforce", MASTER),
    # Setup
    Page("organizations.organizations", "Organizations", "Setup", MASTER),
    Page("organizations.branches", "Branches", "Setup", MASTER),
    Page("access_control.roles", "Roles", "Setup", MASTER),
    Page("access_control.permissions", "Permissions", "Setup", MASTER),
    Page("access_control.user_assignments", "User Assignments", "Setup", MASTER),
)


def _configuration_pages() -> tuple[Page, ...]:
    from apps.configurations.registry import MASTER_CONFIGS

    return tuple(
        Page(f"configurations.{config.slug.replace('-', '_')}", config.label, "Master Data", MASTER)
        for config in MASTER_CONFIGS
    )


PAGES: tuple[Page, ...] = _STATIC_PAGES + _configuration_pages()

PAGE_MAP: dict[str, Page] = {page.key: page for page in PAGES}


def page_codes(key: str) -> list[str]:
    """All permission codes for a page key, e.g. ``inventory.items`` -> 5 codes."""
    page = PAGE_MAP.get(key)
    if not page:
        return []
    return [f"{page.key}.{action}" for action in page.actions]


def iter_page_permissions():
    """Yield ``(code, title, seq)`` for every page/action, ordered for seeding."""
    seq = 0
    for page in PAGES:
        for action in page.actions:
            seq += 10
            code = f"{page.key}.{action}"
            title = f"{ACTION_LABELS[action]} {page.label}"
            yield code, title, seq


def all_codes() -> list[str]:
    return [code for code, _title, _seq in iter_page_permissions()]
