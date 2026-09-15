from typing import Final

StatusChoices = tuple[tuple[str, str], ...]

STATUS_DRAFT: Final = "draft"
STATUS_PENDING: Final = "pending"
STATUS_APPROVED: Final = "approved"
STATUS_REJECTED: Final = "rejected"
STATUS_ACTIVE: Final = "active"
STATUS_INACTIVE: Final = "inactive"
STATUS_ARCHIVED: Final = "archived"
STATUS_COMPLETED: Final = "completed"
STATUS_ONGOING: Final = "ongoing"
STATUS_CREATED: Final = "created"
STATUS_RAISED: Final = "raised"
STATUS_SUBMITTED: Final = "submitted"
STATUS_VERIFIED: Final = "verified"
STATUS_DOUBLE_VERIFIED: Final = "double_verified"
STATUS_POSTED: Final = "posted"
STATUS_CANCELLED: Final = "cancelled"
STATUS_RETURNED: Final = "returned"
STATUS_PARTIAL_RETURNED: Final = "partial_returned"
STATUS_PARTIAL_RECEIVED: Final = "partial_received"
STATUS_FULLY_RECEIVED: Final = "fully_received"
STATUS_CLOSED_SHORT: Final = "closed_short"
STATUS_MATCHED: Final = "matched"
STATUS_REVERSED: Final = "reversed"
STATUS_PARTIALLY_INVOICED: Final = "partially_invoiced"
STATUS_FULLY_INVOICED: Final = "fully_invoiced"
STATUS_CLOSED: Final = "closed"

ALLOWANCE: Final = "allowance"
DEDUCTION: Final = "deduction"

ACCOUNT_TYPE_ASSET: Final = "asset"
ACCOUNT_TYPE_LIABILITY: Final = "liability"
ACCOUNT_TYPE_REVENUE: Final = "revenue"
ACCOUNT_TYPE_EXPENSE: Final = "expense"
ACCOUNT_TYPE_CAPITAL: Final = "capital"

ACCOUNT_LEDGER_GENERAL: Final = "G"
ACCOUNT_LEDGER_SUBSIDIARY: Final = "S"

BALANCE_INCOME_BALANCE_SHEET: Final = "B"
BALANCE_INCOME_INCOME_STATEMENT: Final = "I"

ACCOUNT_NATURE_DEBIT: Final = "D"
ACCOUNT_NATURE_CREDIT: Final = "C"

VOUCHER_TYPE_PAYMENT: Final = "PV"
VOUCHER_TYPE_RECEIPT: Final = "RV"
VOUCHER_TYPE_CONTRA: Final = "CN"
VOUCHER_TYPE_JOURNAL: Final = "JV"
VOUCHER_TYPE_SALES: Final = "SV"
VOUCHER_TYPE_PURCHASE: Final = "PU"

YES: Final = "Y"
NO: Final = "N"

QUALIFICATION_DEGREE: Final = "degree"
QUALIFICATION_DIPLOMA: Final = "diploma"
QUALIFICATION_CERTIFICATE: Final = "certificate"

SCOPE_LOCAL: Final = "local"
SCOPE_GLOBAL: Final = "global"

WORKFLOW_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_DRAFT, "Draft"),
    (STATUS_PENDING, "Pending"),
    (STATUS_APPROVED, "Approved"),
    (STATUS_REJECTED, "Rejected"),
)

RECORD_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_ACTIVE, "Active"),
    (STATUS_INACTIVE, "Inactive"),
    (STATUS_ARCHIVED, "Archived"),
)

FIN_ACCOUNT_TYPE_CHOICES: Final[StatusChoices] = (
    (ACCOUNT_TYPE_ASSET, "Asset"),
    (ACCOUNT_TYPE_LIABILITY, "Liability"),
    (ACCOUNT_TYPE_REVENUE, "Revenue"),
    (ACCOUNT_TYPE_EXPENSE, "Expense"),
)

