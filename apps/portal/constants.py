from dataclasses import dataclass

from apps.core.constants import FIN_VOUCHER_TYPE_PICKER_META


@dataclass(frozen=True)
class NavigationItem:
    label: str
    permission: str | None = None
    url_name: str | None = None
    href: str = "#"
    section: str = "main"
    icon: str = ""
    children: tuple["NavigationItem", ...] = ()
    query: str = ""
    match_paths: tuple[str, ...] = ()
    hidden: bool = False


SECTION_WORKSPACE = "Workspace"
SECTION_OPERATIONS = "Day to Day"
SECTION_FINANCE = "Accounts"
SECTION_REPORTS = "Reports"
SECTION_WORKFORCE = "People"
SECTION_SETUP = "Setup"
SECTION_SUPPORT = "Support"


NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("Dashboard", permission="dashboard.index", url_name="portal:dashboard", section=SECTION_WORKSPACE, icon="D"),

    NavigationItem("Purchase", permission=None, section=SECTION_OPERATIONS, icon="B", children=(
        NavigationItem("Purchase Invoices", permission="inventory.purchase_orders.index", url_name="inventory:purchase_invoice_list"),
        NavigationItem("Purchase Orders", permission="inventory.purchase_orders.index",
                       url_name="inventory:purchase_order_board",
                       match_paths=("/inventory/purchase-orders/",)),
        NavigationItem("Purchase Returns", permission="inventory.purchase_returns.index", url_name="inventory:purchase_return_list"),
        NavigationItem("Suppliers", permission="inventory.suppliers.index", url_name="inventory:supplier_list"),
        NavigationItem("Pending Orders", permission="inventory.purchase_report.index", url_name="inventory:report_pending_orders"),
        NavigationItem("Purchase Report", permission="inventory.purchase_report.index", url_name="inventory:report_purchase"),
    )),
    NavigationItem("Sales", permission=None, section=SECTION_OPERATIONS, icon="S", children=(
        NavigationItem("Sale Invoices", permission="inventory.pos_sales.index", url_name="inventory:sale_invoice_list"),
        NavigationItem("Sales Orders", permission="inventory.pos_sales.index",
                       url_name="inventory:sales_order_list",
                       match_paths=("/inventory/sales-orders/",)),
        NavigationItem("New Sale (POS)", permission="inventory.pos_sales.index", url_name="inventory:pos_list"),
        NavigationItem("Sale Returns", permission="inventory.pos_returns.index", url_name="inventory:pos_return_list"),
        NavigationItem("Customers", permission="inventory.customers.index", url_name="inventory:customer_list"),
        NavigationItem("Customer Ledger", permission="inventory.customer_ledger.index", url_name="inventory:customer_ledger_list"),
    )),
    NavigationItem("Stock", permission=None, section=SECTION_OPERATIONS, icon="K", children=(
        NavigationItem("Items & Stock", permission="inventory.items.index", url_name="inventory:item_list"),
        NavigationItem("Stock Adjustment", permission="inventory.manual_transaction.index", url_name="inventory:manual_transaction"),
        NavigationItem("Item Ledger", permission="inventory.item_ledger.index", url_name="inventory:ledger_list"),
        NavigationItem("Ledger Report", permission="inventory.item_ledger.index", url_name="inventory:report_ledger"),
    )),
    NavigationItem("Products", permission=None, section=SECTION_OPERATIONS, icon="F", children=(
        NavigationItem("Product List", permission="products.products.index", url_name="products:product_list"),
        NavigationItem("Account Linking", permission="products.account_links.index", url_name="products:account_linking"),
        NavigationItem("Raw Bardana Linking", permission="products.raw_bardana.index", url_name="products:raw_bardana_linking"),
        NavigationItem("Finish Bardana Linking", permission="products.finish_bardana.index", url_name="products:finish_bardana_linking"),
        NavigationItem("Opening Balance", permission="products.opening_balances.index", url_name="products:opening_balance"),
        NavigationItem("Rate Update", permission="products.rates.index", url_name="products:rate_update"),
    )),
    NavigationItem("Production", permission=None, section=SECTION_OPERATIONS, icon="P", children=(
        NavigationItem("Grinding", permission="production.grinding.index", url_name="production:grinding_list",
                       match_paths=("/production/grinding/",)),
        NavigationItem("Products Conversion", permission="production.conversions.index",
                       url_name="production:conversion_list"),
        NavigationItem("Daily Grinding", permission="production.reports.index",
                       url_name="production:report_daily_grinding"),
        NavigationItem("Yield Trend", permission="production.reports.index",
                       url_name="production:report_yield_trend"),
        NavigationItem("Production Summary", permission="production.reports.index",
                       url_name="production:report_production_summary"),
    )),

    NavigationItem("Vouchers", permission=None, section=SECTION_FINANCE, icon="V", children=tuple(
        NavigationItem(
            label,
            permission="finance.vouchers.index",
            url_name="finance:account_voucher_list",
            query=f"voucher_type={code}",
        )
        for code, label, _fkey, _prefix in FIN_VOUCHER_TYPE_PICKER_META
    )),
    NavigationItem("Financial Reports", permission=None, section=SECTION_FINANCE, icon="R", children=(
        NavigationItem("Trial Balance", permission="finance.trial_balance.index", url_name="finance:trial_balance"),
        NavigationItem("Income Statement", permission="finance.income_statement.index", url_name="finance:income_statement"),
        NavigationItem("Balance Sheet", permission="finance.balance_sheet.index", url_name="finance:balance_sheet"),
        NavigationItem("Cash Flow", permission="finance.cash_flow.index", url_name="finance:cash_flow"),
        NavigationItem("Inventory Valuation", permission="finance.inventory_valuation.index", url_name="finance:inventory_valuation"),
    )),
    NavigationItem("Accounting Setup", permission=None, section=SECTION_FINANCE, icon="A", children=(
        NavigationItem("Chart of Accounts", permission="finance.chart_of_accounts.index", url_name="finance:chart_of_accounts"),
        NavigationItem("Account Master", permission="finance.accounts.index", url_name="finance:account_configuration_list"),
        NavigationItem("Opening Balances", permission="finance.opening_balances.index", url_name="finance:opening_balances"),
        NavigationItem("Fiscal Years", permission="finance.fiscal_years.index", url_name="finance:fiscal_year_list"),
    )),
    NavigationItem("Period Close", permission="finance.period_close.index", url_name="finance:period_close", section=SECTION_FINANCE, icon="L"),

    NavigationItem("Owner", permission=None, section=SECTION_REPORTS, icon="R", children=(
        NavigationItem("Daily Position", permission="reports.owner.index", url_name="portal:report_daily_position"),
        NavigationItem("Month at a Glance", permission="reports.owner.index", url_name="portal:report_month_glance"),
        NavigationItem("Profitability by Product", permission="reports.owner.index", url_name="portal:report_product_profit"),
        NavigationItem("Receivables Aging", permission="reports.owner.index", url_name="portal:report_receivables_aging"),
        NavigationItem("Payables Aging", permission="reports.owner.index", url_name="portal:report_payables_aging"),
    )),
    NavigationItem("Sales Reports", permission=None, section=SECTION_REPORTS, icon="S", children=(
        NavigationItem("Sales Register", permission="reports.sales.index", url_name="inventory:report_sale"),
        NavigationItem("Sales Summary", permission="reports.sales.index", url_name="inventory:report_sales_summary"),
        NavigationItem("Party-wise Sales", permission="reports.sales.index", url_name="inventory:report_customer_sales"),
        NavigationItem("Product-wise Sales", permission="reports.sales.index", url_name="inventory:report_product_sales"),
        NavigationItem("Sale Rate History", permission="reports.sales.index", url_name="inventory:report_rate_history"),
        NavigationItem("Sale Returns", permission="reports.sales.index", url_name="inventory:report_sale_return"),
        NavigationItem("POS Day Sheet", permission="reports.sales.index", url_name="inventory:report_day_sheet"),
        NavigationItem("Customer Ledger", permission="inventory.customer_ledger.index", url_name="inventory:customer_ledger_list"),
    )),
    NavigationItem("Purchase Reports", permission=None, section=SECTION_REPORTS, icon="B", children=(
        NavigationItem("Wheat Purchase Register", permission="reports.purchase.index", url_name="inventory:report_purchase"),
        NavigationItem("Purchase Summary", permission="reports.purchase.index", url_name="inventory:report_purchase_summary"),
        NavigationItem("Arhti-wise Purchase", permission="reports.purchase.index", url_name="inventory:report_supplier_purchases"),
        NavigationItem("Wheat Quality", permission="reports.purchase.index", url_name="inventory:report_wheat_quality"),
        NavigationItem("Wheat Rate Trend", permission="reports.purchase.index", url_name="inventory:report_wheat_rate_trend"),
        NavigationItem("Freight & Brokerage", permission="reports.purchase.index", url_name="inventory:report_freight_brokerage"),
        NavigationItem("WHT Register", permission="reports.purchase.index", url_name="inventory:report_wht"),
        NavigationItem("Stores Purchase Register", permission="reports.purchase.index", url_name="inventory:report_stores_purchases"),
        NavigationItem("Order Fulfilment", permission="reports.purchase.index", url_name="inventory:report_pending_orders"),
        NavigationItem("Purchase Returns", permission="reports.purchase.index", url_name="inventory:report_purchase_return"),
        NavigationItem("Supplier Payment Status", permission="reports.purchase.index", url_name="inventory:report_supplier_payments"),
    )),
    NavigationItem("Weighbridge", permission=None, section=SECTION_REPORTS, icon="W", children=(
        NavigationItem("Weighbridge Register", permission="reports.weighbridge.index", url_name="inventory:report_weighbridge"),
        NavigationItem("Vehicle-wise Report", permission="reports.weighbridge.index", url_name="inventory:report_vehicles"),
        NavigationItem("Weight Variance", permission="reports.weighbridge.index", url_name="inventory:report_weight_variance"),
        NavigationItem("Daily Gate Sheet", permission="reports.weighbridge.index", url_name="inventory:report_gate_sheet"),
    )),
    NavigationItem("Bardana", permission=None, section=SECTION_REPORTS, icon="J", children=(
        NavigationItem("Bardana Stock (Mill)", permission="reports.bardana.index", url_name="products:report_bardana_stock"),
        NavigationItem("Party Bardana Balances", permission="reports.bardana.index", url_name="products:report_party_bardana"),
        NavigationItem("Bardana Movement Register", permission="reports.bardana.index", url_name="products:report_bardana_movements"),
        NavigationItem("Packing Consumption", permission="reports.bardana.index", url_name="products:report_packing_consumption"),
    )),
    NavigationItem("Production Reports", permission=None, section=SECTION_REPORTS, icon="P", children=(
        NavigationItem("Grinding Register", permission="production.reports.index", url_name="production:report_grinding_register"),
        NavigationItem("Daily Grinding", permission="production.reports.index", url_name="production:report_daily_grinding"),
        NavigationItem("Yield Trend", permission="production.reports.index", url_name="production:report_yield_trend"),
        NavigationItem("Product Output Mix", permission="production.reports.index", url_name="production:report_output_mix"),
        NavigationItem("Shortage / Refraction", permission="production.reports.index", url_name="production:report_shortage"),
        NavigationItem("Product Conversion Register", permission="production.reports.index", url_name="production:report_conversions"),
        NavigationItem("Production Cost per Bag", permission="production.reports.index", url_name="production:report_cost_per_bag"),
        NavigationItem("Production Summary", permission="production.reports.index", url_name="production:report_production_summary"),
    )),
    NavigationItem("Stock Reports", permission=None, section=SECTION_REPORTS, icon="K", children=(
        NavigationItem("Mill Product Stock", permission="reports.stock.index", url_name="inventory:report_mill_stock"),
        NavigationItem("Stores Stock", permission="reports.stock.index", url_name="inventory:report_stores_stock"),
        NavigationItem("Stock Ageing / Slow Moving", permission="reports.stock.index", url_name="inventory:report_slow_moving"),
        NavigationItem("Stock Adjustment Register", permission="reports.stock.index", url_name="inventory:report_stock_adjustments"),
        NavigationItem("Godown-wise Stock", permission="reports.stock.index", url_name="inventory:report_godown_stock"),
        NavigationItem("Wheat Stock in Days", permission="reports.stock.index", url_name="inventory:report_wheat_days"),
        NavigationItem("Item Ledger", permission="inventory.item_ledger.index", url_name="inventory:report_ledger"),
        NavigationItem("Stock Valuation", permission="finance.inventory_valuation.index", url_name="finance:inventory_valuation"),
    )),
    NavigationItem("Accounts Reports", permission=None, section=SECTION_REPORTS, icon="A", children=(
        NavigationItem("Cash Book", permission="reports.accounts.index", url_name="finance:report_cash_book"),
        NavigationItem("Bank Book", permission="reports.accounts.index", url_name="finance:report_bank_book"),
        NavigationItem("Party Ledger", permission="reports.accounts.index", url_name="finance:report_party_ledger"),
        NavigationItem("Voucher Register", permission="reports.accounts.index", url_name="finance:report_voucher_register"),
        NavigationItem("Expense Analysis", permission="reports.accounts.index", url_name="finance:report_expense_analysis"),
        NavigationItem("Receivable / Payable Summary", permission="reports.accounts.index", url_name="finance:report_receivable_payable"),
        NavigationItem("Opening Balances", permission="reports.accounts.index", url_name="finance:report_opening_balances"),
        NavigationItem("Audit Trail", permission="reports.accounts.index", url_name="finance:report_audit_trail"),
        NavigationItem("Daybook", permission="reports.daybook.index", url_name="finance:daybook"),
        NavigationItem("Account Ledger", permission="reports.account_ledger.index", url_name="finance:account_ledger"),
        NavigationItem("Trial Balance", permission="finance.trial_balance.index", url_name="finance:trial_balance"),
        NavigationItem("Income Statement", permission="finance.income_statement.index", url_name="finance:income_statement"),
        NavigationItem("Balance Sheet", permission="finance.balance_sheet.index", url_name="finance:balance_sheet"),
        NavigationItem("Cash Flow", permission="finance.cash_flow.index", url_name="finance:cash_flow"),
        NavigationItem("Period Close", permission="finance.period_close.index", url_name="finance:period_close"),
    )),
    NavigationItem("HR Reports", permission=None, section=SECTION_REPORTS, icon="E", children=(
        NavigationItem("Employee Register", permission="reports.hr.index", url_name="payroll:report_employees"),
        NavigationItem("Salary Sheet", permission="reports.hr.index", url_name="payroll:report_salary_sheet"),
        NavigationItem("Payroll Summary", permission="reports.hr.index", url_name="payroll:report_payroll_summary"),
        NavigationItem("Allowance / Deduction Breakdown", permission="reports.hr.index", url_name="payroll:report_allowance_deduction"),
    )),
    NavigationItem("Setup Reports", permission=None, section=SECTION_REPORTS, icon="M", children=(
        NavigationItem("Supplier / Customer Directory", permission="reports.setup.index", url_name="portal:report_party_directory"),
        NavigationItem("Product Master with Rates", permission="reports.setup.index", url_name="portal:report_product_master"),
        NavigationItem("Chart of Accounts", permission="reports.setup.index", url_name="portal:report_chart_of_accounts"),
        NavigationItem("User Access", permission="reports.setup.index", url_name="portal:report_user_access"),
    )),

    NavigationItem("Employees", permission="hr.employees.index", url_name="hr:employee_list", section=SECTION_WORKFORCE, icon="E"),
    NavigationItem("Payroll", permission=None, section=SECTION_WORKFORCE, icon="Y", children=(
        NavigationItem("Payroll Runs", permission="payroll.runs.index", url_name="payroll:payroll_list"),
        NavigationItem("Salary Items", permission="payroll.salary_items.index", url_name="payroll:employee_salary_list"),
    )),

    NavigationItem("Master Data", permission=None, section=SECTION_SETUP, icon="M", children=(
        NavigationItem("Item Categories", permission="inventory.classes.index", url_name="inventory:class_list"),
        NavigationItem("Units of Measure", permission="inventory.uoms.index", url_name="inventory:uom_list"),
        NavigationItem("UOM Conversions", permission="inventory.uom_conversions.index", url_name="inventory:conversion_list"),
        NavigationItem("Godowns", permission="godowns.godowns.index", url_name="godowns:godown_list"),
        NavigationItem("Departments", permission="configurations.departments.index", href="/masters/departments/", hidden=True),
        NavigationItem("Designations", permission="configurations.designations.index", href="/masters/designations/", hidden=True),
        NavigationItem("Job Types", permission="configurations.job_types.index", href="/masters/job-types/", hidden=True),
        NavigationItem("Cities", permission="configurations.cities.index", href="/masters/cities/", hidden=True),
        NavigationItem("Banks", permission="configurations.banks.index", href="/masters/banks/", hidden=True),
        NavigationItem("Allowances & Deductions", permission="configurations.allowance_deductions.index", href="/masters/allowance-deductions/", hidden=True),
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
