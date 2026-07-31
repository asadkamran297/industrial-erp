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
SECTION_OPERATIONS = "Operations"
SECTION_WORKFORCE = "Workforce"
SECTION_ANALYTICS = "Analytics"
SECTION_SETUP = "Setup"
SECTION_SUPPORT = "Support"


NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("Dashboard", permission="dashboard.index", url_name="portal:dashboard", section=SECTION_WORKSPACE, icon="D"),
    NavigationItem("Production", permission="operations.index", section=SECTION_OPERATIONS, icon="P"),
    NavigationItem("Inventory", permission=None, section=SECTION_OPERATIONS, icon="I", children=(
        NavigationItem("Classes", permission="inventory.classes.index", url_name="inventory:class_list"),
        NavigationItem("UOMs", permission="inventory.uoms.index", url_name="inventory:uom_list"),
        NavigationItem("UOM Conversions", permission="inventory.uom_conversions.index", url_name="inventory:conversion_list"),
        NavigationItem("Vendors", permission="inventory.vendors.index", url_name="inventory:vendor_list"),
        NavigationItem("Items", permission="inventory.items.index", url_name="inventory:item_list"),
        NavigationItem("Current Stock", permission="inventory.stock.index", url_name="inventory:stock_list"),
        NavigationItem("Item Ledger", permission="inventory.item_ledger.index", url_name="inventory:ledger_list"),
        NavigationItem("Customer Ledger", permission="inventory.customer_ledger.index", url_name="inventory:customer_ledger_list"),
        NavigationItem("Purchase Orders", permission="inventory.purchase_orders.index", url_name="inventory:purchase_order_list"),
        NavigationItem("GRN", permission="inventory.grn.index", url_name="inventory:grn_list"),
        NavigationItem("Manual Transaction", permission="inventory.manual_transaction.index", url_name="inventory:manual_transaction"),
        NavigationItem("Customers", permission="inventory.customers.index", url_name="inventory:customer_list"),
        NavigationItem("POS Sales", permission="inventory.pos_sales.index", url_name="inventory:pos_list"),
        NavigationItem("POS Returns", permission="inventory.pos_returns.index", url_name="inventory:pos_return_list"),
        NavigationItem("Purchase Returns", permission="inventory.purchase_returns.index", url_name="inventory:purchase_return_list"),
        NavigationItem("Stock Report", permission="inventory.stock.index", url_name="inventory:report_stock"),
        NavigationItem("Ledger Report", permission="inventory.item_ledger.index", url_name="inventory:report_ledger"),
        NavigationItem("Purchase Report", permission="inventory.purchase_report.index", url_name="inventory:report_purchase"),
    )),
    NavigationItem("Finance", permission=None, section=SECTION_OPERATIONS, icon="F", children=(
        NavigationItem("Fiscal Years", permission="finance.fiscal_years.index", url_name="finance:fiscal_year_list"),
        NavigationItem("Chart of Accounts", permission="finance.accounts.index", url_name="finance:account_configuration_list"),
        NavigationItem("Chart of Accounts Tree", permission="finance.chart_of_accounts.index", url_name="finance:chart_of_accounts"),
        NavigationItem("Opening Balances", permission="finance.opening_balances.index", url_name="finance:opening_balances"),
        NavigationItem("Trial Balance", permission="finance.trial_balance.index", url_name="finance:trial_balance"),
        NavigationItem("Income Statement", permission="finance.income_statement.index", url_name="finance:income_statement"),
        NavigationItem("Balance Sheet", permission="finance.balance_sheet.index", url_name="finance:balance_sheet"),
        NavigationItem("Cash Flow", permission="finance.cash_flow.index", url_name="finance:cash_flow"),
        NavigationItem("Inventory Valuation", permission="finance.inventory_valuation.index", url_name="finance:inventory_valuation"),
        NavigationItem("Period Close", permission="finance.period_close.index", url_name="finance:period_close"),
        NavigationItem("Vouchers", permission="finance.vouchers.index", url_name="finance:account_voucher_list"),
    )),
    NavigationItem("Employees", permission="hr.employees.index", section=SECTION_WORKFORCE, icon="E", url_name="hr:employee_list"),
    NavigationItem("Payroll", permission=None, section=SECTION_WORKFORCE, icon="P", children=(
        NavigationItem("Salary Items", permission="payroll.salary_items.index", url_name="payroll:employee_salary_list"),
        NavigationItem("Payroll Runs", permission="payroll.runs.index", url_name="payroll:payroll_list"),
    )),
    NavigationItem("Reports", permission="reports.index", section=SECTION_ANALYTICS, icon="R"),
    NavigationItem(
        "Company Structure",
        permission=None,
        section=SECTION_SETUP,
        icon="C",
        children=(
            NavigationItem("Organizations", permission="organizations.organizations.index", url_name="organizations:organization_list"),
            NavigationItem("Branches", permission="organizations.branches.index", url_name="organizations:branch_list"),
        ),
    ),
    NavigationItem(
        "Access Control",
        permission=None,
        section=SECTION_SETUP,
        icon="A",
        children=(
            NavigationItem("Roles", permission="access_control.roles.index", url_name="access_control:role_list"),
            NavigationItem("Permissions", permission="access_control.permissions.index", url_name="access_control:permission_list"),
            NavigationItem("User Assignments", permission="access_control.user_assignments.index", url_name="access_control:user_assignment_list"),
        ),
    ),
    NavigationItem("Master Data", permission=None, section=SECTION_SETUP, icon="M", children=(
        NavigationItem("Departments", permission="configurations.departments.index", href="/masters/departments/"),
        NavigationItem("Designations", permission="configurations.designations.index", href="/masters/designations/"),
        NavigationItem("Cities", permission="configurations.cities.index", href="/masters/cities/"),
        NavigationItem("Job Types", permission="configurations.job_types.index", href="/masters/job-types/"),
        NavigationItem("Banks", permission="configurations.banks.index", href="/masters/banks/"),
        NavigationItem("Allowances & Deductions", permission="configurations.allowance_deductions.index", href="/masters/allowance-deductions/"),
    )),
    NavigationItem("System Settings", permission="settings.index", section=SECTION_SETUP, icon="S"),
    NavigationItem("Help Desk", permission="help.index", section=SECTION_SUPPORT, icon="?"),
)
