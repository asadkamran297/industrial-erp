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
    CASH_FLOW_FINANCING,
    CASH_FLOW_INVESTING,
    CASH_FLOW_OPERATING,
    CASH_FLOW_SECTION_LABELS,
    GL_CASH_PATH,
    GL_COGS_PATH,
    GL_INVENTORY_ADJUSTMENT_PATH,
    GL_INVENTORY_PATH,
    GL_OPENING_EQUITY_PATH,
    GL_PAYABLES_PARENT,
    GL_PAYABLES_TITLES,
    GL_RETAINED_EARNINGS_PATH,
    GL_SALES_DISCOUNT_PATH,
    GL_SALES_RETURN_PATH,
    GL_SALES_REVENUE_PATH,
    FIN_MONEY_MODE_SUFFIX,
    FIN_VOUCHER_PREFIX_MAP,
    GL_SALES_TAX_PAYABLE_PATH,
    INVENTORY_ADJUSTMENT_REASONS,
    SETTLEMENT_CASH,
    SETTLEMENT_CREDIT,
    STATUS_ACTIVE,
    STATUS_SUBMITTED,
    VOUCHER_TYPE_JOURNAL,
    VOUCHER_TYPE_PURCHASE,
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
    from .models import AccountVoucherLine  # lazy: models imports services in clean()

    zero = Decimal("0.00")
    balances = account_balances()
    # Debits equal to credits leave no movement figure behind, so activity is
    # read from the lines themselves: an account that was used stays on the sheet.
    posted_codes = set(AccountVoucherLine.objects.values_list("account_no", flat=True).distinct())
    nodes = list(ChartOfAccount.objects.filter(status=STATUS_ACTIVE, account_type__in=account_types).order_by("sort_order", "id"))
    children_map: dict[int | None, list] = {}
    for node in nodes:
        children_map.setdefault(node.parent_id, []).append(node)

    def build(node, depth):
        children = [built for child in children_map.get(node.id, []) if (built := build(child, depth + 1))]
        own = balances.get(node.code) or {}
        if children:
            amount = sum((child["amount"] for child in children), zero)
        else:
            amount = own.get("closing", zero)
        # An account that moved is part of the story even when it nets to zero:
        # a bank run down to nil still belongs on the sheet. Only accounts that
        # were never touched are pruned.
        touched = node.code in posted_codes or bool(own.get("opening"))
        if not amount and not children and not touched:
            return None
        return {
            "code": node.code,
            "title": node.title,
            "account_type": node.account_type,
            "amount": amount,
            "depth": depth,
            "children": children,
            # Only a postable leaf holds entries, so only it opens a ledger.
            "is_leaf": not children,
            # Level 3 and deeper collapse behind a disclosure; the top two levels
            # are the statement's own headings and always stay open.
            "collapsible": bool(children) and depth >= 3,
        }

    return [built for root in children_map.get(None, []) if (built := build(root, 1))]


def _attach_link(nodes, code, url_name):
    """Tag the node with ``code`` so the statement can link it to its detail page."""
    for node in nodes:
        if node["code"] == code:
            node["link"] = url_name
            return True
        if _attach_link(node["children"], code, url_name):
            return True
    return False


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
    # The Inventory line is a control account backed by the stock records, so
    # it links through to the reconciliation that proves the two agree.
    _attach_link(assets, gl_account(GL_INVENTORY_PATH).code, "finance:inventory_valuation")
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


def _current_account_codes():
    """Codes sitting under Current Assets or Current Liabilities.

    Being *current* is what separates a working-capital account (trade
    receivables, stock, trade payables) from a long-term one, and that is the
    distinction the cash-flow sections turn on.
    """
    codes = set()
    for root_title, heading in (("ASSETS", "Current Assets"), ("LIABILITIES", "Current Liabilities")):
        group = ChartOfAccount.objects.filter(title=heading, parent__title=root_title).first()
        if group:
            codes |= set(_descendant_leaf_codes(group))
            if group.code:
                codes.add(group.code)
    return codes


