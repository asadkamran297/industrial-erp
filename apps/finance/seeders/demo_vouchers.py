"""Demo cash and bank vouchers, with the fiscal year they fall in."""

from decimal import Decimal

from django.utils import timezone

from apps.configurations.models import PaymentMethod
from apps.core.constants import (
    ACCOUNT_LEDGER_GENERAL,
    GL_CASH_PATH,
    GL_COGS_PATH,
    GL_SALES_REVENUE_PATH,
    ACCOUNT_LEDGER_SUBSIDIARY,
    ACCOUNT_NATURE_CREDIT,
    ACCOUNT_NATURE_DEBIT,
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_REVENUE,
    BALANCE_INCOME_BALANCE_SHEET,
    BALANCE_INCOME_INCOME_STATEMENT,
    STATUS_ACTIVE,
    STATUS_CREATED,
    VOUCHER_TYPE_PAYMENT,
    VOUCHER_TYPE_RECEIPT,
)
from apps.finance.models import AccountConfiguration, AccountVoucher, FiscalYear
from apps.finance.services import gl_account

# Codes carry the prefix AccountConfiguration.clean() demands for each type:
# A for assets, L for liabilities, R for revenue, E for expenses.
ACCOUNTS = [
    # account_no, code, title, type, ledger, nature, statement, posts to
    ("1000", "A-CASH", "Cash in Hand", ACCOUNT_TYPE_ASSET, ACCOUNT_LEDGER_GENERAL, ACCOUNT_NATURE_DEBIT, BALANCE_INCOME_BALANCE_SHEET, None),
    ("1100", "A-BANK", "Bank Accounts", ACCOUNT_TYPE_ASSET, ACCOUNT_LEDGER_GENERAL, ACCOUNT_NATURE_DEBIT, BALANCE_INCOME_BALANCE_SHEET, None),
    ("4000", "R-SALES", "Sales Revenue", ACCOUNT_TYPE_REVENUE, ACCOUNT_LEDGER_GENERAL, ACCOUNT_NATURE_CREDIT, BALANCE_INCOME_INCOME_STATEMENT, None),
    ("4100", "R-LOCAL", "Local Sales", ACCOUNT_TYPE_REVENUE, ACCOUNT_LEDGER_SUBSIDIARY, ACCOUNT_NATURE_CREDIT, BALANCE_INCOME_INCOME_STATEMENT, "4000"),
    ("5000", "E-OPEX", "Operating Expenses", ACCOUNT_TYPE_EXPENSE, ACCOUNT_LEDGER_GENERAL, ACCOUNT_NATURE_DEBIT, BALANCE_INCOME_INCOME_STATEMENT, None),
    ("5100", "E-UTIL", "Utilities Expense", ACCOUNT_TYPE_EXPENSE, ACCOUNT_LEDGER_SUBSIDIARY, ACCOUNT_NATURE_DEBIT, BALANCE_INCOME_INCOME_STATEMENT, "5000"),
]

NARRATIONS = [
    "Receipt from local customer",
    "Utilities and plant maintenance",
    "Cash sales counter collection",
    "Monthly admin expenses",
    "Freight paid to transporter",
    "Advance received against order",
    "Office rent for the month",
    "Fuel and vehicle running",
]


def seed_demo_accounts() -> int:
    """The handful of postable accounts the demo vouchers are written against."""
    created_count = 0
    account_map = {}
    for account_no, code, title, account_type, ledger, nature, statement, post_to_no in ACCOUNTS:
        account, created = AccountConfiguration.objects.update_or_create(
            account_no=account_no,
            defaults={
                "title": title,
                "code": code,
                "nature": account_type,
                "account_type": account_type,
                "account_ledger": ledger,
                "balance_income": statement,
                "account_nature": nature,
                "post_to_account": account_map.get(post_to_no),
                "status": STATUS_ACTIVE,
            },
        )
        account_map[account_no] = account
        created_count += int(created)
    return created_count


def seed_demo_fiscal_year() -> int:
    today = timezone.localdate()
    fiscal_year, created = FiscalYear.objects.update_or_create(
        code=f"FY-{today.year}",
        defaults={
            "title": f"Fiscal Year {today.year}",
            "start_date": today.replace(month=1, day=1),
            "end_date": today.replace(month=12, day=31),
            "status": STATUS_ACTIVE,
        },
    )
    fiscal_year.generate_periods()
    return int(created)


def seed_demo_vouchers(count: int = 50, *, user=None) -> int:
    """Write ``count`` receipts and payments, each with its own line."""
    created_count = 0
    today = timezone.localdate()
    payment_method = PaymentMethod.objects.filter(code="BANK_TRANSFER").first() or PaymentMethod.objects.order_by("pk").first()

    # A voucher heads on a leaf of the chart of accounts, not on the account
    # configuration master, so these come from the chart and are created there
    # if the chart has not been built by hand yet.
    cash = gl_account(GL_CASH_PATH, user=user)
    sales = gl_account(GL_SALES_REVENUE_PATH, user=user)
    expense = gl_account(GL_COGS_PATH, user=user)

    for index in range(1, count + 1):
        # Alternating so the register carries both sides of the cash book.
        is_payment = index % 2 == 0
        voucher_type = VOUCHER_TYPE_PAYMENT if is_payment else VOUCHER_TYPE_RECEIPT
        amount = (Decimal(25000) + Decimal(index) * Decimal("3750")).quantize(Decimal("0.01"))
        narration = NARRATIONS[(index - 1) % len(NARRATIONS)]

        # Shaped the way the posting services write a voucher: the money account
        # heads it, the header carries the voucher total on both sides, and the
        # lines carry the entry itself and balance between them.
        counter_account = expense if is_payment else sales
        money_debit = Decimal("0.00") if is_payment else amount
        money_credit = amount if is_payment else Decimal("0.00")

        voucher, created = AccountVoucher.objects.update_or_create(
            voucher_no=f"{'E' if is_payment else 'R'}-DEMO-{index:03d}",
            defaults={
                "voucher_type": voucher_type,
                "account_no": cash.code,
                "voucher_date": today,
                "payment_method": payment_method,
                "debit_amount": amount,
                "credit_amount": amount,
                "remarks": narration,
                "status": STATUS_CREATED,
                "posted": "N",
                "created_by": user,
                "updated_by": user,
            },
        )
        created_count += int(created)

        if created:
            for line_number, (line_account, line_debit, line_credit) in enumerate(
                (
                    (cash, money_debit, money_credit),
                    (counter_account, money_credit, money_debit),
                ),
                start=1,
            ):
                voucher.lines.create(
                    line_number=line_number,
                    voucher_no=voucher.voucher_no,
                    account_no=line_account.code,
                    voucher_date=today,
                    payment_method=payment_method,
                    debit_amount=line_debit,
                    credit_amount=line_credit,
                    remarks=narration,
                    person_organization="Trading partner",
                    person_organization_title=f"Demo partner {index}",
                    created_by=user,
                    updated_by=user,
                )

    return created_count
