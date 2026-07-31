from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from django.core.exceptions import ValidationError

from apps.core.constants import (
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_CAPITAL,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_LIABILITY,
    ACCOUNT_TYPE_REVENUE,
    FIN_ACCOUNT_TYPE_ROLES,
    GL_CASH_PATH,
    GL_COGS_PATH,
    GL_INVENTORY_PATH,
    GL_SALES_DISCOUNT_PATH,
    GL_SALES_REVENUE_PATH,
    GL_SALES_TAX_PAYABLE_PATH,
    SETTLEMENT_CASH,
    SETTLEMENT_CREDIT,
    STATUS_ACTIVE,
    STATUS_SUBMITTED,
    VOUCHER_TYPE_SALES,
    YES,
)
from .models import AccountVoucher, AccountVoucherLine, ChartOfAccount

TWO_DP = Decimal("0.01")

MONEY_GROUP_TITLES = ("Cash", "Bank")

# Accounts that grow on the debit side; everything else grows on the credit side.
DEBIT_NATURE_TYPES = (ACCOUNT_TYPE_ASSET, ACCOUNT_TYPE_EXPENSE)

# The two P&L root types vs. the three balance-sheet root types.
INCOME_STATEMENT_TYPES = (ACCOUNT_TYPE_REVENUE, ACCOUNT_TYPE_EXPENSE)
BALANCE_SHEET_TYPES = (ACCOUNT_TYPE_ASSET, ACCOUNT_TYPE_LIABILITY, ACCOUNT_TYPE_CAPITAL)


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


def _account_rows(account_types):
    """Postable accounts of the given root types with their closing balance, signed natural side."""
    balances = account_balances()
    zero = Decimal("0.00")
    rows = []
    accounts = ChartOfAccount.objects.filter(
        status=STATUS_ACTIVE, children__isnull=True, account_type__in=account_types
    ).order_by("code")
    for account in accounts:
        own = balances.get(account.code) or {"opening": zero, "movement": zero, "closing": zero}
        if not own["closing"]:
            continue
        rows.append({"code": account.code, "title": account.title, "account_type": account.account_type, "amount": own["closing"]})
    return rows


def income_statement():
    """Revenue and expense accounts, to date, with net profit/loss.

    Balances are cumulative movement since inception (there is no period-close
    step yet, see FiscalPeriod), so this reads as "life-to-date" P&L rather
    than a single fiscal period's.
    """
    zero = Decimal("0.00")
    rows = _account_rows(INCOME_STATEMENT_TYPES)
    revenue = [row for row in rows if row["account_type"] == ACCOUNT_TYPE_REVENUE]
    expense = [row for row in rows if row["account_type"] == ACCOUNT_TYPE_EXPENSE]
    total_revenue = sum((row["amount"] for row in revenue), zero)
    total_expense = sum((row["amount"] for row in expense), zero)
    return {
        "revenue": revenue,
        "expense": expense,
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "net_profit": total_revenue - total_expense,
    }


def _balance_forest(account_types):
    """Chart-of-accounts subtrees for ``account_types``, each node carrying a rolled-up closing balance.

    Headings hold no balance of their own, so a heading's amount is the sum of
    its subtree. Branches that net to zero are pruned — a balance sheet lists
    what the business holds, not every account ever opened.
    """
    zero = Decimal("0.00")
    balances = account_balances()
    nodes = list(ChartOfAccount.objects.filter(status=STATUS_ACTIVE, account_type__in=account_types).order_by("sort_order", "id"))
    children_map: dict[int | None, list] = {}
    for node in nodes:
        children_map.setdefault(node.parent_id, []).append(node)

    def build(node, depth):
        children = [built for child in children_map.get(node.id, []) if (built := build(child, depth + 1))]
        if children:
            amount = sum((child["amount"] for child in children), zero)
        else:
            amount = (balances.get(node.code) or {}).get("closing", zero)
        if not amount and not children:
            return None
        return {
            "code": node.code,
            "title": node.title,
            "account_type": node.account_type,
            "amount": amount,
            "depth": depth,
            "children": children,
            # Level 3 and deeper collapse behind a disclosure; the top two levels
            # are the statement's own headings and always stay open.
            "collapsible": bool(children) and depth >= 3,
        }

    return [built for root in children_map.get(None, []) if (built := build(root, 1))]