def _cash_flow_section(counterpart_type, code, current_codes):
    """Which activity a cash movement belongs to, from the account it faced.

    Trading and working-capital accounts are day-to-day operating flows;
    owner capital and long-term debt are financing; what is left — chiefly
    non-current assets — is investing.
    """
    if counterpart_type in (ACCOUNT_TYPE_REVENUE, ACCOUNT_TYPE_EXPENSE):
        return CASH_FLOW_OPERATING
    if counterpart_type == ACCOUNT_TYPE_CAPITAL:
        return CASH_FLOW_FINANCING
    if code in current_codes:
        return CASH_FLOW_OPERATING
    # Non-current: borrowings are financing, everything else is investing.
    if counterpart_type == ACCOUNT_TYPE_LIABILITY:
        return CASH_FLOW_FINANCING
    return CASH_FLOW_INVESTING


def cash_flow_statement():
    """Where cash actually came from and went, grouped by activity.

    Built from real movements on the Cash and Bank accounts rather than from
    account balances: for every voucher touching money, the cash leg is the
    amount and the other legs say what it was for. Each counterpart account
    becomes a line under Operating, Investing or Financing.

    Opening cash + net movement = closing cash, and that reconciliation is
    what makes this a statement rather than a list.
    """
    zero = Decimal("0.00")
    money_codes = cash_bank_account_codes()
    balances = account_balances()
    natures = dict(ChartOfAccount.objects.values_list("code", "account_type"))
    titles = dict(ChartOfAccount.objects.values_list("code", "title"))
    current_codes = _current_account_codes()

    opening = sum((balances.get(code, {}).get("opening", zero) for code in money_codes), zero)
    closing = sum((balances.get(code, {}).get("closing", zero) for code in money_codes), zero)

    # Group the lines by voucher so each cash leg can be attributed to whatever
    # the rest of that voucher was about.
    lines = AccountVoucherLine.objects.values("voucher_id", "account_no", "debit_amount", "credit_amount")
    by_voucher: dict[int, list] = {}
    for line in lines:
        by_voucher.setdefault(line["voucher_id"], []).append(line)

    buckets: dict[str, dict[str, Decimal]] = {
        CASH_FLOW_OPERATING: {}, CASH_FLOW_INVESTING: {}, CASH_FLOW_FINANCING: {}
    }
    for voucher_lines in by_voucher.values():
        cash_in = sum(((ln["debit_amount"] or zero) - (ln["credit_amount"] or zero))
                      for ln in voucher_lines if ln["account_no"] in money_codes)
        if not cash_in:
            continue
        others = [ln for ln in voucher_lines if ln["account_no"] not in money_codes]
        # Split the cash movement across the non-cash legs in proportion to
        # their size, so a mixed voucher lands in more than one activity.
        weights = [abs((ln["debit_amount"] or zero) - (ln["credit_amount"] or zero)) for ln in others]
        total_weight = sum(weights, zero)
        if not total_weight:
            continue
        for line, weight in zip(others, weights):
            if not weight:
                continue
            code = line["account_no"]
            share = (cash_in * weight / total_weight).quantize(TWO_DP)
            section = _cash_flow_section(natures.get(code), code, current_codes)
            buckets[section][code] = buckets[section].get(code, zero) + share

    sections = []
    net_movement = zero
    for key in (CASH_FLOW_OPERATING, CASH_FLOW_INVESTING, CASH_FLOW_FINANCING):
        rows = [
            {"code": code, "title": titles.get(code, code), "amount": amount}
            for code, amount in sorted(buckets[key].items())
            if amount
        ]
        subtotal = sum((row["amount"] for row in rows), zero)
        net_movement += subtotal
        sections.append({"key": key, "label": CASH_FLOW_SECTION_LABELS[key], "rows": rows, "subtotal": subtotal})

    return {
        "sections": sections,
        "opening": opening,
        "net_movement": net_movement,
        "closing": closing,
        # Opening + movement must equal closing; a gap means cash moved through
        # a voucher this attribution could not explain, and is surfaced not hidden.
        "reconciles": (opening + net_movement) == closing,
        "difference": closing - (opening + net_movement),
    }


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


def get_payables_group(*, user=None):
    """Supplier control heading under LIABILITIES > Current Liabilities.

    Reuses a hand-made "Payable"/"Payables" heading if one already exists, so
    an established chart never gains a second, nearly identical group.
    """
    parent = gl_account(GL_PAYABLES_PARENT, user=user)
    existing = ChartOfAccount.objects.filter(parent=parent, title__in=GL_PAYABLES_TITLES).first()
    if existing:
        return existing
    return _get_or_create_group(parent=parent, title=GL_PAYABLES_TITLES[0], account_type=parent.account_type, user=user)