FIN_ACCOUNT_LEDGER_CHOICES: Final[StatusChoices] = (
    (ACCOUNT_LEDGER_GENERAL, "General"),
    (ACCOUNT_LEDGER_SUBSIDIARY, "Subsidiary"),
)

FIN_COA_ACCOUNT_TYPE_CHOICES: Final[StatusChoices] = (
    (ACCOUNT_TYPE_ASSET, "Assets"),
    (ACCOUNT_TYPE_LIABILITY, "Liabilities"),
    (ACCOUNT_TYPE_REVENUE, "Revenue"),
    (ACCOUNT_TYPE_EXPENSE, "Expenses"),
    (ACCOUNT_TYPE_CAPITAL, "Capital"),
)

FIN_BALANCE_INCOME_CHOICES: Final[StatusChoices] = (
    (BALANCE_INCOME_BALANCE_SHEET, "Balance Sheet"),
    (BALANCE_INCOME_INCOME_STATEMENT, "Income Statement"),
)

FIN_ACCOUNT_NATURE_CHOICES: Final[StatusChoices] = (
    (ACCOUNT_NATURE_DEBIT, "Debit"),
    (ACCOUNT_NATURE_CREDIT, "Credit"),
)

FIN_VOUCHER_TYPE_CHOICES: Final[StatusChoices] = (
    (VOUCHER_TYPE_CONTRA, "Contra"),
    (VOUCHER_TYPE_PAYMENT, "Payment"),
    (VOUCHER_TYPE_RECEIPT, "Receipt"),
    (VOUCHER_TYPE_JOURNAL, "Journal"),
    (VOUCHER_TYPE_SALES, "Sales"),
    (VOUCHER_TYPE_PURCHASE, "Purchase"),
)

FIN_VOUCHER_TYPE_META: Final = (
    (VOUCHER_TYPE_PAYMENT, "Payment", "F5", "E"),
    (VOUCHER_TYPE_RECEIPT, "Receipt", "F6", "R"),
    (VOUCHER_TYPE_JOURNAL, "Journal", "F7", "J"),
    (VOUCHER_TYPE_SALES, "Sales", "F8", "S"),
    (VOUCHER_TYPE_PURCHASE, "Purchase", "F9", "P"),
    (VOUCHER_TYPE_CONTRA, "Contra", "F4", "C"),
)

FIN_VOUCHER_PREFIX_MAP: Final[dict[str, str]] = {code: prefix for code, _label, _fkey, prefix in FIN_VOUCHER_TYPE_META}

FIN_MONEY_MODE_SUFFIX: Final[dict[str, str]] = {"cash": "C", "bank": "B"}

FIN_VOUCHER_TYPE_HIDDEN: Final = (VOUCHER_TYPE_SALES, VOUCHER_TYPE_PURCHASE, VOUCHER_TYPE_CONTRA)

FIN_VOUCHER_TYPE_PICKER_META: Final = tuple(
    entry for entry in FIN_VOUCHER_TYPE_META if entry[0] not in FIN_VOUCHER_TYPE_HIDDEN
)

VOUCHER_SUPPLIER_TYPES: Final = (VOUCHER_TYPE_PAYMENT, VOUCHER_TYPE_PURCHASE)
VOUCHER_CUSTOMER_TYPES: Final = (VOUCHER_TYPE_RECEIPT, VOUCHER_TYPE_SALES)

VOUCHER_SIMPLE_SIDES: Final[dict[str, tuple[str, str]]] = {
    VOUCHER_TYPE_PAYMENT: ("credit", "debit"),  # money out of Cash/Bank
    VOUCHER_TYPE_RECEIPT: ("debit", "credit"),  # money into Cash/Bank
    VOUCHER_TYPE_SALES: ("debit", "credit"),  # Dr money or customer, Cr revenue
    VOUCHER_TYPE_PURCHASE: ("credit", "debit"),  # Dr expense, Cr money or supplier
}

