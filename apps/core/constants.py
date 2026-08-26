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
# An order nobody expects the rest of any more. Distinct from cancelled, which
# means nothing arrived at all: a short-closed order was part delivered and the
# balance was deliberately written off rather than left hanging for ever.
STATUS_CLOSED_SHORT: Final = "closed_short"
# A supplier bill, from entered to matched against what actually arrived.
STATUS_MATCHED: Final = "matched"
STATUS_REVERSED: Final = "reversed"

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

# Cash and bank vouchers of the same type number in separate books: EC-000001
# runs alongside EB-000001, so each book reads as its own unbroken sequence.
FIN_MONEY_MODE_SUFFIX: Final[dict[str, str]] = {"cash": "C", "bank": "B"}

# Voucher types kept off the manual entry screen: Sales is posted from a POS
# sale, Purchase from a GRN, and Contra is not entered here for now. The types
# stay valid everywhere else (numbering, lists, posting, reports).
FIN_VOUCHER_TYPE_HIDDEN: Final = (VOUCHER_TYPE_SALES, VOUCHER_TYPE_PURCHASE, VOUCHER_TYPE_CONTRA)

FIN_VOUCHER_TYPE_PICKER_META: Final = tuple(
    entry for entry in FIN_VOUCHER_TYPE_META if entry[0] not in FIN_VOUCHER_TYPE_HIDDEN
)

# Account-nature groups: supplier (payable) vs customer (receivable) voucher types.
VOUCHER_SUPPLIER_TYPES: Final = (VOUCHER_TYPE_PAYMENT, VOUCHER_TYPE_PURCHASE)
VOUCHER_CUSTOMER_TYPES: Final = (VOUCHER_TYPE_RECEIPT, VOUCHER_TYPE_SALES)

# Simple-mode vouchers hide the debit/credit choice: the voucher type fixes both
# sides. The header account is the money leg (Cash/Bank), every grid line is the
# reason leg, and each line carries a single positive amount.
# {voucher_type: (header_side, line_side)}
VOUCHER_SIMPLE_SIDES: Final[dict[str, tuple[str, str]]] = {
    VOUCHER_TYPE_PAYMENT: ("credit", "debit"),  # money out of Cash/Bank
    VOUCHER_TYPE_RECEIPT: ("debit", "credit"),  # money into Cash/Bank
    VOUCHER_TYPE_SALES: ("debit", "credit"),  # Dr money or customer, Cr revenue
    VOUCHER_TYPE_PURCHASE: ("credit", "debit"),  # Dr expense, Cr money or supplier
}

# Sales and Purchase settle either on the spot (money account) or on account
# (customer receivable / supplier payable). The mode picks the header account.
SETTLEMENT_CASH: Final = "cash"
SETTLEMENT_CREDIT: Final = "credit"

FIN_SETTLEMENT_MODE_CHOICES: Final[StatusChoices] = (
    (SETTLEMENT_CASH, "Cash"),
    (SETTLEMENT_CREDIT, "Credit"),
)

VOUCHER_SETTLEMENT_TYPES: Final = (VOUCHER_TYPE_SALES, VOUCHER_TYPE_PURCHASE)

# A Journal is only its lines: no money account heads it, so no payment method
# and no single amount either — the grid carries both sides.
VOUCHER_HEADERLESS_TYPES: Final = (VOUCHER_TYPE_JOURNAL,)

# Extra voucher header fields each payment method needs, keyed by a lowercased
# PaymentMethod.title. Methods missing here (Cash, …) collect nothing extra; the
# listed fields are both shown and required, and everything else is blanked out.
FIN_PAYMENT_METHOD_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    # A transfer already moves through the voucher's bank account, so the bank is
    # known; only the reference the bank gave it is collected.
    "bank transfer": ("transaction_ref",),
    "bank": ("transaction_ref",),
    "cheque": ("bank_name", "cheque_no", "cheque_date"),
    "mobile wallet": ("wallet_operator", "transaction_ref"),
}

# Every conditional field, in on-screen order — the ones hidden for a method.
FIN_PAYMENT_CONDITIONAL_FIELDS: Final = ("bank_name", "cheque_no", "cheque_date", "wallet_operator", "transaction_ref")

# Shown for their method but never demanded: the bank reference often reaches the
# office after the voucher is written.
FIN_PAYMENT_OPTIONAL_FIELDS: Final = ("transaction_ref",)

