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

ACCOUNT_LEDGER_GENERAL: Final = "G"
ACCOUNT_LEDGER_SUBSIDIARY: Final = "S"

BALANCE_INCOME_BALANCE_SHEET: Final = "B"
BALANCE_INCOME_INCOME_STATEMENT: Final = "I"

ACCOUNT_NATURE_DEBIT: Final = "D"
ACCOUNT_NATURE_CREDIT: Final = "C"

VOUCHER_TYPE_PAYMENT: Final = "PV"
VOUCHER_TYPE_RECEIPT: Final = "RV"

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

FIN_BALANCE_INCOME_CHOICES: Final[StatusChoices] = (
    (BALANCE_INCOME_BALANCE_SHEET, "Balance Sheet"),
    (BALANCE_INCOME_INCOME_STATEMENT, "Income Statement"),
)

FIN_ACCOUNT_NATURE_CHOICES: Final[StatusChoices] = (
    (ACCOUNT_NATURE_DEBIT, "Debit"),
    (ACCOUNT_NATURE_CREDIT, "Credit"),
)

FIN_VOUCHER_TYPE_CHOICES: Final[StatusChoices] = (
    (VOUCHER_TYPE_PAYMENT, "Payment Voucher"),
    (VOUCHER_TYPE_RECEIPT, "Receipt Voucher"),
)

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