@transaction.atomic
def create_vendor_payable_account(*, vendor, user=None):
    """Postable payable account for a supplier (idempotent by name)."""
    payables = get_payables_group(user=user)
    existing = ChartOfAccount.objects.filter(parent=payables, title=vendor.name).first()
    if existing:
        return existing
    next_order = (
        ChartOfAccount.objects.filter(parent=payables).order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    ) + 1
    node = ChartOfAccount.objects.create(
        parent=payables,
        title=vendor.name,
        account_type=payables.account_type,
        is_group=False,
        sort_order=next_order,
        created_by=user,
        updated_by=user,
    )
    ChartOfAccount.rebuild_codes()
    node.refresh_from_db(fields=["code"])
    return node


def _post_voucher(*, source_ref, voucher_type, voucher_date, account_no, entries, remarks,
                  settlement_mode="", party_account_no="", user=None):
    """Create one balanced, posted voucher from ``entries`` and return it.

    ``entries`` is a list of ``(account_code, debit, credit, line_remark)``.
    Zero-value lines are dropped: they carry no information and the line
    validator rejects them. The voucher is only marked posted once its lines
    exist, so ``AccountVoucher.clean()`` can verify debits equal credits.

    Idempotent by ``source_ref`` — re-posting a source document is a no-op,
    which is what stops a retried save from double-booking the same event.
    """
    existing = AccountVoucher.objects.filter(source_ref=source_ref).first()
    if existing:
        return existing
    if not any(debit or credit for _code, debit, credit, _r in entries):
        return None

    voucher = AccountVoucher(
        source_ref=source_ref,
        voucher_type=voucher_type,
        voucher_date=voucher_date,
        settlement_mode=settlement_mode,
        account_no=account_no,
        party_account_no=party_account_no,
        remarks=remarks,
        created_by=user,
        updated_by=user,
    )
    voucher.save()

    line_number = 0
    for account_code, debit, credit, line_remark in entries:
        if not debit and not credit:
            continue
        line_number += 1
        AccountVoucherLine.objects.create(
            voucher=voucher,
            line_number=line_number,
            voucher_no=voucher.voucher_no,
            account_no=account_code,
            voucher_date=voucher.voucher_date,
            debit_amount=debit,
            credit_amount=credit,
            remarks=line_remark,
            created_by=user,
            updated_by=user,
        )

    voucher.refresh_from_db()
    voucher.status = STATUS_SUBMITTED
    voucher.posted = YES  # clean() re-checks debit == credit before allowing this
    voucher.updated_by = user
    voucher.save()
    return voucher


@transaction.atomic
def post_sale_to_gl(*, sale, cost_of_goods, user=None):
    """Book a posted POS sale.

    Revenue recognition
        Dr Cash/Bank            amount actually collected
        Dr Customer receivable  amount still owed
        Dr Sales Discount       discount given (contra-revenue)
            Cr Sales Revenue        gross sale value
            Cr Sales Tax Payable    tax collected on behalf of the authority
    Cost matching (perpetual inventory)
        Dr Cost of Goods Sold   stock cost of the items sold
            Cr Inventory            same, removing the asset
    """
    from apps.inventory.models import Customer  # lazy: inventory imports finance

    zero = Decimal("0.00")
    gross = (sale.total_amount or zero).quantize(TWO_DP)
    tax = (sale.tax_amount or zero).quantize(TWO_DP)
    discount = (sale.discount_amount or zero).quantize(TWO_DP)
    net = (sale.net_amount or zero).quantize(TWO_DP)
    paid = min((sale.total_paid or zero).quantize(TWO_DP), net)
    receivable = net - paid
    cost = (cost_of_goods or zero).quantize(TWO_DP)

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
    return _post_voucher(
        source_ref=f"inv_pos_masters:{sale.pk}",
        voucher_type=VOUCHER_TYPE_SALES,
        voucher_date=sale.sale_date,
        settlement_mode=SETTLEMENT_CREDIT if on_credit else SETTLEMENT_CASH,
        account_no=customer_account.code if on_credit else cash.code,
        party_account_no="" if on_credit else customer_account.code,
        remarks=f"Auto-posted from sale {sale.sale_num}",
        entries=[
            (cash.code, paid, zero, f"Received against {sale.sale_num}"),
            (customer_account.code, receivable, zero, f"Receivable on {sale.sale_num}"),
            (sales_discount.code, discount, zero, f"Discount allowed on {sale.sale_num}"),
            (revenue.code, zero, gross, f"Sale {sale.sale_num}"),
            (tax_payable.code, zero, tax, f"Sales tax on {sale.sale_num}"),
            (cogs.code, cost, zero, f"Cost of goods sold on {sale.sale_num}"),
            (inventory.code, zero, cost, f"Stock issued against {sale.sale_num}"),
        ],
        user=user,
    )