# Voucher types that can carry a scanned bank slip, and only while the money
# side is a bank account — cash across the counter produces no such document.
FIN_RECEIPT_UPLOAD_TYPES: Final = (VOUCHER_TYPE_PAYMENT, VOUCHER_TYPE_RECEIPT)

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
# Goods are in the godown long before the supplier's bill turns up. Their value
# has to sit somewhere in the meantime, and it sits here: a liability that says
# "received, not yet invoiced". The bill then debits it away and credits the
# real payable, so the two net to zero. Whatever is left in this account at any
# moment is exactly the goods received that nobody has billed for -- without it
# payables are understated and there is no way to say by how much.
GL_GRN_CLEARING_PATH: Final = ("LIABILITIES", "Current Liabilities", "GRN Clearing")
# Sales tax paid to a supplier is money the business gets back, so it is an
# asset until it is set off, not a cost of the goods. Loading it onto stock
# would overstate both inventory and, later, cost of sales.
GL_INPUT_TAX_PATH: Final = ("ASSETS", "Current Assets", "Input Sales Tax")
# Where a supplier bill that disagrees with the goods receipt lands. The stock
# was already valued when it arrived; re-valuing it now would rewrite the cost
# of units that may already have been sold, so the difference is taken to the
# profit and loss account instead.
GL_PURCHASE_VARIANCE_PATH: Final = ("EXPENSES", "Direct Expenses", "Purchase Price Variance")
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
    "supplier": "Suppliers & Payables",
    "expense": "Expenses",
    "revenue": "Income",
    "other": "Other Accounts",
}

# Fallback role by account_type, for accounts outside Cash/Bank/Receivables.
FIN_ACCOUNT_TYPE_ROLES: Final[dict[str, str]] = {
    ACCOUNT_TYPE_LIABILITY: "supplier",
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
    # "customer" included: money is also paid out to a customer — a refund, or
    # an advance being returned — which lands on the receivable ledger.
    VOUCHER_TYPE_PAYMENT: ("supplier", "expense", "customer"),
    VOUCHER_TYPE_RECEIPT: ("customer", "revenue"),
    VOUCHER_TYPE_SALES: ("revenue",),
    VOUCHER_TYPE_PURCHASE: ("expense", "other"),
}

# Settlement mode overrides the header roles for Sales and Purchase.
FIN_SETTLEMENT_HEADER_ROLES: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    VOUCHER_TYPE_SALES: {SETTLEMENT_CASH: ("cash", "bank"), SETTLEMENT_CREDIT: ("customer",)},
    VOUCHER_TYPE_PURCHASE: {SETTLEMENT_CASH: ("cash", "bank"), SETTLEMENT_CREDIT: ("supplier",)},
}

# On a cash sale/purchase the header is a money account, so the counterparty is
# recorded separately in party_account_no. On credit it *is* the header account.
FIN_VOUCHER_PARTY_ROLES: Final[dict[str, tuple[str, ...]]] = {
    VOUCHER_TYPE_SALES: ("customer",),
    VOUCHER_TYPE_PURCHASE: ("supplier",),
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
# Stock taken back out because the movement that put it in was withdrawn. Kept
# apart from an adjustment: an adjustment is a count difference the business
# discovered, a reversal is an entry the business retracted, and reading the
# item ledger is a great deal easier when the two are not the same word.
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

# What is being sold: something stocked and counted, or labour that never
# carries a quantity. Separate from INV_ITEM_TYPE_CHOICES, which says how an
# item is held on the balance sheet.
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
    (STATUS_RAISED, "Raised"),
    (STATUS_PARTIAL_RECEIVED, "Partial Received"),
    (STATUS_FULLY_RECEIVED, "Fully Received"),
    (STATUS_CLOSED_SHORT, "Closed"),
    (STATUS_CANCELLED, "Cancelled"),
)

INV_PURCHASE_BILL_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_POSTED, "Posted"),
    (STATUS_REVERSED, "Reversed"),
)

# Why an order was abandoned. A free-text box here fills up with "cancelled" and
# tells nobody anything six months later, so the reason is picked from a list
# and the list is short enough that the honest answer is always on it.
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

# Why a posted document was reversed. A reversal without one is unusable to
# whoever reads the books afterwards, which is the whole point of keeping it.
INV_REVERSAL_REASONS: Final[StatusChoices] = (
    ("entered_in_error", "Entered in error"),
    ("wrong_quantity", "Wrong quantity entered"),
    ("wrong_rate", "Wrong rate entered"),
    ("wrong_supplier", "Wrong supplier selected"),
    ("duplicate", "Duplicate entry"),
    ("wrong_date", "Wrong date or period"),
    ("cancelled_by_supplier", "Cancelled by the supplier"),
)

# Above this the order is a commitment somebody senior has to agree to, so it
# stays a draft until they do. Held as a setting rather than a constant because
# the figure is a matter of company policy, not of software.
CONF_PO_APPROVAL_LIMIT_KEY: Final = "inventory.purchase_order.approval_limit"
CONF_PO_APPROVAL_LIMIT_DEFAULT: Final = "500000.00"

# How far a supplier's bill may drift from the value of the goods that were
# received against it before the system stops accepting it without a second
# pair of eyes. Two percent is the usual commercial rounding; beyond that
# somebody is billing for something that did not arrive.
INV_BILL_MATCH_TOLERANCE_PERCENT: Final = "2.00"

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
# Committing money on somebody else's behalf, and unwinding a posted entry.
# Held apart from "edit" so the person who raises a document is not, by that
# fact alone, the person who approves it or withdraws it.
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