def balance_sheet():
    """Assets vs. Liabilities + Capital as collapsible trees, with life-to-date net profit in Capital.

    Without closing entries revenue/expense accounts never zero out into
    retained earnings, so the statement folds ``income_statement()["net_profit"]``
    into the Capital side to keep Assets = Liabilities + Capital true.
    """
    zero = Decimal("0.00")
    assets = _balance_forest([ACCOUNT_TYPE_ASSET])
    liabilities = _balance_forest([ACCOUNT_TYPE_LIABILITY])
    capital = _balance_forest([ACCOUNT_TYPE_CAPITAL])
    net_profit = income_statement()["net_profit"]
    total_assets = sum((node["amount"] for node in assets), zero)
    total_liabilities = sum((node["amount"] for node in liabilities), zero)
    total_capital = sum((node["amount"] for node in capital), zero) + net_profit
    return {
        "assets": assets,
        "liabilities": liabilities,
        "capital": capital,
        "net_profit": net_profit,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_capital": total_capital,
        "total_liabilities_and_capital": total_liabilities + total_capital,
    }


def cash_flow_summary():
    """Opening, movement (net change) and closing balance for every Cash/Bank leaf account.

    A simple net-change view, not a full indirect/direct-method statement —
    there is no activity classification (operating/investing/financing) to
    derive one from yet.
    """
    zero = Decimal("0.00")
    balances = account_balances()
    groups = money_account_codes()
    accounts = {a.code: a for a in ChartOfAccount.objects.filter(status=STATUS_ACTIVE, children__isnull=True)}
    rows, totals = [], {"opening": zero, "movement": zero, "closing": zero}
    for group_title, codes in groups.items():
        for code in sorted(codes):
            account = accounts.get(code)
            own = balances.get(code)
            if not account or not own:
                continue
            rows.append({"code": code, "title": account.title, "group": group_title, **own})
            for key in totals:
                totals[key] += own[key]
    return {"rows": rows, "totals": totals}


# account_type of each chart-of-accounts root, for auto-created GL account paths.
_ROOT_TYPES = {
    "ASSETS": ACCOUNT_TYPE_ASSET,
    "LIABILITIES": ACCOUNT_TYPE_LIABILITY,
    "CAPITAL": ACCOUNT_TYPE_CAPITAL,
    "REVENUE": ACCOUNT_TYPE_REVENUE,
    "EXPENSES": ACCOUNT_TYPE_EXPENSE,
}


def gl_account(path, *, user=None):
    """Find-or-create the postable account at ``path`` (root, heading, ..., leaf).

    Every element but the last is a heading; the last is the postable account.
    Used so automatic postings never fail on a chart that has not been set up
    by hand yet.
    """
    root_title = path[0]
    node = _get_or_create_group(parent=None, title=root_title, account_type=_ROOT_TYPES[root_title], user=user)
    for title in path[1:]:
        node = _get_or_create_group(parent=node, title=title, account_type=node.account_type, user=user)
    if not node.code:
        ChartOfAccount.rebuild_codes()
        node.refresh_from_db(fields=["code"])
    return node