SETTLEMENT_CASH: Final = "cash"
SETTLEMENT_CREDIT: Final = "credit"

FIN_SETTLEMENT_MODE_CHOICES: Final[StatusChoices] = (
    (SETTLEMENT_CASH, "Cash"),
    (SETTLEMENT_CREDIT, "Credit"),
)

VOUCHER_SETTLEMENT_TYPES: Final = (VOUCHER_TYPE_SALES, VOUCHER_TYPE_PURCHASE)

VOUCHER_HEADERLESS_TYPES: Final = (VOUCHER_TYPE_JOURNAL,)

FIN_PAYMENT_METHOD_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "bank transfer": ("transaction_ref",),
    "bank": ("transaction_ref",),
    "cheque": ("bank_name", "cheque_no", "cheque_date"),
    "mobile wallet": ("wallet_operator", "transaction_ref"),
}

FIN_PAYMENT_CONDITIONAL_FIELDS: Final = ("bank_name", "cheque_no", "cheque_date", "wallet_operator", "transaction_ref")

FIN_PAYMENT_OPTIONAL_FIELDS: Final = ("transaction_ref",)

FIN_RECEIPT_UPLOAD_TYPES: Final = (VOUCHER_TYPE_PAYMENT, VOUCHER_TYPE_RECEIPT)

GL_CASH_PATH: Final = ("ASSETS", "Current Assets", "Cash")
GL_INVENTORY_PATH: Final = ("ASSETS", "Current Assets", "Inventory")
GL_SALES_TAX_PAYABLE_PATH: Final = ("LIABILITIES", "Current Liabilities", "Sales Tax Payable")
GL_SALES_REVENUE_PATH: Final = ("REVENUE", "Direct Revenue", "Sales Revenue")
GL_SALES_DISCOUNT_PATH: Final = ("REVENUE", "Direct Revenue", "Sales Discount")
GL_SALES_RETURN_PATH: Final = ("REVENUE", "Direct Revenue", "Sales Returns")
GL_COGS_PATH: Final = ("EXPENSES", "Direct Expenses", "Cost of Goods Sold")
GL_GRN_CLEARING_PATH: Final = ("LIABILITIES", "Current Liabilities", "GRN Clearing")
GL_INPUT_TAX_PATH: Final = ("ASSETS", "Current Assets", "Input Sales Tax")
GL_PURCHASE_VARIANCE_PATH: Final = ("EXPENSES", "Direct Expenses", "Purchase Price Variance")
GL_FREIGHT_PATH: Final = ("EXPENSES", "Direct Expenses", "Freight and Carriage")
GL_BROKERS_GROUP_PATH: Final = ("LIABILITIES", "Current Liabilities", "Brokers")
GL_BROKERAGE_PATH: Final = ("EXPENSES", "Direct Expenses", "Brokerage")
GL_WITHHOLDING_PAYABLE_PATH: Final = ("LIABILITIES", "Current Liabilities", "Withholding Tax Payable")
BROKERAGE_WEIGHT_UNIT_KG: Final = "100"
WITHHOLDING_WEIGHT_UNIT_KG: Final = "40"
GL_BROKERS_GROUP_TITLE: Final = "Brokers"
GL_RETAINED_EARNINGS_PATH: Final = ("CAPITAL", "Reserves & Surplus", "Retained Earnings")

GL_INVENTORY_ADJUSTMENT_PATH: Final = ("EXPENSES", "Direct Expenses", "Inventory Adjustment")
GL_OPENING_EQUITY_PATH: Final = ("CAPITAL", "Owner's Capital", "Opening Balance Equity")

INVENTORY_ADJUSTMENT_REASONS: Final[dict[str, str]] = {
    "opening": "Opening catch-up — stock on hand before ledger posting began",
    "adjustment": "Stock adjustment — count difference, shrinkage or write-down",
}