@transaction.atomic
def post_sale_return_to_gl(*, sale_return, cost_of_goods, user=None):
    """Book a posted sale return — the mirror of the sale.

        Dr Sales Returns        value returned (contra-revenue)
            Cr Customer receivable  credit given back to the customer
        Dr Inventory            cost of the goods back on the shelf
            Cr Cost of Goods Sold   reversing the original cost match

    The credit goes to the customer's ledger rather than cash: a refund paid
    out is a separate payment voucher, so the two events stay distinguishable.
    """
    from apps.inventory.models import Customer  # lazy: inventory imports finance

    zero = Decimal("0.00")
    returned = (sale_return.returned_amount or zero).quantize(TWO_DP)
    cost = (cost_of_goods or zero).quantize(TWO_DP)

    sale = sale_return.pos_master
    customer = sale.customer or Customer.get_default()
    if not customer:
        raise ValidationError("A customer (or a default customer) is required to post a sale return to the general ledger.")
    customer_account = create_customer_receivable_account(customer=customer, user=user)

    sales_return = gl_account(GL_SALES_RETURN_PATH, user=user)
    cogs = gl_account(GL_COGS_PATH, user=user)
    inventory = gl_account(GL_INVENTORY_PATH, user=user)

    return _post_voucher(
        source_ref=f"inv_pos_return_masters:{sale_return.pk}",
        voucher_type=VOUCHER_TYPE_JOURNAL,
        voucher_date=sale_return.return_date,
        account_no=customer_account.code,
        remarks=f"Auto-posted from sale return {sale_return.return_num} against {sale_return.sale_num}",
        entries=[
            (sales_return.code, returned, zero, f"Sale return {sale_return.return_num}"),
            (customer_account.code, zero, returned, f"Credit to customer on {sale_return.return_num}"),
            (inventory.code, cost, zero, f"Stock returned on {sale_return.return_num}"),
            (cogs.code, zero, cost, f"Reversing cost of goods sold on {sale_return.return_num}"),
        ],
        user=user,
    )


@transaction.atomic
def post_purchase_receipt_to_gl(*, receipt, vendor, amount, user=None):
    """Book goods received against a purchase order.

        Dr Inventory            landed cost of the goods received
            Cr Supplier payable     amount now owed to the vendor

    Landed cost includes apportioned freight, so the asset carries what the
    goods actually cost to bring in — which is what the later COGS entry
    matches against revenue.
    """
    zero = Decimal("0.00")
    value = (amount or zero).quantize(TWO_DP)
    if not vendor:
        raise ValidationError("A vendor is required to post a goods receipt to the general ledger.")
    vendor_account = create_vendor_payable_account(vendor=vendor, user=user)
    inventory = gl_account(GL_INVENTORY_PATH, user=user)

    return _post_voucher(
        source_ref=f"inv_purchase_order_item_received:{receipt.pk}",
        voucher_type=VOUCHER_TYPE_PURCHASE,
        voucher_date=receipt.receive_date,
        settlement_mode=SETTLEMENT_CREDIT,
        account_no=vendor_account.code,
        remarks=f"Auto-posted from goods receipt {receipt.grn_number}",
        entries=[
            (inventory.code, value, zero, f"Stock received on {receipt.grn_number}"),
            (vendor_account.code, zero, value, f"Payable to {vendor.name} on {receipt.grn_number}"),
        ],
        user=user,
    )


