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

# Chart of Accounts tree: five top-level roots (adds Capital over the 4 posting types).
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

# Tally-style voucher shortcuts for the add-voucher picker: (code, label, F-key, prefix)
# Payment listed first: it is the most common voucher and the default selection.
FIN_VOUCHER_TYPE_META: Final = (
    (VOUCHER_TYPE_PAYMENT, "Payment", "F5", "E"),
    (VOUCHER_TYPE_RECEIPT, "Receipt", "F6", "R"),
    (VOUCHER_TYPE_JOURNAL, "Journal", "F7", "J"),
    (VOUCHER_TYPE_SALES, "Sales", "F8", "S"),
    (VOUCHER_TYPE_PURCHASE, "Purchase", "F9", "P"),
    (VOUCHER_TYPE_CONTRA, "Contra", "F4", "C"),
)

FIN_VOUCHER_PREFIX_MAP: Final[dict[str, str]] = {code: prefix for code, _label, _fkey, prefix in FIN_VOUCHER_TYPE_META}

# Voucher types kept off the manual entry screen: Sales is posted from a POS
# sale, Purchase from a GRN, and Contra is not entered here for now. The types
# stay valid everywhere else (numbering, lists, posting, reports).
FIN_VOUCHER_TYPE_HIDDEN: Final = (VOUCHER_TYPE_SALES, VOUCHER_TYPE_PURCHASE, VOUCHER_TYPE_CONTRA)

FIN_VOUCHER_TYPE_PICKER_META: Final = tuple(
    entry for entry in FIN_VOUCHER_TYPE_META if entry[0] not in FIN_VOUCHER_TYPE_HIDDEN
)

# Account-nature groups: vendor (payable) vs customer (receivable) voucher types.
VOUCHER_VENDOR_TYPES: Final = (VOUCHER_TYPE_PAYMENT, VOUCHER_TYPE_PURCHASE)
VOUCHER_CUSTOMER_TYPES: Final = (VOUCHER_TYPE_RECEIPT, VOUCHER_TYPE_SALES)

# Simple-mode vouchers hide the debit/credit choice: the voucher type fixes both
# sides. The header account is the money leg (Cash/Bank), every grid line is the
# reason leg, and each line carries a single positive amount.
# {voucher_type: (header_side, line_side)}
VOUCHER_SIMPLE_SIDES: Final[dict[str, tuple[str, str]]] = {
    VOUCHER_TYPE_PAYMENT: ("credit", "debit"),  # money out of Cash/Bank
    VOUCHER_TYPE_RECEIPT: ("debit", "credit"),  # money into Cash/Bank
    VOUCHER_TYPE_SALES: ("debit", "credit"),  # Dr money or customer, Cr revenue
    VOUCHER_TYPE_PURCHASE: ("credit", "debit"),  # Dr expense, Cr money or vendor
}

# Sales and Purchase settle either on the spot (money account) or on account
# (customer receivable / vendor payable). The mode picks the header account.
SETTLEMENT_CASH: Final = "cash"
SETTLEMENT_CREDIT: Final = "credit"

FIN_SETTLEMENT_MODE_CHOICES: Final[StatusChoices] = (
    (SETTLEMENT_CASH, "Cash"),
    (SETTLEMENT_CREDIT, "Credit"),
)

VOUCHER_SETTLEMENT_TYPES: Final = (VOUCHER_TYPE_SALES, VOUCHER_TYPE_PURCHASE)

# Extra voucher header fields each payment method needs, keyed by a lowercased
# PaymentMethod.title. Methods missing here (Cash, …) collect nothing extra; the
# listed fields are both shown and required, and everything else is blanked out.
FIN_PAYMENT_METHOD_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "bank transfer": ("bank_name", "transaction_ref"),
    "cheque": ("bank_name", "cheque_no", "cheque_date"),
    "mobile wallet": ("wallet_operator", "transaction_ref"),
}

# Every conditional field, in on-screen order — the ones hidden for a method.
FIN_PAYMENT_CONDITIONAL_FIELDS: Final = ("bank_name", "cheque_no", "cheque_date", "wallet_operator", "transaction_ref")

# Chart-of-accounts titles the automatic sales posting needs. Each entry is the
# (root, sub-heading, leaf) path used to find-or-create the account, so a fresh
# install posts without any manual chart setup.
GL_CASH_PATH: Final = ("ASSETS", "Current Assets", "Cash")
GL_INVENTORY_PATH: Final = ("ASSETS", "Current Assets", "Inventory")
GL_SALES_TAX_PAYABLE_PATH: Final = ("LIABILITIES", "Current Liabilities", "Sales Tax Payable")
GL_SALES_REVENUE_PATH: Final = ("REVENUE", "Direct Revenue", "Sales Revenue")
# Sales discount and sales returns are contra-revenue: debit-balance accounts
# under REVENUE, so they net against Sales Revenue on the income statement
# instead of being misreported as expenses.
GL_SALES_DISCOUNT_PATH: Final = ("REVENUE", "Direct Revenue", "Sales Discount")
GL_SALES_RETURN_PATH: Final = ("REVENUE", "Direct Revenue", "Sales Returns")
GL_COGS_PATH: Final = ("EXPENSES", "Direct Expenses", "Cost of Goods Sold")
GL_RETAINED_EARNINGS_PATH: Final = ("CAPITAL", "Reserves & Surplus", "Retained Earnings")

