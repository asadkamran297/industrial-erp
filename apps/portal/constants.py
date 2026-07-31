from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationItem:
    label: str
    permission: str | None = None
    url_name: str | None = None
    href: str = "#"
    section: str = "main"
    icon: str = ""
    children: tuple["NavigationItem", ...] = ()


SECTION_WORKSPACE = "Workspace"
SECTION_OPERATIONS = "Day to Day"
SECTION_FINANCE = "Accounts"
SECTION_WORKFORCE = "People"
SECTION_SETUP = "Setup"
SECTION_SUPPORT = "Support"


# Grouped by the job someone is doing, not by which Django app owns the page.
# "Day to Day" is work that happens every shift; "Accounts" is the books;
# "Setup" is configured once and rarely touched again. A page that is entered
# daily must never sit next to one that is configured once a year.
NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("Dashboard", permission="dashboard.index", url_name="portal:dashboard", section=SECTION_WORKSPACE, icon="D"),

    # ── Day to Day ──────────────────────────────────────────────────────
    # One group per direction goods move: in from suppliers, out to
    # customers, and what is sitting on the shelf in between.
    NavigationItem("Purchasing", permission=None, section=SECTION_OPERATIONS, icon="B", children=(
        NavigationItem("Purchase Orders", permission="inventory.purchase_orders.index", url_name="inventory:purchase_order_list"),
        NavigationItem("Goods Receipt (GRN)", permission="inventory.grn.index", url_name="inventory:grn_list"),
        NavigationItem("Purchase Returns", permission="inventory.purchase_returns.index", url_name="inventory:purchase_return_list"),
        NavigationItem("Suppliers", permission="inventory.vendors.index", url_name="inventory:vendor_list"),
        NavigationItem("Purchase Report", permission="inventory.purchase_report.index", url_name="inventory:report_purchase"),
    )),
    NavigationItem("Sales", permission=None, section=SECTION_OPERATIONS, icon="S", children=(
        NavigationItem("New Sale (POS)", permission="inventory.pos_sales.index", url_name="inventory:pos_list"),
        NavigationItem("Sale Returns", permission="inventory.pos_returns.index", url_name="inventory:pos_return_list"),
        NavigationItem("Customers", permission="inventory.customers.index", url_name="inventory:customer_list"),
        NavigationItem("Customer Ledger", permission="inventory.customer_ledger.index", url_name="inventory:customer_ledger_list"),
    )),
    NavigationItem("Stock", permission=None, section=SECTION_OPERATIONS, icon="K", children=(
        NavigationItem("Current Stock", permission="inventory.stock.index", url_name="inventory:stock_list"),
        NavigationItem("Items", permission="inventory.items.index", url_name="inventory:item_list"),
        NavigationItem("Stock Adjustment", permission="inventory.manual_transaction.index", url_name="inventory:manual_transaction"),
        NavigationItem("Item Ledger", permission="inventory.item_ledger.index", url_name="inventory:ledger_list"),
        NavigationItem("Stock Report", permission="inventory.stock.index", url_name="inventory:report_stock"),
        NavigationItem("Ledger Report", permission="inventory.item_ledger.index", url_name="inventory:report_ledger"),
    )),
    NavigationItem("Production", permission="operations.index", section=SECTION_OPERATIONS, icon="P"),

    # ── Accounts ────────────────────────────────────────────────────────
    # Entry, then what you read, then what you set up, then the one
    # deliberate act that ends a period.
    NavigationItem("Vouchers", permission="finance.vouchers.index", url_name="finance:account_voucher_list", section=SECTION_FINANCE, icon="V"),
    NavigationItem("Financial Reports", permission=None, section=SECTION_FINANCE, icon="R", children=(
        NavigationItem("Trial Balance", permission="finance.trial_balance.index", url_name="finance:trial_balance"),
        NavigationItem("Income Statement", permission="finance.income_statement.index", url_name="finance:income_statement"),
        NavigationItem("Balance Sheet", permission="finance.balance_sheet.index", url_name="finance:balance_sheet"),
        NavigationItem("Cash Flow", permission="finance.cash_flow.index", url_name="finance:cash_flow"),
        NavigationItem("Inventory Valuation", permission="finance.inventory_valuation.index", url_name="finance:inventory_valuation"),
    )),
    NavigationItem("Accounting Setup", permission=None, section=SECTION_FINANCE, icon="A", children=(
        # The tree is the chart people actually use; the flat list is the
        # older account master, named apart so the two stop being confused.
        NavigationItem("Chart of Accounts", permission="finance.chart_of_accounts.index", url_name="finance:chart_of_accounts"),
        NavigationItem("Account Master", permission="finance.accounts.index", url_name="finance:account_configuration_list"),
        NavigationItem("Opening Balances", permission="finance.opening_balances.index", url_name="finance:opening_balances"),
        NavigationItem("Fiscal Years", permission="finance.fiscal_years.index", url_name="finance:fiscal_year_list"),
    )),
    NavigationItem("Period Close", permission="finance.period_close.index", url_name="finance:period_close", section=SECTION_FINANCE, icon="L"),

    # ── People ──────────────────────────────────────────────────────────
    NavigationItem("Employees", permission="hr.employees.index", url_name="hr:employee_list", section=SECTION_WORKFORCE, icon="E"),
    NavigationItem("Payroll", permission=None, section=SECTION_WORKFORCE, icon="Y", children=(
        NavigationItem("Payroll Runs", permission="payroll.runs.index", url_name="payroll:payroll_list"),
        NavigationItem("Salary Items", permission="payroll.salary_items.index", url_name="payroll:employee_salary_list"),
    )),

    # ── Setup ───────────────────────────────────────────────────────────
    # Everything configured once. Item classes and UOMs live here rather
    # than under Stock: they are defined at setup, not touched on a shift.
    NavigationItem("Master Data", permission=None, section=SECTION_SETUP, icon="M", children=(
        NavigationItem("Item Classes", permission="inventory.classes.index", url_name="inventory:class_list"),
        NavigationItem("Units of Measure", permission="inventory.uoms.index", url_name="inventory:uom_list"),
        NavigationItem("UOM Conversions", permission="inventory.uom_conversions.index", url_name="inventory:conversion_list"),
        NavigationItem("Departments", permission="configurations.departments.index", href="/masters/departments/"),
        NavigationItem("Designations", permission="configurations.designations.index", href="/masters/designations/"),
        NavigationItem("Job Types", permission="configurations.job_types.index", href="/masters/job-types/"),
        NavigationItem("Cities", permission="configurations.cities.index", href="/masters/cities/"),
        NavigationItem("Banks", permission="configurations.banks.index", href="/masters/banks/"),
        NavigationItem("Allowances & Deductions", permission="configurations.allowance_deductions.index", href="/masters/allowance-deductions/"),
    )),
    NavigationItem("Company", permission=None, section=SECTION_SETUP, icon="O", children=(
        NavigationItem("Organizations", permission="organizations.organizations.index", url_name="organizations:organization_list"),
        NavigationItem("Branches", permission="organizations.branches.index", url_name="organizations:branch_list"),
    )),
    NavigationItem("Users & Access", permission=None, section=SECTION_SETUP, icon="U", children=(
        NavigationItem("User Assignments", permission="access_control.user_assignments.index", url_name="access_control:user_assignment_list"),
        NavigationItem("Roles", permission="access_control.roles.index", url_name="access_control:role_list"),
        NavigationItem("Permissions", permission="access_control.permissions.index", url_name="access_control:permission_list"),
    )),
    NavigationItem("System Settings", permission="settings.index", section=SECTION_SETUP, icon="G"),

    NavigationItem("Help Desk", permission="help.index", section=SECTION_SUPPORT, icon="?"),
)