@transaction.atomic
def post_purchase_return_to_gl(*, purchase_return, user=None):
    """Book a posted purchase return — goods go back, the debt shrinks.

        Dr Supplier payable     amount no longer owed
            Cr Inventory            cost of the goods sent back
    """
    zero = Decimal("0.00")
    returned = (purchase_return.returned_amount or zero).quantize(TWO_DP)
    vendor = getattr(purchase_return.purchase_master, "vendor", None) or getattr(purchase_return.purchase_order, "vendor", None)
    if not vendor:
        raise ValidationError("A vendor is required to post a purchase return to the general ledger.")
    vendor_account = create_vendor_payable_account(vendor=vendor, user=user)
    inventory = gl_account(GL_INVENTORY_PATH, user=user)

    return _post_voucher(
        source_ref=f"inv_purchase_return_masters:{purchase_return.pk}",
        voucher_type=VOUCHER_TYPE_JOURNAL,
        voucher_date=purchase_return.return_date,
        account_no=vendor_account.code,
        remarks=f"Auto-posted from purchase return {purchase_return.return_num}",
        entries=[
            (vendor_account.code, returned, zero, f"Payable reduced on {purchase_return.return_num}"),
            (inventory.code, zero, returned, f"Stock returned to {vendor.name} on {purchase_return.return_num}"),
        ],
        user=user,
    )


def inventory_valuation():
    """Reconcile the Inventory control account against the stock records.

    Stock is a subsidiary ledger: each item row says how many units are held
    and what they cost. The Inventory account in the chart is the control
    account that is supposed to equal their total. When the two disagree the
    balance sheet is overstating or understating what the business owns, so
    the difference is reported rather than smoothed over.
    """
    from apps.inventory.models import Stock  # lazy: inventory imports finance

    zero = Decimal("0.00")
    rows = []
    for stock in Stock.objects.filter(status=STATUS_ACTIVE).order_by("item_name"):
        quantity = stock.current_quantity or Decimal("0")
        cost = stock.current_price or zero
        value = (quantity * cost).quantize(TWO_DP)
        if not quantity and not value:
            continue
        rows.append({
            "item_code": stock.item_code,
            "item_name": stock.item_name,
            "quantity": quantity,
            "cost": cost,
            "value": value,
        })

    stock_value = sum((row["value"] for row in rows), zero)
    account = gl_account(GL_INVENTORY_PATH)
    ledger_value = (account_balances().get(account.code) or {}).get("closing", zero)

    # A single mispriced item can dominate the total, so surface the largest
    # holdings — that is where a data-entry slip shows up.
    largest = sorted(rows, key=lambda row: -row["value"])[:5]

    return {
        "rows": rows,
        "largest": largest,
        "stock_value": stock_value,
        "ledger_value": ledger_value,
        "difference": stock_value - ledger_value,
        "reconciles": stock_value == ledger_value,
        "account": account,
    }


def inventory_control_summary():
    """Compact form of :func:`inventory_valuation` for the stock/items banner.

    Lets a subsidiary-ledger page show, in one line, whether it agrees with the
    Inventory account that reports its total on the balance sheet.
    """
    from django.urls import reverse

    state = inventory_valuation()
    return {
        "label": "Stock on hand",
        "subtotal": state["stock_value"],
        "account": state["account"],
        "ledger": state["ledger_value"],
        "difference": state["difference"],
        "reconciles": state["reconciles"],
        "url": reverse("finance:inventory_valuation"),
    }


@transaction.atomic
def post_inventory_adjustment(*, adjustment_date, reason, user=None):
    """Bring the Inventory control account in line with the stock records.

        stock worth more than the ledger says
            Dr Inventory          the shortfall
                Cr counterpart
        stock worth less
            Dr counterpart
                Cr Inventory          the excess

    ``reason`` picks the counterpart: ``opening`` books the difference to
    equity, for stock that existed before the ledger did; ``adjustment``
    books it to an expense account, which is where a real count difference
    belongs because it is a trading loss.
    """
    zero = Decimal("0.00")
    state = inventory_valuation()
    difference = state["difference"]
    if not difference:
        return None

    counterpart_path = GL_OPENING_EQUITY_PATH if reason == "opening" else GL_INVENTORY_ADJUSTMENT_PATH
    counterpart = gl_account(counterpart_path, user=user)
    inventory = state["account"]
    label = INVENTORY_ADJUSTMENT_REASONS.get(reason, reason)

    if difference > 0:
        entries = [
            (inventory.code, difference, zero, "Inventory brought in line with stock on hand"),
            (counterpart.code, zero, difference, label),
        ]
    else:
        entries = [
            (counterpart.code, -difference, zero, label),
            (inventory.code, zero, -difference, "Inventory reduced to stock on hand"),
        ]

    return _post_voucher(
        source_ref=f"inventory_adjustment:{adjustment_date:%Y-%m-%d}:{reason}",
        voucher_type=VOUCHER_TYPE_JOURNAL,
        voucher_date=adjustment_date,
        account_no=inventory.code,
        remarks=f"Inventory reconciliation — {label}",
        entries=entries,
        user=user,
    )