GL_PAYABLES_PARENT: Final = ("LIABILITIES", "Current Liabilities")
GL_PAYABLES_TITLES: Final = ("Payables", "Payable")

CASH_FLOW_OPERATING: Final = "operating"
CASH_FLOW_INVESTING: Final = "investing"
CASH_FLOW_FINANCING: Final = "financing"

CASH_FLOW_SECTION_LABELS: Final[dict[str, str]] = {
    CASH_FLOW_OPERATING: "Operating activities",
    CASH_FLOW_INVESTING: "Investing activities",
    CASH_FLOW_FINANCING: "Financing activities",
}

FIN_ACCOUNT_ROLE_LABELS: Final[dict[str, str]] = {
    "cash": "Cash",
    "bank": "Bank",
    "customer": "Customers",
    "supplier": "Suppliers & Payables",
    "expense": "Expenses",
    "revenue": "Income",
    "other": "Other Accounts",
}

FIN_ACCOUNT_TYPE_ROLES: Final[dict[str, str]] = {
    ACCOUNT_TYPE_LIABILITY: "supplier",
    ACCOUNT_TYPE_EXPENSE: "expense",
    ACCOUNT_TYPE_REVENUE: "revenue",
}

FIN_VOUCHER_HEADER_ROLES: Final[dict[str, tuple[str, ...]]] = {
    VOUCHER_TYPE_PAYMENT: ("cash", "bank"),
    VOUCHER_TYPE_RECEIPT: ("cash", "bank"),
}
FIN_VOUCHER_LINE_ROLES: Final[dict[str, tuple[str, ...]]] = {
    VOUCHER_TYPE_PAYMENT: ("supplier", "expense", "customer"),
    VOUCHER_TYPE_RECEIPT: ("customer", "revenue"),
    VOUCHER_TYPE_SALES: ("revenue",),
    VOUCHER_TYPE_PURCHASE: ("expense", "other"),
}

FIN_SETTLEMENT_HEADER_ROLES: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    VOUCHER_TYPE_SALES: {SETTLEMENT_CASH: ("cash", "bank"), SETTLEMENT_CREDIT: ("customer",)},
    VOUCHER_TYPE_PURCHASE: {SETTLEMENT_CASH: ("cash", "bank"), SETTLEMENT_CREDIT: ("supplier",)},
}

FIN_VOUCHER_PARTY_ROLES: Final[dict[str, tuple[str, ...]]] = {
    VOUCHER_TYPE_SALES: ("customer",),
    VOUCHER_TYPE_PURCHASE: ("supplier",),
}

FIN_VOUCHER_LABELS: Final[dict[str, dict[str, str]]] = {
    VOUCHER_TYPE_PAYMENT: {"header": "Paid From", "line": "Paid To"},
    VOUCHER_TYPE_RECEIPT: {"header": "Received In", "line": "Received From"},
    VOUCHER_TYPE_SALES: {
        "header": "Received In",
        "header_credit": "Sold To",
        "line": "Sales Account",
        "party": "Sold To",
        "settlement": "Receipt Method",
    },
    VOUCHER_TYPE_PURCHASE: {
        "header": "Paid From",
        "header_credit": "Purchase From",
        "line": "Purchase Account",
        "party": "Purchase From",
        "settlement": "Payment Method",
    },
}

FIN_VOUCHER_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_CREATED, "Created"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_VERIFIED, "Verified"),
    (STATUS_DOUBLE_VERIFIED, "Double Verified"),
)

YES_NO_CHOICES: Final[StatusChoices] = (
    (YES, "Yes"),
    (NO, "No"),
)