@transaction.atomic
def post_sale_to_gl(*, sale, cost_of_goods, user=None):
    """Book the double entry for a posted POS sale and return the voucher.

    Two entries in one Sales voucher, per the perpetual inventory method:

    Revenue recognition
        Dr Cash/Bank            amount actually collected
        Dr Customer receivable  amount still owed
        Dr Sales Discount       discount given (contra-revenue)
            Cr Sales Revenue        gross sale value
            Cr Sales Tax Payable    tax collected on behalf of the authority
    Cost matching
        Dr Cost of Goods Sold   stock cost of the items sold
            Cr Inventory            same, removing the asset

    Idempotent: a sale that already has a voucher returns it untouched.
    """
    from apps.inventory.models import Customer  # lazy: inventory imports finance

    source_ref = f"inv_pos_masters:{sale.pk}"
    existing = AccountVoucher.objects.filter(source_ref=source_ref).first()
    if existing:
        return existing

    zero = Decimal("0.00")
    gross = (sale.total_amount or zero).quantize(TWO_DP)
    tax = (sale.tax_amount or zero).quantize(TWO_DP)
    discount = (sale.discount_amount or zero).quantize(TWO_DP)
    net = (sale.net_amount or zero).quantize(TWO_DP)
    paid = min((sale.total_paid or zero).quantize(TWO_DP), net)
    receivable = net - paid
    cost = (cost_of_goods or zero).quantize(TWO_DP)
    if not gross and not cost:
        return None

    customer = sale.customer or Customer.get_default()
    if not customer:
        raise ValidationError("A customer (or a default customer) is required to post a sale to the general ledger.")
    customer_account = create_customer_receivable_account(customer=customer, user=user)

    cash = gl_account(GL_CASH_PATH, user=user)
    revenue = gl_account(GL_SALES_REVENUE_PATH, user=user)
    sales_discount = gl_account(GL_SALES_DISCOUNT_PATH, user=user)
    tax_payable = gl_account(GL_SALES_TAX_PAYABLE_PATH, user=user)
    cogs = gl_account(GL_COGS_PATH, user=user)
    inventory = gl_account(GL_INVENTORY_PATH, user=user)

    # A fully collected sale settles in cash and names the customer separately;
    # anything left outstanding is a credit sale headed by the customer ledger.
    on_credit = receivable > 0
    voucher = AccountVoucher(
        source_ref=source_ref,
        voucher_type=VOUCHER_TYPE_SALES,
        voucher_date=sale.sale_date,
        settlement_mode=SETTLEMENT_CREDIT if on_credit else SETTLEMENT_CASH,
        account_no=customer_account.code if on_credit else cash.code,
        party_account_no="" if on_credit else customer_account.code,
        remarks=f"Auto-posted from sale {sale.sale_num}",
        created_by=user,
        updated_by=user,
    )
    voucher.save()

    entries = [
        (cash.code, paid, zero, f"Received against {sale.sale_num}"),
        (customer_account.code, receivable, zero, f"Receivable on {sale.sale_num}"),
        (sales_discount.code, discount, zero, f"Discount allowed on {sale.sale_num}"),
        (revenue.code, zero, gross, f"Sale {sale.sale_num}"),
        (tax_payable.code, zero, tax, f"Sales tax on {sale.sale_num}"),
        (cogs.code, cost, zero, f"Cost of goods sold on {sale.sale_num}"),
        (inventory.code, zero, cost, f"Stock issued against {sale.sale_num}"),
    ]
    line_number = 0
    for account_no, debit, credit, remarks in entries:
        if not debit and not credit:
            continue  # a zero line carries no information and clean() rejects it
        line_number += 1
        AccountVoucherLine.objects.create(
            voucher=voucher,
            line_number=line_number,
            voucher_no=voucher.voucher_no,
            account_no=account_no,
            voucher_date=voucher.voucher_date,
            debit_amount=debit,
            credit_amount=credit,
            remarks=remarks,
            created_by=user,
            updated_by=user,
        )

    voucher.refresh_from_db()
    voucher.status = STATUS_SUBMITTED
    voucher.posted = YES  # clean() re-checks debit == credit before allowing this
    voucher.updated_by = user
    voucher.save()
    return voucher


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