@transaction.atomic
def close_period_to_retained_earnings(*, closing_date, user=None, label=None):
    """Close revenue and expense into Retained Earnings and return the voucher.

    The closing entry every set of books needs at period end: each income and
    expense account is written back to nil against its own natural side, and
    the difference — the profit or loss — lands in Capital.

        Dr each revenue account      its credit balance
            Cr each expense account      its debit balance
            Cr Retained Earnings         the profit  (Dr, if a loss)

    After this runs the income statement starts again from zero and the
    balance sheet balances on its own, without profit being plugged in.
    """
    zero = Decimal("0.00")
    balances = account_balances()
    accounts = ChartOfAccount.objects.filter(
        status=STATUS_ACTIVE, children__isnull=True, account_type__in=INCOME_STATEMENT_TYPES
    ).order_by("code")

    retained = gl_account(GL_RETAINED_EARNINGS_PATH, user=user)
    entries, result = [], zero
    for account in accounts:
        # Signed on the account's own natural side: positive revenue is a
        # credit balance, positive expense a debit one.
        amount = (balances.get(account.code) or {}).get("closing", zero)
        if not amount:
            continue
        debit, credit = signed_to_dr_cr(amount, account.account_type)
        # Post the opposite side to bring the account back to nil.
        entries.append((account.code, credit, debit, f"Closing {account.title}"))
        result += amount if account.account_type == ACCOUNT_TYPE_REVENUE else -amount

    if not entries:
        return None

    profit_debit, profit_credit = (zero, result) if result >= 0 else (-result, zero)
    entries.append((retained.code, profit_debit, profit_credit,
                    "Profit for the period" if result >= 0 else "Loss for the period"))

    return _post_voucher(
        source_ref=f"period_close:{closing_date:%Y-%m-%d}",
        voucher_type=VOUCHER_TYPE_JOURNAL,
        voucher_date=closing_date,
        account_no=retained.code,
        remarks=label or f"Closing entries for the period ended {closing_date:%d %b %Y}",
        entries=entries,
        user=user,
    )


# A voucher's real-world name, when the source document says more than the
# voucher type does. A sale return is a credit note; a purchase return a debit
# note — neither has its own voucher type, both are journals underneath.
_SOURCE_KINDS = (
    ("inv_pos_return_masters:", "Credit Note"),
    ("inv_purchase_return_masters:", "Debit Note"),
    ("inv_pos_masters:", "Sale"),
    ("inv_purchase_order_item_received:", "Purchase"),
    ("inventory_adjustment:", "Stock Adjustment"),
    ("period_close:", "Period Close"),
)


def money_mode_for_account(account_no: str) -> str:
    """"cash" or "bank" for a money account, "" for anything else."""
    if not account_no:
        return ""
    groups = money_account_codes()
    if account_no in groups.get("Cash", ()):
        return "cash"
    if account_no in groups.get("Bank", ()):
        return "bank"
    return ""


def next_voucher_number(voucher_type: str, money_mode: str = "") -> str:
    """The next number in this voucher type's own sequence.

    Each type counts independently — payments run E-000001, E-000002 … while
    receipts run R-000001 … — so a gap in one book does not shift another.
    Cash and bank keep separate books within a type (EC-000001 vs EB-000001):
    the cash book and the bank book are read and reconciled separately.
    Numbering previously used the table's highest id, which meant the first
    receipt could be numbered R-000015 simply because payments had been
    entered first.

    Advisory only when shown on a form: two people opening the form at once
    would see the same number, so ``AccountVoucher.save()`` re-derives it and
    retries on the unique constraint.
    """
    import re

    prefix = FIN_VOUCHER_PREFIX_MAP.get(voucher_type, "V") + FIN_MONEY_MODE_SUFFIX.get(money_mode, "")
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    highest = 0
    for number in AccountVoucher.all_objects.filter(voucher_type=voucher_type).values_list(
        "voucher_no", flat=True
    ):
        match = pattern.match(number or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:06d}"