INVENTORY_IMPORTED_LOCAL: Final = "L"
INVENTORY_IMPORTED_IMPORTED: Final = "I"
INVENTORY_TYPE_INVENTORY: Final = "I"
INVENTORY_TYPE_FIXED_ASSET: Final = "F"
LEDGER_OPENING: Final = "OPENING"
LEDGER_RECEIVE: Final = "RECEIVE"
LEDGER_PURCHASE_RETURN: Final = "PURCHASE_RETURN"
LEDGER_SALE: Final = "SALE"
LEDGER_SALE_RETURN: Final = "SALE_RETURN"
LEDGER_ADJUSTMENT: Final = "ADJUSTMENT"
LEDGER_REVERSAL: Final = "REVERSAL"
CUSTOMER_LEDGER_PURCHASE: Final = "PURCHASE"
CUSTOMER_LEDGER_CASH_PAYMENT: Final = "CASH_PAYMENT"
CUSTOMER_LEDGER_RETURN: Final = "RETURN"
PAY_MODE_CASH: Final = "cash"
PAY_MODE_CARD: Final = "card"
PAY_MODE_ONLINE: Final = "online"
PAY_MODE_CREDIT: Final = "credit"

INV_IMPORTED_CHOICES: Final[StatusChoices] = (
    (INVENTORY_IMPORTED_IMPORTED, "Imported"),
    (INVENTORY_IMPORTED_LOCAL, "Local"),
)

INV_ITEM_TYPE_CHOICES: Final[StatusChoices] = (
    (INVENTORY_TYPE_INVENTORY, "Inventory"),
    (INVENTORY_TYPE_FIXED_ASSET, "Fixed Asset"),
)

INVENTORY_KIND_PRODUCT: Final = "P"
INVENTORY_KIND_SERVICE: Final = "S"

INV_ITEM_KIND_CHOICES: Final[StatusChoices] = (
    (INVENTORY_KIND_PRODUCT, "Product"),
    (INVENTORY_KIND_SERVICE, "Service"),
)

INV_TRANSACTION_TYPE_CHOICES: Final[StatusChoices] = (
    (LEDGER_OPENING, "Opening"),
    (LEDGER_RECEIVE, "Receive"),
    (LEDGER_PURCHASE_RETURN, "Purchase Return"),
    (LEDGER_SALE, "Sale"),
    (LEDGER_SALE_RETURN, "Sale Return"),
    (LEDGER_ADJUSTMENT, "Adjustment"),
    (LEDGER_REVERSAL, "Reversal"),
)

INV_CUSTOMER_LEDGER_TRANSACTION_TYPE_CHOICES: Final[StatusChoices] = (
    (CUSTOMER_LEDGER_PURCHASE, "Purchase"),
    (CUSTOMER_LEDGER_CASH_PAYMENT, "Cash Payment"),
    (CUSTOMER_LEDGER_RETURN, "Return"),
)

INV_POS_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_CREATED, "Created"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_POSTED, "Posted"),
    (STATUS_CANCELLED, "Cancelled"),
    (STATUS_RETURNED, "Returned"),
    (STATUS_PARTIAL_RETURNED, "Partial Returned"),
)

INV_PURCHASE_ORDER_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_DRAFT, "Draft"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_PARTIALLY_INVOICED, "Partially Invoiced"),
    (STATUS_FULLY_INVOICED, "Fully Invoiced"),
    (STATUS_CLOSED, "Closed"),
    (STATUS_CANCELLED, "Cancelled"),
)

INV_SALES_ORDER_STATUS_CHOICES: Final[StatusChoices] = INV_PURCHASE_ORDER_STATUS_CHOICES

INV_ORDER_OPEN_STATUSES: Final = (STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED)

INV_PURCHASE_INVOICE_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_DRAFT, "Draft"),
    (STATUS_POSTED, "Posted"),
    (STATUS_REVERSED, "Reversed"),
    (STATUS_CANCELLED, "Cancelled"),
)

INV_PURCHASE_BILL_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_POSTED, "Posted"),
    (STATUS_REVERSED, "Reversed"),
)

