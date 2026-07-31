from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.core.constants import ACCOUNT_TYPE_ASSET, ACCOUNT_TYPE_EXPENSE, FIN_ACCOUNT_TYPE_ROLES, STATUS_ACTIVE
from .models import ChartOfAccount

MONEY_GROUP_TITLES = ("Cash", "Bank")

# Accounts that grow on the debit side; everything else grows on the credit side.
DEBIT_NATURE_TYPES = (ACCOUNT_TYPE_ASSET, ACCOUNT_TYPE_EXPENSE)


def _get_or_create_group(*, parent, title, account_type, user=None):
    """Fetch or create a heading node (is_group=True) under ``parent``."""
    node = ChartOfAccount.objects.filter(parent=parent, title=title).first()
    if node:
        return node
    next_order = (
        ChartOfAccount.objects.filter(parent=parent).order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    ) + 1
    return ChartOfAccount.objects.create(
        parent=parent,
        title=title,
        account_type=account_type if parent is None else parent.account_type,
        is_group=True,
        sort_order=next_order,
        created_by=user,
        updated_by=user,
    )


def get_receivables_group(*, user=None):
    """Ensure ASSETS > Current Assets > Receivables headings exist; return the leaf group."""
    assets = _get_or_create_group(parent=None, title="ASSETS", account_type=ACCOUNT_TYPE_ASSET, user=user)
    current = _get_or_create_group(parent=assets, title="Current Assets", account_type=ACCOUNT_TYPE_ASSET, user=user)
    return _get_or_create_group(parent=current, title="Receivables", account_type=ACCOUNT_TYPE_ASSET, user=user)


@transaction.atomic
def create_customer_receivable_account(*, customer, user=None):
    """Create a postable Receivables account for a new customer (idempotent by title)."""
    receivables = get_receivables_group(user=user)
    existing = ChartOfAccount.objects.filter(parent=receivables, title=customer.customer_name).first()
    if existing:
        return existing
    next_order = (
        ChartOfAccount.objects.filter(parent=receivables).order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    ) + 1
    node = ChartOfAccount.objects.create(
        parent=receivables,
        title=customer.customer_name,
        account_type=receivables.account_type,
        is_group=False,
        sort_order=next_order,
        created_by=user,
        updated_by=user,
    )
    ChartOfAccount.rebuild_codes()
    node.refresh_from_db(fields=["code"])
    if customer.customer_code != node.code:
        customer.customer_code = node.code
        customer.save(update_fields=["customer_code", "updated_at"])
    return node


def signed_to_dr_cr(amount, account_type):
    """Split a natural-side-signed amount into (debit, credit) display amounts."""
    zero = Decimal("0.00")
    debit_natured = account_type in DEBIT_NATURE_TYPES
    if debit_natured:
        return (amount, zero) if amount >= 0 else (zero, -amount)
    return (zero, amount) if amount >= 0 else (-amount, zero)


def dr_cr_to_signed(debit, credit, account_type):
    """Inverse of signed_to_dr_cr: fold a (debit, credit) pair back to one signed amount."""
    net = debit - credit
    return net if account_type in DEBIT_NATURE_TYPES else -net


def _descendant_leaf_codes(group):
    """Return codes of all postable (leaf) accounts under a group node."""
    codes = []

    def walk(parent):
        children = list(ChartOfAccount.objects.filter(parent=parent, status=STATUS_ACTIVE))
        if not children and parent.code:
            codes.append(parent.code)
        for child in children:
            walk(child)

    for child in ChartOfAccount.objects.filter(parent=group, status=STATUS_ACTIVE):
        walk(child)
    return codes


def money_account_codes():
    """Postable codes of the money groups, split per group: {"Cash": {...}, "Bank": {...}}.

    A money group with no children is itself the postable account — that is how a
    single unsplit "Cash" heading is normally configured.
    """
    groups = {title: set() for title in MONEY_GROUP_TITLES}
    current = ChartOfAccount.objects.filter(title="Current Assets", parent__title="ASSETS").first()
    if not current:
        return groups
    for group in ChartOfAccount.objects.filter(parent=current, title__in=MONEY_GROUP_TITLES):
        codes = set(_descendant_leaf_codes(group))
        groups[group.title] = codes or ({group.code} if group.code else set())
    return groups


def cash_bank_account_codes():
    """Codes of every leaf account under the Cash and Bank groups (Current Assets)."""
    groups = money_account_codes()
    return set().union(*groups.values())


def receivable_account_codes():
    """Leaf codes under ASSETS > Current Assets > Receivables — the customer ledgers."""
    return set(_descendant_leaf_codes(get_receivables_group()))


def account_role(account, money_groups, customer_codes):
    """Business role of a postable account, used to filter and group the pickers."""
    if account.code in money_groups.get("Cash", ()):
        return "cash"
    if account.code in money_groups.get("Bank", ()):
        return "bank"
    if account.code in customer_codes:
        return "customer"
    return FIN_ACCOUNT_TYPE_ROLES.get(account.account_type, "other")


def account_balances():
    """Opening, voucher movement and closing balance for every account, by code.

    Every amount is signed on the account's own natural side: a debit-natured
    account (asset, expense) grows with debits, a credit-natured one (liability,
    revenue, capital) grows with credits. So a positive closing balance always
    means "normal balance", whatever the account type.
    """
    from .models import AccountVoucherLine  # lazy: models imports services in clean()

    zero = Decimal("0.00")
    natures = dict(ChartOfAccount.objects.values_list("code", "account_type"))
    balances = {
        code: {"opening": opening or zero, "movement": zero, "closing": opening or zero}
        for code, opening in ChartOfAccount.objects.values_list("code", "opening_balance")
        if code
    }
    rows = AccountVoucherLine.objects.values("account_no").annotate(
        debit=Sum("debit_amount"), credit=Sum("credit_amount")
    )
    for row in rows:
        entry = balances.get(row["account_no"])
        if entry is None:
            continue
        debit, credit = row["debit"] or zero, row["credit"] or zero
        is_debit_natured = natures.get(row["account_no"]) in DEBIT_NATURE_TYPES
        entry["movement"] = debit - credit if is_debit_natured else credit - debit
        entry["closing"] = entry["opening"] + entry["movement"]
    return balances


def sync_customer_from_coa(*, node, user=None):
    """Reverse sync: a postable account added under Receivables auto-creates a Customer.

    Only fires for leaf accounts whose parent is the Receivables group. Idempotent
    by customer_name so editing the tree elsewhere never spawns duplicates.
    """
    from apps.inventory.models import Customer  # lazy: avoid circular import

    receivables = get_receivables_group(user=user)
    if node.parent_id != receivables.id:
        return None
    if Customer.all_objects.filter(customer_name=node.title).exists():
        return None
    node.refresh_from_db(fields=["code"])  # code assigned by rebuild_codes after node.save()
    return Customer.objects.create(
        customer_name=node.title, customer_code=node.code or None, created_by=user, updated_by=user
    )