# Counterparts for an inventory reconciliation. A genuine count difference is a
# trading loss or gain; stock that predates general-ledger posting is not — it
# is brought on to the books against opening equity so it never touches profit.
GL_INVENTORY_ADJUSTMENT_PATH: Final = ("EXPENSES", "Direct Expenses", "Inventory Adjustment")
GL_OPENING_EQUITY_PATH: Final = ("CAPITAL", "Owner's Capital", "Opening Balance Equity")

INVENTORY_ADJUSTMENT_REASONS: Final[dict[str, str]] = {
    "opening": "Opening catch-up — stock on hand before ledger posting began",
    "adjustment": "Stock adjustment — count difference, shrinkage or write-down",
}

# Supplier control account. Both spellings are accepted so an existing
# hand-built chart is reused instead of gaining a near-duplicate heading.
GL_PAYABLES_PARENT: Final = ("LIABILITIES", "Current Liabilities")
GL_PAYABLES_TITLES: Final = ("Payables", "Payable")

# Cash-flow activity buckets, by the account type on the other side of the entry.
CASH_FLOW_OPERATING: Final = "operating"
CASH_FLOW_INVESTING: Final = "investing"
CASH_FLOW_FINANCING: Final = "financing"

CASH_FLOW_SECTION_LABELS: Final[dict[str, str]] = {
    CASH_FLOW_OPERATING: "Operating activities",
    CASH_FLOW_INVESTING: "Investing activities",
    CASH_FLOW_FINANCING: "Financing activities",
}

# Business role of a postable account, and the optgroup caption it gets in the
# voucher pickers. Roles come from the account's place in the chart of accounts,
# not account_type alone: customer ledgers sit under Receivables, so their
# account_type is "asset" and cannot be told apart from any other asset.
FIN_ACCOUNT_ROLE_LABELS: Final[dict[str, str]] = {
    "cash": "Cash",
    "bank": "Bank",
    "customer": "Customers",
    "vendor": "Vendors & Payables",
    "expense": "Expenses",
    "revenue": "Income",
    "other": "Other Accounts",
}

# Fallback role by account_type, for accounts outside Cash/Bank/Receivables.
FIN_ACCOUNT_TYPE_ROLES: Final[dict[str, str]] = {
    ACCOUNT_TYPE_LIABILITY: "vendor",
    ACCOUNT_TYPE_EXPENSE: "expense",
    ACCOUNT_TYPE_REVENUE: "revenue",
}

# Which account roles each voucher type accepts, per side.
# Absent voucher type (Journal/Contra) => every role allowed.
FIN_VOUCHER_HEADER_ROLES: Final[dict[str, tuple[str, ...]]] = {
    VOUCHER_TYPE_PAYMENT: ("cash", "bank"),
    VOUCHER_TYPE_RECEIPT: ("cash", "bank"),
}
FIN_VOUCHER_LINE_ROLES: Final[dict[str, tuple[str, ...]]] = {
    VOUCHER_TYPE_PAYMENT: ("vendor", "expense"),
    VOUCHER_TYPE_RECEIPT: ("customer", "revenue"),
    VOUCHER_TYPE_SALES: ("revenue",),
    VOUCHER_TYPE_PURCHASE: ("expense", "other"),
}

# Settlement mode overrides the header roles for Sales and Purchase.
FIN_SETTLEMENT_HEADER_ROLES: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    VOUCHER_TYPE_SALES: {SETTLEMENT_CASH: ("cash", "bank"), SETTLEMENT_CREDIT: ("customer",)},
    VOUCHER_TYPE_PURCHASE: {SETTLEMENT_CASH: ("cash", "bank"), SETTLEMENT_CREDIT: ("vendor",)},
}

# On a cash sale/purchase the header is a money account, so the counterparty is
# recorded separately in party_account_no. On credit it *is* the header account.
FIN_VOUCHER_PARTY_ROLES: Final[dict[str, tuple[str, ...]]] = {
    VOUCHER_TYPE_SALES: ("customer",),
    VOUCHER_TYPE_PURCHASE: ("vendor",),
}

# On-screen captions per voucher type. "header_credit" overrides "header" when
# the voucher settles on credit; keys are read by the voucher form's JS too.
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

INV_TRANSACTION_TYPE_CHOICES: Final[StatusChoices] = (
    (LEDGER_OPENING, "Opening"),
    (LEDGER_RECEIVE, "Receive"),
    (LEDGER_PURCHASE_RETURN, "Purchase Return"),
    (LEDGER_SALE, "Sale"),
    (LEDGER_SALE_RETURN, "Sale Return"),
    (LEDGER_ADJUSTMENT, "Adjustment"),
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
    (STATUS_RAISED, "Raised"),
    (STATUS_PARTIAL_RECEIVED, "Partial Received"),
    (STATUS_FULLY_RECEIVED, "Fully Received"),
    (STATUS_CANCELLED, "Cancelled"),
)

INV_RETURN_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_CREATED, "Created"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_POSTED, "Posted"),
    (STATUS_CANCELLED, "Cancelled"),
)

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


# --- Page-level access-control actions ---
ACTION_INDEX: Final[str] = "index"
ACTION_VIEW: Final[str] = "view"
ACTION_ADD: Final[str] = "add"
ACTION_EDIT: Final[str] = "edit"
ACTION_DELETE: Final[str] = "delete"

PAGE_ACTIONS: Final[tuple[str, ...]] = (
    ACTION_INDEX,
    ACTION_VIEW,
    ACTION_ADD,
    ACTION_EDIT,
    ACTION_DELETE,
)

ACTION_LABELS: Final[dict[str, str]] = {
    ACTION_INDEX: "List",
    ACTION_VIEW: "View",
    ACTION_ADD: "Add",
    ACTION_EDIT: "Edit",
    ACTION_DELETE: "Delete",
}