INV_PO_CANCEL_REASONS: Final[StatusChoices] = (
    ("entered_in_error", "Entered in error"),
    ("wrong_supplier", "Raised on the wrong supplier"),
    ("duplicate", "Duplicate of another order"),
    ("rate_renegotiated", "Cancelled after the rate was renegotiated"),
    ("no_longer_required", "No longer required"),
)

INV_PO_CLOSE_SHORT_REASONS: Final[StatusChoices] = (
    ("supplier_short", "Supplier could not supply the balance"),
    ("season_over", "Crop or season finished -- no more available"),
    ("quality_rejected", "Quality rejected -- balance not wanted"),
    ("over_ordered", "Ordered in excess by mistake"),
    ("accepted_as_final", "Delivered short and accepted as final"),
)

INV_BARDANA_MILL: Final = "mill"
INV_BARDANA_PARTY: Final = "party"
INV_BARDANA_RETURNABLE: Final = "returnable"
INV_BARDANA_OWNERSHIP_CHOICES: Final[StatusChoices] = (
    (INV_BARDANA_MILL, "Mill's own"),
    (INV_BARDANA_PARTY, "Party's"),
    (INV_BARDANA_RETURNABLE, "Returnable"),
)
INV_BARDANA_NOT_PURCHASED: Final = (INV_BARDANA_PARTY, INV_BARDANA_RETURNABLE)

INV_REVERSAL_REASONS: Final[StatusChoices] = (
    ("entered_in_error", "Entered in error"),
    ("wrong_quantity", "Wrong quantity entered"),
    ("wrong_rate", "Wrong rate entered"),
    ("wrong_supplier", "Wrong supplier selected"),
    ("duplicate", "Duplicate entry"),
    ("wrong_date", "Wrong date or period"),
    ("cancelled_by_supplier", "Cancelled by the supplier"),
)

CONF_PO_APPROVAL_LIMIT_KEY: Final = "inventory.purchase_order.approval_limit"
CONF_PO_APPROVAL_LIMIT_DEFAULT: Final = "500000.00"

INV_BILL_MATCH_TOLERANCE_PERCENT: Final = "2.00"

INV_RETURN_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_DRAFT, "Draft"),
    (STATUS_CREATED, "Created"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_POSTED, "Posted"),
    (STATUS_REVERSED, "Reversed"),
    (STATUS_CANCELLED, "Cancelled"),
)
INV_RETURN_DRAFT_STATUSES: Final = (STATUS_DRAFT, STATUS_CREATED, STATUS_SUBMITTED)
INV_PURCHASE_RETURN_PREFIX: Final = "PR"

PAY_MODE_CHOICES: Final[StatusChoices] = (
    (PAY_MODE_CASH, "Cash"),
    (PAY_MODE_CARD, "Card"),
    (PAY_MODE_ONLINE, "Online"),
    (PAY_MODE_CREDIT, "Credit"),
)

FIN_ACCOUNT_TYPE_CODE_MAP: Final[dict[str, str]] = {
    ACCOUNT_TYPE_ASSET: "A",
    ACCOUNT_TYPE_LIABILITY: "L",
    ACCOUNT_TYPE_REVENUE: "R",
    ACCOUNT_TYPE_EXPENSE: "E",
}

COMPLETION_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_COMPLETED, "Completed"),
    (STATUS_ONGOING, "Ongoing"),
)

ALLOWANCE_DEDUCTION_TYPE_CHOICES: Final[StatusChoices] = (
    (ALLOWANCE, "Allowance"),
    (DEDUCTION, "Deduction"),
)

QUALIFICATION_TYPE_CHOICES: Final[StatusChoices] = (
    (QUALIFICATION_DEGREE, "Degree"),
    (QUALIFICATION_DIPLOMA, "Diploma"),
    (QUALIFICATION_CERTIFICATE, "Certificate"),
)

SCOPE_CHOICES: Final[StatusChoices] = (
    (SCOPE_LOCAL, "Local"),
    (SCOPE_GLOBAL, "Global"),
)