_ONES = ("", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


def _under_thousand(number: int) -> str:
    if number < 20:
        return _ONES[number]
    if number < 100:
        return _TENS[number // 10] + (f"-{_ONES[number % 10]}" if number % 10 else "")
    return _ONES[number // 100] + " hundred" + (f" {_under_thousand(number % 100)}" if number % 100 else "")


def amount_in_words(amount, currency: str = "Rupees", fraction: str = "Paisa") -> str:
    """The figure spelled out, the way a voucher is signed off.

    Grouped as crore / lakh / thousand: that is how the amount is read aloud
    here, and a printed voucher that reads differently from the ledger invites
    the argument it exists to prevent.
    """
    amount = Decimal(amount or 0).quantize(Decimal("0.01"))
    whole = int(amount)
    paisa = int((amount - whole) * 100)
    parts = []
    for size, name in ((10000000, "crore"), (100000, "lakh"), (1000, "thousand")):
        if whole >= size:
            parts.append(f"{_under_thousand(whole // size)} {name}")
            whole %= size
    if whole:
        parts.append(_under_thousand(whole))
    words = " ".join(parts) or "zero"
    text = f"{currency} {words}"
    if paisa:
        text += f" and {fraction} {_under_thousand(paisa)}"
    return f"{text} only".capitalize()


def voucher_kind(voucher) -> str:
    for prefix, label in _SOURCE_KINDS:
        if voucher.source_ref.startswith(prefix):
            return label
    return voucher.get_voucher_type_display()


def daybook(day, *, voucher_type=""):
    """Every entry posted on one day, in the order it was written.

    The daybook is the book of original entry: one chronological list of the
    day's transactions — sales, purchases, receipts, payments, credit and debit
    notes, journals — each with its own debit and credit legs, and the day's
    totals underneath. Anything posted to the ledger appears here, which is
    what makes it the day's complete record rather than a per-module report.
    """
    zero = Decimal("0.00")
    vouchers = (
        AccountVoucher.objects.filter(voucher_date=day)
        .prefetch_related("lines")
        .order_by("id")
    )
    if voucher_type:
        vouchers = vouchers.filter(voucher_type=voucher_type)

    titles = dict(ChartOfAccount.objects.values_list("code", "title"))
    money_codes = cash_bank_account_codes()

    entries, totals = [], {"debit": zero, "credit": zero, "cash_in": zero, "cash_out": zero}
    summary: dict[str, dict] = {}

    for voucher in vouchers:
        lines = []
        debit = credit = cash_in = cash_out = zero
        for line in voucher.lines.all().order_by("line_number"):
            line_debit = line.debit_amount or zero
            line_credit = line.credit_amount or zero
            debit += line_debit
            credit += line_credit
            if line.account_no in money_codes:
                cash_in += line_debit
                cash_out += line_credit
            lines.append({
                "account_no": line.account_no,
                # An account missing from the chart is named as such rather
                # than shown as a bare code with no explanation.
                "title": titles.get(line.account_no, "— not in chart of accounts —"),
                "known": line.account_no in titles,
                "debit": line_debit,
                "credit": line_credit,
                "remarks": line.remarks,
            })

        kind = voucher_kind(voucher)
        entries.append({
            "voucher": voucher,
            "kind": kind,
            "party": titles.get(voucher.party_account_no or voucher.account_no, voucher.account_no),
            "lines": lines,
            "debit": debit,
            "credit": credit,
            "balanced": debit == credit,
        })

        totals["debit"] += debit
        totals["credit"] += credit
        totals["cash_in"] += cash_in
        totals["cash_out"] += cash_out

        bucket = summary.setdefault(kind, {"kind": kind, "count": 0, "amount": zero})
        bucket["count"] += 1
        bucket["amount"] += debit

    return {
        "day": day,
        "entries": entries,
        "totals": totals,
        "summary": sorted(summary.values(), key=lambda row: -row["amount"]),
        "balanced": totals["debit"] == totals["credit"],
        "net_cash": totals["cash_in"] - totals["cash_out"],
    }


def ledger_integrity():
    """Everything that would make the statements lie, gathered in one place.

    ``account_balances()`` can only report on codes that exist in the chart, so
    a line posted to a code that was never created — or was deleted — drops out
    of every report. The trial balance then *looks* balanced precisely because
    the offending entry is missing. These checks exist so that never passes
    unnoticed: the reports say what they cannot account for.
    """
    zero = Decimal("0.00")
    known = {code for code in ChartOfAccount.objects.values_list("code", flat=True) if code}

    # Postings whose account is not in the chart of accounts.
    orphan_rows = (
        AccountVoucherLine.objects.exclude(account_no__in=known)
        .values("account_no")
        .annotate(debit=Sum("debit_amount"), credit=Sum("credit_amount"))
        .order_by("account_no")
    )
    orphans = [
        {"account_no": row["account_no"], "debit": row["debit"] or zero, "credit": row["credit"] or zero}
        for row in orphan_rows
    ]
    orphan_debit = sum((row["debit"] for row in orphans), zero)
    orphan_credit = sum((row["credit"] for row in orphans), zero)

    # Vouchers whose own lines do not balance.
    unbalanced = []
    for voucher in AccountVoucher.objects.prefetch_related("lines").order_by("voucher_date", "id"):
        lines = list(voucher.lines.all())
        if not lines:
            continue
        debit = sum((line.debit_amount or zero for line in lines), zero)
        credit = sum((line.credit_amount or zero for line in lines), zero)
        if debit != credit:
            unbalanced.append({
                "voucher": voucher, "debit": debit, "credit": credit, "difference": debit - credit,
            })

    # Opening balances are entered by hand and must themselves be a double entry.
    opening_debit = opening_credit = zero
    for account in ChartOfAccount.objects.filter(status=STATUS_ACTIVE, children__isnull=True):
        debit, credit = signed_to_dr_cr(account.opening_balance or zero, account.account_type)
        opening_debit += debit
        opening_credit += credit

    return {
        "orphans": orphans,
        "orphan_debit": orphan_debit,
        "orphan_credit": orphan_credit,
        "unbalanced": unbalanced,
        "opening_debit": opening_debit,
        "opening_credit": opening_credit,
        "opening_difference": opening_debit - opening_credit,
        "is_clean": not orphans and not unbalanced and opening_debit == opening_credit,
    }


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


def account_ledger(account_no, *, date_from=None, date_to=None):
    """One account's statement: opening balance, its entries, running balance.

    The opening balance is the account's own opening plus everything posted
    before ``date_from``, so a date range reads as a continuation of the ledger
    rather than a fragment of it. Each row carries the balance as it stood after
    that entry, signed on the account's natural side — the same convention
    ``account_balances`` uses, so a positive figure always means normal balance.
    """
    from .models import AccountVoucherLine  # lazy: models imports services in clean()

    zero = Decimal("0.00")
    account = ChartOfAccount.objects.filter(code=account_no).first()
    if account is None:
        return None

    debit_natured = account.account_type in DEBIT_NATURE_TYPES
    signed = (lambda debit, credit: debit - credit) if debit_natured else (lambda debit, credit: credit - debit)

    lines = AccountVoucherLine.objects.filter(account_no=account_no).select_related("voucher")

    opening = account.opening_balance or zero
    if date_from:
        earlier = lines.filter(voucher_date__lt=date_from).aggregate(
            debit=Sum("debit_amount"), credit=Sum("credit_amount")
        )
        opening += signed(earlier["debit"] or zero, earlier["credit"] or zero)
        lines = lines.filter(voucher_date__gte=date_from)
    if date_to:
        lines = lines.filter(voucher_date__lte=date_to)

    rows = []
    balance = opening
    total_debit = total_credit = zero
    for line in lines.order_by("voucher_date", "voucher_no", "line_number"):
        debit = line.debit_amount or zero
        credit = line.credit_amount or zero
        balance += signed(debit, credit)
        total_debit += debit
        total_credit += credit
        rows.append({
            "line": line,
            "voucher": line.voucher,
            "debit": debit,
            "credit": credit,
            "balance": balance,
        })

    return {
        "account": account,
        "debit_natured": debit_natured,
        "opening": opening,
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "closing": balance,
    }
