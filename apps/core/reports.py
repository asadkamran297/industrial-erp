"""Every report in one list. The nav, the dashboard card and the access report read from here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Report:
    key: str
    label: str
    module: str
    reader: str
    url_name: str
    permission: str
    group: str
    query: str = ""


GROUP_OWNER = "Owner"
GROUP_SALES = "Sales"
GROUP_PURCHASE = "Purchase"
GROUP_WEIGHBRIDGE = "Weighbridge"
GROUP_BARDANA = "Bardana"
GROUP_PRODUCTION = "Production"
GROUP_STOCK = "Stock"
GROUP_ACCOUNTS = "Accounts"
GROUP_HR = "HR"
GROUP_SETUP = "Setup"

GROUP_ORDER = (
    GROUP_OWNER, GROUP_SALES, GROUP_PURCHASE, GROUP_WEIGHBRIDGE, GROUP_BARDANA,
    GROUP_PRODUCTION, GROUP_STOCK, GROUP_ACCOUNTS, GROUP_HR, GROUP_SETUP,
)

REPORTS: tuple[Report, ...] = (
    Report("owner.daily_position", "Daily Position", "portal", "Owner", "portal:report_daily_position", "reports.owner.index", GROUP_OWNER),
    Report("owner.month_glance", "Month at a Glance", "portal", "Owner", "portal:report_month_glance", "reports.owner.index", GROUP_OWNER),
    Report("owner.product_profit", "Profitability by Product", "portal", "Owner", "portal:report_product_profit", "reports.owner.index", GROUP_OWNER),
    Report("owner.receivables_aging", "Receivables Aging", "portal", "Owner", "portal:report_receivables_aging", "reports.owner.index", GROUP_OWNER),
    Report("owner.payables_aging", "Payables Aging", "portal", "Owner", "portal:report_payables_aging", "reports.owner.index", GROUP_OWNER),

    Report("sales.register", "Sales Register", "inventory", "Sales Manager", "inventory:report_sale", "reports.sales.index", GROUP_SALES),
    Report("sales.summary", "Sales Summary", "inventory", "Sales Manager", "inventory:report_sales_summary", "reports.sales.index", GROUP_SALES),
    Report("sales.customers", "Party-wise Sales", "inventory", "Sales Manager", "inventory:report_customer_sales", "reports.sales.index", GROUP_SALES),
    Report("sales.products", "Product-wise Sales", "inventory", "Sales Manager", "inventory:report_product_sales", "reports.sales.index", GROUP_SALES),
    Report("sales.rate_history", "Sale Rate History", "inventory", "Sales Manager", "inventory:report_rate_history", "reports.sales.index", GROUP_SALES),
    Report("sales.returns", "Sale Returns", "inventory", "Sales Manager", "inventory:report_sale_return", "reports.sales.index", GROUP_SALES),
    Report("sales.day_sheet", "POS Day Sheet", "inventory", "Cashier", "inventory:report_day_sheet", "reports.sales.index", GROUP_SALES),
    Report("sales.customer_ledger", "Customer Ledger", "inventory", "Sales Manager", "inventory:customer_ledger_list", "inventory.customer_ledger.index", GROUP_SALES),

    Report("purchase.wheat_register", "Wheat Purchase Register", "inventory", "Purchase Manager", "inventory:report_purchase", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.summary", "Purchase Summary", "inventory", "Purchase Manager", "inventory:report_purchase_summary", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.arhti", "Arhti-wise Purchase", "inventory", "Purchase Manager", "inventory:report_supplier_purchases", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.quality", "Wheat Quality", "inventory", "Purchase Manager", "inventory:report_wheat_quality", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.rate_trend", "Wheat Rate Trend", "inventory", "Purchase Manager", "inventory:report_wheat_rate_trend", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.freight", "Freight & Brokerage", "inventory", "Purchase Manager", "inventory:report_freight_brokerage", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.wht", "WHT Register", "inventory", "Purchase Manager", "inventory:report_wht", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.stores", "Stores Purchase Register", "inventory", "Purchase Manager", "inventory:report_stores_purchases", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.orders", "Order Fulfilment", "inventory", "Purchase Manager", "inventory:report_pending_orders", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.returns", "Purchase Returns", "inventory", "Purchase Manager", "inventory:report_purchase_return", "reports.purchase.index", GROUP_PURCHASE),
    Report("purchase.payments", "Supplier Payment Status", "inventory", "Purchase Manager", "inventory:report_supplier_payments", "reports.purchase.index", GROUP_PURCHASE),

    Report("weighbridge.weighbridge", "Weighbridge Register", "inventory", "Gate Clerk", "inventory:report_weighbridge", "reports.weighbridge.index", GROUP_WEIGHBRIDGE),
    Report("weighbridge.vehicles", "Vehicle-wise Report", "inventory", "Gate Clerk", "inventory:report_vehicles", "reports.weighbridge.index", GROUP_WEIGHBRIDGE),
    Report("weighbridge.weight_variance", "Weight Variance", "inventory", "Gate Clerk", "inventory:report_weight_variance", "reports.weighbridge.index", GROUP_WEIGHBRIDGE),
    Report("weighbridge.gate_sheet", "Daily Gate Sheet", "inventory", "Gate Clerk", "inventory:report_gate_sheet", "reports.weighbridge.index", GROUP_WEIGHBRIDGE),

    Report("bardana.bardana_stock", "Bardana Stock (Mill)", "products", "Bardana Clerk", "products:report_bardana_stock", "reports.bardana.index", GROUP_BARDANA),
    Report("bardana.party_bardana_balances", "Party Bardana Balances", "products", "Bardana Clerk", "products:report_party_bardana", "reports.bardana.index", GROUP_BARDANA),
    Report("bardana.bardana_movements", "Bardana Movement Register", "products", "Bardana Clerk", "products:report_bardana_movements", "reports.bardana.index", GROUP_BARDANA),
    Report("bardana.packing_consumption", "Packing Consumption", "products", "Bardana Clerk", "products:report_packing_consumption", "reports.bardana.index", GROUP_BARDANA),

    Report("production.grinding_register", "Grinding Register", "production", "Mill Manager", "production:report_grinding_register", "production.reports.index", GROUP_PRODUCTION),
    Report("production.daily_grinding", "Daily Grinding", "production", "Mill Manager", "production:report_daily_grinding", "production.reports.index", GROUP_PRODUCTION),
    Report("production.yield_trend", "Yield Trend", "production", "Mill Manager", "production:report_yield_trend", "production.reports.index", GROUP_PRODUCTION),
    Report("production.output_mix", "Product Output Mix", "production", "Mill Manager", "production:report_output_mix", "production.reports.index", GROUP_PRODUCTION),
    Report("production.shortage", "Shortage / Refraction", "production", "Mill Manager", "production:report_shortage", "production.reports.index", GROUP_PRODUCTION),
    Report("production.conversions", "Product Conversion Register", "production", "Mill Manager", "production:report_conversions", "production.reports.index", GROUP_PRODUCTION),
    Report("production.cost_per_bag", "Production Cost per Bag", "production", "Mill Manager", "production:report_cost_per_bag", "production.reports.index", GROUP_PRODUCTION),
    Report("production.production_summary", "Production Summary", "production", "Mill Manager", "production:report_production_summary", "production.reports.index", GROUP_PRODUCTION),

    Report("stock.mill_stock", "Mill Product Stock", "inventory", "Store Keeper", "inventory:report_mill_stock", "reports.stock.index", GROUP_STOCK),
    Report("stock.stores_stock", "Stores Stock", "inventory", "Store Keeper", "inventory:report_stores_stock", "reports.stock.index", GROUP_STOCK),
    Report("stock.slow_moving", "Stock Ageing / Slow Moving", "inventory", "Store Keeper", "inventory:report_slow_moving", "reports.stock.index", GROUP_STOCK),
    Report("stock.stock_adjustments", "Stock Adjustment Register", "inventory", "Store Keeper", "inventory:report_stock_adjustments", "reports.stock.index", GROUP_STOCK),
    Report("stock.godown_stock", "Godown-wise Stock", "inventory", "Store Keeper", "inventory:report_godown_stock", "reports.stock.index", GROUP_STOCK),
    Report("stock.wheat_days", "Wheat Stock in Days", "inventory", "Store Keeper", "inventory:report_wheat_days", "reports.stock.index", GROUP_STOCK),
    Report("stock.item_ledger", "Item Ledger", "inventory", "Store Keeper", "inventory:report_ledger", "inventory.item_ledger.index", GROUP_STOCK),
    Report("stock.valuation", "Inventory Valuation", "finance", "Accountant", "finance:inventory_valuation", "finance.inventory_valuation.index", GROUP_STOCK),

    Report("accounts.cash_book", "Cash Book", "finance", "Accountant", "finance:report_cash_book", "reports.accounts.index", GROUP_ACCOUNTS),
    Report("accounts.bank_book", "Bank Book", "finance", "Accountant", "finance:report_bank_book", "reports.accounts.index", GROUP_ACCOUNTS),
    Report("accounts.party_ledger", "Party Ledger", "finance", "Accountant", "finance:report_party_ledger", "reports.accounts.index", GROUP_ACCOUNTS),
    Report("accounts.voucher_register", "Voucher Register", "finance", "Accountant", "finance:report_voucher_register", "reports.accounts.index", GROUP_ACCOUNTS),
    Report("accounts.expense_analysis", "Expense Analysis", "finance", "Accountant", "finance:report_expense_analysis", "reports.accounts.index", GROUP_ACCOUNTS),
    Report("accounts.receivable_payable", "Receivable / Payable Summary", "finance", "Accountant", "finance:report_receivable_payable", "reports.accounts.index", GROUP_ACCOUNTS),
    Report("accounts.opening_balances", "Opening Balances", "finance", "Accountant", "finance:report_opening_balances", "reports.accounts.index", GROUP_ACCOUNTS),
    Report("accounts.audit_trail", "Audit Trail", "finance", "Accountant", "finance:report_audit_trail", "reports.accounts.index", GROUP_ACCOUNTS),
    Report("accounts.daybook", "Daybook", "finance", "Accountant", "finance:daybook", "reports.daybook.index", GROUP_ACCOUNTS),
    Report("accounts.account_ledger", "Account Ledger", "finance", "Accountant", "finance:account_ledger", "reports.account_ledger.index", GROUP_ACCOUNTS),
    Report("accounts.trial_balance", "Trial Balance", "finance", "Accountant", "finance:trial_balance", "finance.trial_balance.index", GROUP_ACCOUNTS),
    Report("accounts.income_statement", "Income Statement", "finance", "Accountant", "finance:income_statement", "finance.income_statement.index", GROUP_ACCOUNTS),
    Report("accounts.balance_sheet", "Balance Sheet", "finance", "Accountant", "finance:balance_sheet", "finance.balance_sheet.index", GROUP_ACCOUNTS),
    Report("accounts.cash_flow", "Cash Flow", "finance", "Accountant", "finance:cash_flow", "finance.cash_flow.index", GROUP_ACCOUNTS),
    Report("accounts.period_close", "Period Close", "finance", "Accountant", "finance:period_close", "finance.period_close.index", GROUP_ACCOUNTS),

    Report("hr.employees", "Employee Register", "payroll", "HR / Payroll", "payroll:report_employees", "reports.hr.index", GROUP_HR),
    Report("hr.salary_sheet", "Salary Sheet", "payroll", "HR / Payroll", "payroll:report_salary_sheet", "reports.hr.index", GROUP_HR),
    Report("hr.payroll_summary", "Payroll Summary", "payroll", "HR / Payroll", "payroll:report_payroll_summary", "reports.hr.index", GROUP_HR),
    Report("hr.allowance_deduction", "Allowance / Deduction Breakdown", "payroll", "HR / Payroll", "payroll:report_allowance_deduction", "reports.hr.index", GROUP_HR),

    Report("setup.party_directory", "Supplier / Customer Directory", "portal", "Admin", "portal:report_party_directory", "reports.setup.index", GROUP_SETUP),
    Report("setup.product_master", "Product Master with Rates", "portal", "Admin", "portal:report_product_master", "reports.setup.index", GROUP_SETUP),
    Report("setup.chart_of_accounts", "Chart of Accounts", "portal", "Admin", "portal:report_chart_of_accounts", "reports.setup.index", GROUP_SETUP),
    Report("setup.user_access", "User Access", "portal", "Admin", "portal:report_user_access", "reports.setup.index", GROUP_SETUP),
)

REPORT_MAP: dict[str, Report] = {report.key: report for report in REPORTS}


def reports_by_group() -> list[tuple[str, list[Report]]]:
    grouped = {group: [] for group in GROUP_ORDER}
    for report in REPORTS:
        grouped.setdefault(report.group, []).append(report)
    return [(group, rows) for group, rows in grouped.items() if rows]


def reports_for(permission_codes: set[str]) -> list[Report]:
    return [report for report in REPORTS if report.permission in permission_codes]