COMMON_STATUS_LABELS: Final[dict[str, str]] = {
    value: label
    for value, label in WORKFLOW_STATUS_CHOICES + RECORD_STATUS_CHOICES + COMPLETION_STATUS_CHOICES
}


ACTION_INDEX: Final[str] = "index"
ACTION_VIEW: Final[str] = "view"
ACTION_ADD: Final[str] = "add"
ACTION_EDIT: Final[str] = "edit"
ACTION_DELETE: Final[str] = "delete"
ACTION_APPROVE: Final[str] = "approve"
ACTION_REVERSE: Final[str] = "reverse"

PAGE_ACTIONS: Final[tuple[str, ...]] = (
    ACTION_INDEX,
    ACTION_VIEW,
    ACTION_ADD,
    ACTION_EDIT,
    ACTION_DELETE,
    ACTION_APPROVE,
    ACTION_REVERSE,
)

ACTION_LABELS: Final[dict[str, str]] = {
    ACTION_INDEX: "List",
    ACTION_VIEW: "View",
    ACTION_ADD: "Add",
    ACTION_EDIT: "Edit",
    ACTION_DELETE: "Delete",
    ACTION_APPROVE: "Approve",
    ACTION_REVERSE: "Reverse",
}


PRD_LEVEL_GROUP: Final[int] = 1
PRD_LEVEL_SUB_GROUP: Final[int] = 2
PRD_LEVEL_ITEM: Final[int] = 3

PRD_LEVEL_CHOICES: Final[tuple[tuple[int, str], ...]] = (
    (PRD_LEVEL_GROUP, "Group"),
    (PRD_LEVEL_SUB_GROUP, "Sub Group"),
    (PRD_LEVEL_ITEM, "Item"),
)

PRD_SEGMENT_WIDTHS: Final[dict[int, int]] = {
    PRD_LEVEL_GROUP: 2,
    PRD_LEVEL_SUB_GROUP: 2,
    PRD_LEVEL_ITEM: 3,
}

PRD_SPEC_RAW_ITEM: Final = "raw_item"
PRD_SPEC_RAW_PACKING: Final = "raw_packing"
PRD_SPEC_FINISH_ITEM: Final = "finish_item"
PRD_SPEC_FINISH_PACKING: Final = "finish_packing"
PRD_SPEC_BYPRODUCT: Final = "byproduct"
PRD_SPEC_SERVICE_ITEM: Final = "service_item"
PRD_SPEC_WAGE_ITEM: Final = "wage_item"

PRD_SPECIFICATION_CHOICES: Final[StatusChoices] = (
    (PRD_SPEC_RAW_ITEM, "Raw Item"),
    (PRD_SPEC_RAW_PACKING, "Raw Packing"),
    (PRD_SPEC_FINISH_ITEM, "Finish Item"),
    (PRD_SPEC_FINISH_PACKING, "Finish Packing"),
    (PRD_SPEC_BYPRODUCT, "By-Product"),
    (PRD_SPEC_SERVICE_ITEM, "Service Item"),
    (PRD_SPEC_WAGE_ITEM, "Wage Item"),
)

PRD_SPEC_RULES: Final[dict[str, dict[str, bool]]] = {
    PRD_SPEC_RAW_ITEM: {"can_buy": True, "can_produce": False, "can_sell": True, "keeps_stock": True},
    PRD_SPEC_RAW_PACKING: {"can_buy": True, "can_produce": False, "can_sell": False, "keeps_stock": True},
    PRD_SPEC_FINISH_ITEM: {"can_buy": False, "can_produce": True, "can_sell": True, "keeps_stock": True},
    PRD_SPEC_FINISH_PACKING: {"can_buy": True, "can_produce": False, "can_sell": False, "keeps_stock": True},
    PRD_SPEC_BYPRODUCT: {"can_buy": False, "can_produce": True, "can_sell": True, "keeps_stock": True},
    PRD_SPEC_SERVICE_ITEM: {"can_buy": True, "can_produce": False, "can_sell": True, "keeps_stock": False},
    PRD_SPEC_WAGE_ITEM: {"can_buy": False, "can_produce": False, "can_sell": False, "keeps_stock": False},
}

PRD_BUYABLE_SPECS: Final[tuple[str, ...]] = tuple(
    spec for spec, rules in PRD_SPEC_RULES.items() if rules["can_buy"]
)
PRD_STOCKED_SPECS: Final[tuple[str, ...]] = tuple(
    spec for spec, rules in PRD_SPEC_RULES.items() if rules["keeps_stock"]
)
PRD_SELLABLE_SPECS: Final[tuple[str, ...]] = tuple(
    spec for spec, rules in PRD_SPEC_RULES.items() if rules["can_sell"]
)
PRD_PACKABLE_SPECS: Final[tuple[str, ...]] = (PRD_SPEC_FINISH_ITEM, PRD_SPEC_BYPRODUCT)

PRD_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_ACTIVE, "Active"),
    (STATUS_INACTIVE, "Inactive"),
    (STATUS_CLOSED, "Closed"),
)

PRD_UNIT_KG: Final = "kg"
PRD_UNIT_PIECE: Final = "piece"
PRD_UNIT_MOUND: Final = "mound"

PRD_UNIT_CHOICES: Final[StatusChoices] = (
    (PRD_UNIT_KG, "Kg"),
    (PRD_UNIT_PIECE, "Piece"),
    (PRD_UNIT_MOUND, "Mound"),
)

PRD_UNIT_BASE_WEIGHT: Final[dict[str, str]] = {
    PRD_UNIT_KG: "1",
    PRD_UNIT_MOUND: "40",
}

PRD_LEDGER_OPENING: Final = "opening"
PRD_LEDGER_PURCHASE: Final = "purchase"
PRD_LEDGER_PURCHASE_RETURN: Final = "purchase_return"
PRD_LEDGER_SALE: Final = "sale"
PRD_LEDGER_SALE_RETURN: Final = "sale_return"
PRD_LEDGER_PRODUCTION_IN: Final = "production_in"
PRD_LEDGER_PRODUCTION_OUT: Final = "production_out"
PRD_LEDGER_PACKING_OUT: Final = "packing_out"
PRD_LEDGER_ADJUSTMENT: Final = "adjustment"

PRD_LEDGER_SOURCE_CHOICES: Final[StatusChoices] = (
    (PRD_LEDGER_OPENING, "Opening Balance"),
    (PRD_LEDGER_PURCHASE, "Purchase"),
    (PRD_LEDGER_PURCHASE_RETURN, "Purchase Return"),
    (PRD_LEDGER_SALE, "Sale"),
    (PRD_LEDGER_SALE_RETURN, "Sale Return"),
    (PRD_LEDGER_PRODUCTION_IN, "Production Receipt"),
    (PRD_LEDGER_PRODUCTION_OUT, "Grinding Issue"),
    (PRD_LEDGER_PACKING_OUT, "Packing Consumption"),
    (PRD_LEDGER_ADJUSTMENT, "Stock Adjustment"),
)


GODOWN_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_ACTIVE, "Active"),
    (STATUS_INACTIVE, "Inactive"),
)

GODOWN_TYPE_MILL: Final = "mill"
GODOWN_TYPE_STORE: Final = "store"
GODOWN_TYPE_SILO: Final = "silo"

GODOWN_TYPE_CHOICES: Final[StatusChoices] = (
    (GODOWN_TYPE_MILL, "Mill"),
    (GODOWN_TYPE_STORE, "Store"),
    (GODOWN_TYPE_SILO, "Silo"),
)


PRODUCTION_GRINDING_PREFIX: Final = "WG"
PRODUCTION_CONVERSION_PREFIX: Final = "PC"

PRODUCTION_OPEN_STOCK_PACK_NAME: Final = "Open Stock without Bardana"
