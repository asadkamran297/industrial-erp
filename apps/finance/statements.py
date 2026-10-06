"""Financial statement engine.

Every statement figure comes from ``aggregate()``: one query over posted voucher
lines with one conditional sum per column, plus one chart read. Figures leave
the query as raw ``debit - credit``; ``Chart.natural`` flips them to each
account's own side exactly once.
"""

from collections import namedtuple
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import reduce
from operator import or_

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.utils import timezone

from apps.core.constants import (
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_CAPITAL,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_LIABILITY,
    ACCOUNT_TYPE_REVENUE,
    FS_CASH_GROUP_TITLES,
    FS_CURRENT_ASSETS_PATH,
    FS_CURRENT_LIABILITIES_PATH,
    FS_PERIOD_CLOSE_PREFIX,
    FS_PL_COGS,
    FS_PL_EXPENSES,
    FS_PL_INCOME,
    FS_PL_OTHER_EXPENSES,
    FS_PL_OTHER_INCOME,
    FS_PL_SECTION_BY_GROUP,
    FS_PL_SECTION_LABELS,
    FS_PL_UNMAPPED,
    GL_RETAINED_EARNINGS_PATH,
    STATUS_ACTIVE,
    YES,
)
from apps.core.reporting import money

from .models import AccountVoucherLine, ChartOfAccount, FiscalYear

Column = namedtuple("Column", "key label start end")

ZERO = Decimal("0.00")
DEBIT_NATURE_TYPES = (ACCOUNT_TYPE_ASSET, ACCOUNT_TYPE_EXPENSE)
PL_TYPES = (ACCOUNT_TYPE_REVENUE, ACCOUNT_TYPE_EXPENSE)

SHOW_ACTIVE = "active"
SHOW_NONZERO = "nonzero"
SHOW_ALL = "all"
SHOW_CHOICES = ((SHOW_ACTIVE, "Active rows only"), (SHOW_NONZERO, "Non-zero rows"), (SHOW_ALL, "All rows"))

_AMOUNT = DecimalField(max_digits=18, decimal_places=2)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def range_q(start, end) -> Q:
    q = Q(voucher_date__lte=end)
    if start:
        q &= Q(voucher_date__gte=start)
    return q


def without_close(q: Q) -> Q:
    return q & ~Q(voucher__source_ref__startswith=FS_PERIOD_CLOSE_PREFIX)


def aggregate(specs: dict, *, codes=None, posted_only=True) -> dict:
    """``{code: {key: raw debit - credit}}``, one conditional sum per ``{key: Q}`` spec, one query."""
    if not specs:
        return {}
    keys = list(specs)
    lines = AccountVoucherLine.objects.filter(voucher__deleted_at__isnull=True)
    if posted_only:
        lines = lines.filter(voucher__posted=YES)
    if codes is not None:
        lines = lines.filter(account_no__in=list(codes))
    lines = lines.filter(reduce(or_, specs.values()))
    net = F("debit_amount") - F("credit_amount")
    annotations = {
        f"c{index}": Sum(Case(When(specs[key], then=net), default=Value(ZERO), output_field=_AMOUNT))
        for index, key in enumerate(keys)
    }
    result = {}
    for row in lines.values("account_no").annotate(**annotations).order_by():
        result[row["account_no"]] = {key: money(row[f"c{index}"]) for index, key in enumerate(keys)}
    return result


def account_movements(columns, *, codes=None, exclude_close=False, posted_only=True) -> dict:
    """Raw movement per account per column. ``start=None`` runs from inception; openings never included."""
    specs = {}
    for column in columns:
        q = range_q(column.start, column.end)
        specs[column.key] = without_close(q) if exclude_close else q
    return aggregate(specs, codes=codes, posted_only=posted_only)


def balances_as_of(dates: dict, *, chart=None, codes=None, posted_only=True) -> dict:
    """Raw cumulative balance per account at each ``{key: date}``, master opening included."""
    chart = chart or load_chart()
    figures = aggregate({key: Q(voucher_date__lte=day) for key, day in dates.items()}, codes=codes, posted_only=posted_only)
    return chart.with_openings(figures, list(dates), codes=codes)


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

@dataclass
class Node:
    id: int
    parent_id: int | None
    code: str
    title: str
    account_type: str
    status: str
    opening: Decimal
    children: list = field(default_factory=list)

    @property
    def inactive(self) -> bool:
        return self.status != STATUS_ACTIVE


class Chart:
    def __init__(self, nodes):
        self.by_id = {node.id: node for node in nodes}
        self.by_code = {node.code: node for node in nodes if node.code}
        self.roots = []
        for node in nodes:
            parent = self.by_id.get(node.parent_id)
            (parent.children if parent else self.roots).append(node)

    def root(self, account_type):
        return next((node for node in self.roots if node.account_type == account_type), None)

    def find(self, path):
        nodes = self.roots
        found = None
        for title in path:
            found = next((node for node in nodes if node.title == title), None)
            if found is None:
                return None
            nodes = found.children
        return found

    def codes_of(self, *account_types) -> set:
        return {code for code, node in self.by_code.items() if node.account_type in account_types}

    def descendant_codes(self, node) -> set:
        codes = {node.code} if node.code else set()
        for child in node.children:
            codes |= self.descendant_codes(child)
        return codes

    def ordered_codes(self, nodes=None) -> list:
        """Every code in chart order (depth first, sibling sort order)."""
        codes = []
        for node in self.roots if nodes is None else nodes:
            if node.code:
                codes.append(node.code)
            codes += self.ordered_codes(node.children)
        return codes

    def leaf_codes(self, node) -> set:
        if not node.children:
            return {node.code} if node.code else set()
        codes = set()
        for child in node.children:
            codes |= self.leaf_codes(child)
        return codes

    def title(self, code) -> str:
        node = self.by_code.get(code)
        return node.title if node else code

    def raw_opening(self, code) -> Decimal:
        node = self.by_code.get(code)
        if node is None or not node.opening:
            return ZERO
        return node.opening if node.account_type in DEBIT_NATURE_TYPES else -node.opening

    def with_openings(self, figures, keys, codes=None) -> dict:
        result = {code: dict(values) for code, values in figures.items()}
        for code, node in self.by_code.items():
            if not node.opening or (codes is not None and code not in codes):
                continue
            opening = self.raw_opening(code)
            values = result.setdefault(code, {key: ZERO for key in keys})
            for key in keys:
                values[key] = values.get(key, ZERO) + opening
        return result

    def natural(self, figures) -> dict:
        """Flip raw ``debit - credit`` to each account's own side: positive means normal balance."""
        result = {}
        for code, values in figures.items():
            node = self.by_code.get(code)
            debit_natured = node is None or node.account_type in DEBIT_NATURE_TYPES
            result[code] = values if debit_natured else {key: -value for key, value in values.items()}
        return result


def load_chart() -> Chart:
    nodes = [
        Node(row["id"], row["parent_id"], row["code"], row["title"], row["account_type"], row["status"], row["opening_balance"] or ZERO)
        for row in ChartOfAccount.objects.order_by("sort_order", "id").values(
            "id", "parent_id", "code", "title", "account_type", "status", "opening_balance"
        )
    ]
    return Chart(nodes)


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def _zeros(keys):
    return {key: ZERO for key in keys}


def _add(left, right, sign=1):
    return {key: left.get(key, ZERO) + sign * right.get(key, ZERO) for key in left}


def _row(kind, depth, title, values, *, code="", row_id="", parent="", drill=None, collapsible=False, inactive=False):
    return {
        "kind": kind, "depth": depth, "code": code, "title": title, "values": values, "id": row_id or code or title,
        "parent": parent, "drill": drill, "collapsible": collapsible, "inactive": inactive,
    }


class TreeBuilder:
    """Turns chart subtrees plus natural-signed figures into flat statement rows with ``Total`` rows."""

    def __init__(self, chart, natural, keys, *, show=SHOW_ACTIVE, drill=None, computed=()):
        self.chart = chart
        self.natural = natural
        self.keys = keys
        self.show = show
        self.drill = drill
        self.computed = set(computed)

    def _visible(self, code, values, inactive):
        nonzero = any(values.values())
        if inactive:
            return nonzero
        if self.show == SHOW_ALL or nonzero:
            return True
        return self.show == SHOW_ACTIVE and code in self.natural

    def _account(self, node, depth, parent, title=None):
        values = {key: (self.natural.get(node.code) or {}).get(key, ZERO) for key in self.keys}
        if not self._visible(node.code, values, node.inactive):
            return [], values
        kind = "computed" if node.code in self.computed else "account"
        drill = self.drill(node.code) if self.drill and kind == "account" else None
        return [_row(kind, depth, title or node.title, values, code=node.code, parent=parent, drill=drill, inactive=node.inactive)], values

    def node(self, node, depth, parent=""):
        """Rows for ``node`` and its subtree, and the subtree's total per column."""
        if not node.children:
            return self._account(node, depth, parent)
        row_id = node.code or f"g{node.id}"
        child_rows, total = [], _zeros(self.keys)
        if node.code in self.natural:
            own_rows, own = self._account(node, depth + 1, row_id)
            child_rows += own_rows
            total = _add(total, own)
        for child in node.children:
            rows, values = self.node(child, depth + 1, row_id)
            child_rows += rows
            total = _add(total, values)
        if not child_rows and not (self.show == SHOW_ALL and not node.inactive):
            return [], total
        return [
            _row("group", depth, node.title, total, code=node.code, row_id=row_id, parent=parent, collapsible=True, inactive=node.inactive),
            *child_rows,
            _row("total", depth, f"Total {node.title}", total, row_id=f"{row_id}-total", parent=row_id),
        ], total

    def children(self, node, depth, parent=""):
        """``node``'s children rendered without a header for ``node`` itself."""
        rows, total = [], _zeros(self.keys)
        for child in node.children:
            child_rows, values = self.node(child, depth, parent)
            rows += child_rows
            total = _add(total, values)
        return rows, total


# ---------------------------------------------------------------------------
# Fiscal year
# ---------------------------------------------------------------------------

def _fiscal_years():
    return list(FiscalYear.objects.values_list("start_date", "end_date"))


def fiscal_year_start(day: date, years=None) -> date:
    """Start of the fiscal year holding ``day``; falls back to the 1 July year ``resolve_period`` uses."""
    years = _fiscal_years() if years is None else years
    starts = [start for start, end in years if start <= day <= end]
    if starts:
        return max(starts)
    return date(day.year if day.month >= 7 else day.year - 1, 7, 1)


# ---------------------------------------------------------------------------
# Profit and loss
# ---------------------------------------------------------------------------

def _pl_sections(chart):
    """``{section: [(group_node, sign)]}`` where sign turns natural figures into profit contribution."""
    sections = {key: [] for key in FS_PL_SECTION_LABELS}
    for account_type in PL_TYPES:
        root = chart.root(account_type)
        if root is None:
            continue
        sign = 1 if account_type == ACCOUNT_TYPE_REVENUE else -1
        for group in root.children:
            section = FS_PL_SECTION_BY_GROUP.get((root.title, group.title), FS_PL_UNMAPPED)
            sections[section].append((group, sign))
    return sections


def _section_rows(builder, key, groups, keys):
    """One P&L section: header, its accounts, ``Total <Section>``. Total is signed for the section's side."""
    label = FS_PL_SECTION_LABELS[key]
    expense_side = key in (FS_PL_COGS, FS_PL_EXPENSES, FS_PL_OTHER_EXPENSES)
    body, total, contribution = [], _zeros(keys), _zeros(keys)
    single = len(groups) == 1
    for group, sign in groups:
        if single and group.children:
            rows, values = builder.children(group, 1, key)
        else:
            rows, values = builder.node(group, 1, key)
        body += rows
        contribution = _add(contribution, values, sign)
    total = {k: -v for k, v in contribution.items()} if expense_side else contribution
    if not body and key in (FS_PL_UNMAPPED, FS_PL_OTHER_EXPENSES) and builder.show != SHOW_ALL:
        return [], total, contribution
    rows = [
        _row("section", 0, label, total, row_id=key, collapsible=True),
        *body,
        _row("total", 0, f"Total {label}", total, row_id=f"{key}-total", parent=key),
    ]
    return rows, total, contribution


def profit_and_loss(columns, *, show=SHOW_ACTIVE, drill=None, posted_only=True) -> dict:
    """QuickBooks layout: Income, COGS, Gross Profit, Expenses, Net Operating Income, Other, Net Income.

    Period-close journals are left out so a range spanning a close still shows its profit.
    """
    keys = [column.key for column in columns]
    chart = load_chart()
    pl_codes = chart.codes_of(*PL_TYPES)
    figures = account_movements(columns, codes=pl_codes, exclude_close=True, posted_only=posted_only)
    builder = TreeBuilder(chart, chart.natural(figures), keys, show=show, drill=drill)
    sections = _pl_sections(chart)

    out, totals = {}, {}
    for key in FS_PL_SECTION_LABELS:
        out[key] = _section_rows(builder, key, sections[key], keys)
        totals[key] = out[key][1]

    gross = _add(totals[FS_PL_INCOME], totals[FS_PL_COGS], -1)
    operating = _add(gross, totals[FS_PL_EXPENSES], -1)
    other = _add(totals[FS_PL_OTHER_INCOME], totals[FS_PL_OTHER_EXPENSES], -1)
    unmapped = out[FS_PL_UNMAPPED][2]
    net = _add(_add(operating, other), unmapped)

    rows = [
        *out[FS_PL_INCOME][0],
        *out[FS_PL_COGS][0],
        _row("computed", 0, "Gross Profit", gross, row_id="gross_profit"),
        *out[FS_PL_EXPENSES][0],
        _row("computed", 0, "Net Operating Income", operating, row_id="net_operating_income"),
        *out[FS_PL_OTHER_INCOME][0],
        *out[FS_PL_OTHER_EXPENSES][0],
        _row("computed", 0, "Net Other Income", other, row_id="net_other_income"),
        *out[FS_PL_UNMAPPED][0],
        _row("grand", 0, "Net Income", net, row_id="net_income"),
    ]
    totals.update({"gross_profit": gross, "net_operating_income": operating, "net_other_income": other, "unmapped": unmapped, "net_income": net})
    return {"columns": list(columns), "rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# Balance sheet
# ---------------------------------------------------------------------------

def balance_sheet(columns, *, show=SHOW_ACTIVE, drill=None, posted_only=True) -> dict:
    """Assets against Liabilities and Equity at each column's ``end``.

    Equity carries Retained Earnings (everything before the fiscal-year start,
    plus whatever the Retained Earnings account holds) and Net Income (fiscal-year
    start to the as-of date, period closes excluded). The two always add up to
    the Retained Earnings account plus every Revenue/Expense balance, so the
    sheet ties whether or not a period has been closed.
    """
    keys = [column.key for column in columns]
    chart = load_chart()
    years = _fiscal_years()
    pl_codes = chart.codes_of(*PL_TYPES)
    specs = {}
    for column in columns:
        specs[f"b:{column.key}"] = Q(voucher_date__lte=column.end)
        fy_start = fiscal_year_start(column.end, years)
        specs[f"n:{column.key}"] = without_close(range_q(fy_start, column.end)) & Q(account_no__in=list(pl_codes))
    figures = aggregate(specs, posted_only=posted_only)

    balance_raw = chart.with_openings(
        {code: {key: values[f"b:{key}"] for key in keys} for code, values in figures.items()}, keys
    )
    net_income = {key: -sum((values[f"n:{key}"] for values in figures.values()), ZERO) for key in keys}
    all_pl = {key: -sum((balance_raw[code][key] for code in pl_codes if code in balance_raw), ZERO) for key in keys}

    natural = chart.natural(balance_raw)
    retained = chart.find(GL_RETAINED_EARNINGS_PATH)
    retained_own = (natural.get(retained.code) if retained and retained.code else None) or _zeros(keys)
    retained_line = {key: retained_own.get(key, ZERO) + all_pl[key] - net_income[key] for key in keys}
    computed = ()
    if retained and retained.code:
        natural[retained.code] = retained_line
        computed = (retained.code,)

    builder = TreeBuilder(chart, natural, keys, show=show, drill=drill, computed=computed)

    asset_root = chart.root(ACCOUNT_TYPE_ASSET)
    asset_rows, total_assets = builder.children(asset_root, 1, "assets") if asset_root else ([], _zeros(keys))

    liability_root = chart.root(ACCOUNT_TYPE_LIABILITY)
    liability_rows, total_liabilities = builder.children(liability_root, 2, "liabilities") if liability_root else ([], _zeros(keys))

    capital_root = chart.root(ACCOUNT_TYPE_CAPITAL)
    equity_rows, equity = builder.children(capital_root, 2, "equity") if capital_root else ([], _zeros(keys))
    if not computed:
        equity_rows.append(_row("computed", 2, "Retained Earnings", retained_line, row_id="retained_earnings", parent="equity"))
        equity = _add(equity, retained_line)
    equity_rows.append(_row("computed", 2, "Net Income", net_income, row_id="net_income", parent="equity"))
    total_equity = _add(equity, net_income)

    total_le = _add(total_liabilities, total_equity)
    difference = _add(total_assets, total_le, -1)

    rows = [
        _row("section", 0, "Assets", total_assets, row_id="assets", collapsible=True),
        *asset_rows,
        _row("grand", 0, "Total Assets", total_assets, row_id="assets-total", parent="assets"),
        _row("section", 0, "Liabilities and Equity", total_le, row_id="le", collapsible=True),
        _row("group", 1, "Liabilities", total_liabilities, row_id="liabilities", parent="le", collapsible=True),
        *liability_rows,
        _row("total", 1, "Total Liabilities", total_liabilities, row_id="liabilities-total", parent="liabilities"),
        _row("group", 1, "Equity", total_equity, row_id="equity", parent="le", collapsible=True),
        *equity_rows,
        _row("total", 1, "Total Equity", total_equity, row_id="equity-total", parent="equity"),
        _row("grand", 0, "Total Liabilities and Equity", total_le, row_id="le-total", parent="le"),
    ]
    if any(difference.values()):
        rows.append(_row("error", 0, "Out of balance", difference, row_id="out_of_balance"))

    return {
        "columns": list(columns),
        "rows": rows,
        "totals": {
            "assets": total_assets, "liabilities": total_liabilities, "equity": total_equity,
            "liabilities_and_equity": total_le, "retained_earnings": retained_line, "net_income": net_income,
            "difference": difference,
        },
    }


# ---------------------------------------------------------------------------
# Ledger detail (General Ledger, P&L / Balance Sheet Detail, Account Ledger)
# ---------------------------------------------------------------------------

SPLIT = "-Split-"


def _kind(voucher):
    from .services import voucher_kind  # lazy: services imports models that import services

    return voucher_kind(voucher)


def ledger(*, codes=None, start=None, end=None, posted_only=True, exclude_close=False, with_opening=True, chart=None) -> list:
    """Per account in chart order: opening, each line with its split account and running balance, closing.

    Three queries whatever the account count: openings, the period's lines, and
    the other legs of those vouchers (for the split column).
    """
    chart = chart or load_chart()
    lines = AccountVoucherLine.objects.filter(voucher__deleted_at__isnull=True)
    if posted_only:
        lines = lines.filter(voucher__posted=YES)
    if exclude_close:
        lines = lines.exclude(voucher__source_ref__startswith=FS_PERIOD_CLOSE_PREFIX)
    if codes is not None:
        codes = set(codes)
        lines = lines.filter(account_no__in=list(codes))

    openings = {}
    if with_opening:
        before = aggregate({"o": Q(voucher_date__lt=start)}, codes=codes, posted_only=posted_only) if start else {}
        openings = {code: values["o"] for code, values in chart.with_openings(before, ["o"], codes=codes).items()}

    period = lines
    if start:
        period = period.filter(voucher_date__gte=start)
    if end:
        period = period.filter(voucher_date__lte=end)
    legs = {}
    for voucher_id, account_no in (
        AccountVoucherLine.objects.filter(voucher_id__in=period.values("voucher_id")).values_list("voucher_id", "account_no").distinct()
    ):
        legs.setdefault(voucher_id, set()).add(account_no)
    grouped = {}
    for line in period.select_related("voucher").order_by("voucher_date", "voucher_no", "line_number"):
        grouped.setdefault(line.account_no, []).append(line)

    order = [code for code in chart.ordered_codes() if codes is None or code in codes]
    order += sorted(code for code in set(grouped) | set(openings) if code not in chart.by_code)
    accounts = []
    for code in order:
        opening_raw = openings.get(code, ZERO)
        if code not in grouped and not opening_raw:
            continue
        node = chart.by_code.get(code)
        debit_natured = node is None or node.account_type in DEBIT_NATURE_TYPES
        sign = 1 if debit_natured else -1
        balance = sign * opening_raw
        opening = balance
        rows, total_debit, total_credit = [], ZERO, ZERO
        for line in grouped.get(code, []):
            debit, credit = line.debit_amount or ZERO, line.credit_amount or ZERO
            amount = sign * (debit - credit)
            balance += amount
            total_debit += debit
            total_credit += credit
            voucher = line.voucher
            others = legs.get(line.voucher_id, set()) - {code}
            rows.append({
                "line": line, "voucher": voucher, "date": line.voucher_date, "type": _kind(voucher),
                "number": line.voucher_no, "party": chart.title(voucher.party_account_no) if voucher.party_account_no else line.person_organization_title,
                "memo": line.remarks or voucher.remarks, "split": chart.title(next(iter(others))) if len(others) == 1 else (SPLIT if others else ""),
                "debit": debit, "credit": credit, "amount": amount, "balance": balance,
            })
        accounts.append({
            "code": code, "title": chart.title(code), "account_type": node.account_type if node else "", "inactive": bool(node and node.inactive),
            "debit_natured": debit_natured, "opening": opening, "rows": rows,
            "debit": total_debit, "credit": total_credit, "movement": balance - opening, "closing": balance,
        })
    return accounts


def journal(start, end, *, voucher_type="", posted_only=True, chart=None) -> list:
    """Every voucher in the period with all its lines; debits equal credits per voucher."""
    from .models import AccountVoucher

    chart = chart or load_chart()
    vouchers = AccountVoucher.objects.filter(voucher_date__range=(start, end)).prefetch_related("lines").order_by("voucher_date", "voucher_no")
    if posted_only:
        vouchers = vouchers.filter(posted=YES)
    if voucher_type:
        vouchers = vouchers.filter(voucher_type=voucher_type)
    out = []
    for voucher in vouchers:
        lines = [
            {"line": line, "code": line.account_no, "title": chart.title(line.account_no), "memo": line.remarks,
             "debit": line.debit_amount or ZERO, "credit": line.credit_amount or ZERO}
            for line in sorted(voucher.lines.all(), key=lambda item: item.line_number)
        ]
        debit = sum((line["debit"] for line in lines), ZERO)
        credit = sum((line["credit"] for line in lines), ZERO)
        out.append({"voucher": voucher, "type": _kind(voucher), "lines": lines, "debit": debit, "credit": credit, "balanced": debit == credit})
    return out


# ---------------------------------------------------------------------------
# Trial balance
# ---------------------------------------------------------------------------

TB_KEYS = ("o_dr", "o_cr", "p_dr", "p_cr", "c_dr", "c_cr")


def _split(raw):
    return (raw, ZERO) if raw >= 0 else (ZERO, -raw)


def trial_balance(start, end, *, tree=False, show=SHOW_ACTIVE, posted_only=True) -> dict:
    """Opening, period movement and closing per account, each split to Dr / Cr. ``start=None`` means no opening cut."""
    chart = load_chart()
    specs = {"move": range_q(start, end)}
    if start:
        specs["open"] = Q(voucher_date__lt=start)
    figures = aggregate(specs, posted_only=posted_only)
    raw = {}
    for code, values in figures.items():
        raw[code] = {"open": values.get("open", ZERO), "move": values["move"]}
    for code in chart.by_code:
        opening = chart.raw_opening(code)
        if opening:
            raw.setdefault(code, {"open": ZERO, "move": ZERO})["open"] += opening
    for values in raw.values():
        values["close"] = values["open"] + values["move"]

    keys = ["open", "move", "close"]
    if tree:
        builder = TreeBuilder(chart, raw, keys, show=show)
        rows = []
        for root in chart.roots:
            root_rows, _ = builder.node(root, 0)
            rows += root_rows
    else:
        rows = []
        for code in sorted(raw):
            node = chart.by_code.get(code)
            if node and node.children:
                continue
            values = raw[code]
            if show != SHOW_ALL and not any(values.values()) and not (show == SHOW_ACTIVE and code in figures):
                continue
            rows.append(_row("account", 0, f"{code} · {chart.title(code)}", values, code=code, inactive=bool(node and node.inactive)))
        if show == SHOW_ALL:
            listed = {row["code"] for row in rows}
            for code, node in sorted(chart.by_code.items()):
                if not node.children and code not in listed and not node.inactive:
                    rows.append(_row("account", 0, f"{code} · {node.title}", _zeros(keys), code=code))
            rows.sort(key=lambda row: row["code"])

    totals = {key: ZERO for key in TB_KEYS}
    for row in rows:
        values = row["values"]
        split = {}
        for prefix, key in (("o", "open"), ("p", "move"), ("c", "close")):
            split[f"{prefix}_dr"], split[f"{prefix}_cr"] = _split(values.get(key, ZERO))
        row["values"] = split
        if row["kind"] == "account":
            for key in TB_KEYS:
                totals[key] += split[key]
    rows.append(_row("grand", 0, "Total", dict(totals), row_id="tb-total"))
    return {"rows": rows, "totals": totals, "balanced": all(totals[f"{p}_dr"] == totals[f"{p}_cr"] for p in "opc")}


# ---------------------------------------------------------------------------
# Cash flow (indirect method)
# ---------------------------------------------------------------------------

CF_OPERATING = "operating"
CF_INVESTING = "investing"
CF_FINANCING = "financing"
CF_LABELS = {
    CF_OPERATING: ("Operating Activities", "Net cash provided by operating activities"),
    CF_INVESTING: ("Investing Activities", "Net cash provided by investing activities"),
    CF_FINANCING: ("Financing Activities", "Net cash provided by financing activities"),
}


def cash_codes(chart) -> set:
    current = chart.find(FS_CURRENT_ASSETS_PATH)
    codes = set()
    for node in current.children if current else []:
        if node.title in FS_CASH_GROUP_TITLES:
            codes |= chart.leaf_codes(node)
    return codes


def cash_flow(columns, *, show=SHOW_ACTIVE, posted_only=True) -> dict:
    """Net Income adjusted by the change in every non-cash balance-sheet account, by activity.

    Period closes are left out on both sides: they only move Revenue/Expense into
    Retained Earnings, which nets to nothing in cash.
    """
    keys = [column.key for column in columns]
    chart = load_chart()
    cash = cash_codes(chart)
    pl_codes = chart.codes_of(*PL_TYPES)
    current = set()
    for path in (FS_CURRENT_ASSETS_PATH, FS_CURRENT_LIABILITIES_PATH):
        node = chart.find(path)
        if node:
            current |= chart.descendant_codes(node)

    specs = {}
    for column in columns:
        specs[f"m:{column.key}"] = without_close(range_q(column.start, column.end))
        if column.start:
            specs[f"o:{column.key}"] = Q(voucher_date__lt=column.start) & Q(account_no__in=list(cash))
    figures = aggregate(specs, posted_only=posted_only)

    def movement(code):
        values = figures.get(code) or {}
        return {key: values.get(f"m:{key}", ZERO) for key in keys}

    net_income = {key: -sum((movement(code)[key] for code in pl_codes if code in figures), ZERO) for key in keys}
    opening_raw = sum((chart.raw_opening(code) for code in cash), ZERO)
    begin = {key: opening_raw + sum(((figures.get(code) or {}).get(f"o:{key}", ZERO) for code in cash), ZERO) for key in keys}
    cash_move = {key: sum((movement(code)[key] for code in cash if code in figures), ZERO) for key in keys}

    sections = {CF_OPERATING: [], CF_INVESTING: [], CF_FINANCING: []}
    order = [code for code in chart.ordered_codes() if code in figures]
    order += sorted(code for code in figures if code not in chart.by_code)
    for code in order:
        node = chart.by_code.get(code)
        if code in cash or code in pl_codes or (node and node.children and code not in figures):
            continue
        effect = {key: -value for key, value in movement(code).items()}
        if not any(effect.values()) and show != SHOW_ALL:
            continue
        if node is None or code in current:
            section = CF_OPERATING
        elif node.account_type == ACCOUNT_TYPE_ASSET:
            section = CF_INVESTING
        else:
            section = CF_FINANCING
        sections[section].append((code, effect, bool(node and node.inactive)))

    rows, totals = [], {}
    for key, (label, total_label) in CF_LABELS.items():
        body = []
        if key == CF_OPERATING:
            body.append(_row("computed", 1, "Net Income", net_income, row_id="net_income", parent=key))
            adjust = sections[key]
            if adjust:
                adjust_total = _zeros(keys)
                adjust_rows = []
                for code, effect, inactive in adjust:
                    adjust_rows.append(_row("account", 2, chart.title(code), effect, code=code, parent="adjust", inactive=inactive))
                    adjust_total = _add(adjust_total, effect)
                body += [
                    _row("group", 1, "Adjustments to reconcile Net Income to net cash", adjust_total, row_id="adjust", parent=key, collapsible=True),
                    *adjust_rows,
                    _row("total", 1, "Total adjustments", adjust_total, row_id="adjust-total", parent="adjust"),
                ]
            total = _add(net_income, sum_values([effect for _c, effect, _i in adjust], keys))
        else:
            for code, effect, inactive in sections[key]:
                body.append(_row("account", 1, chart.title(code), effect, code=code, parent=key, inactive=inactive))
            total = sum_values([effect for _c, effect, _i in sections[key]], keys)
        totals[key] = total
        if key != CF_OPERATING and not body and show != SHOW_ALL:
            continue
        rows += [
            _row("section", 0, label, total, row_id=key, collapsible=True),
            *body,
            _row("total", 0, total_label, total, row_id=f"{key}-total", parent=key),
        ]

    net = sum_values(list(totals.values()), keys)
    end = _add(begin, net)
    actual = _add(begin, cash_move)
    difference = _add(actual, end, -1)
    rows += [
        _row("grand", 0, "Net cash increase for period", net, row_id="net_change"),
        _row("computed", 0, "Cash at beginning of period", begin, row_id="cash_begin"),
        _row("grand", 0, "Cash at end of period", end, row_id="cash_end"),
    ]
    if any(difference.values()):
        rows.append(_row("error", 0, "Difference to cash and bank balance", difference, row_id="cash_difference"))
    return {"rows": rows, "totals": {**totals, "net_income": net_income, "net_change": net, "begin": begin, "end": end, "actual_end": actual, "difference": difference}}


def changes_in_equity(columns, *, show=SHOW_ACTIVE, posted_only=True) -> dict:
    """Equity at the start, each capital account's movement, Net Income, equity at the end; ties to the balance sheet."""
    keys = [column.key for column in columns]
    chart = load_chart()
    capital_codes = chart.codes_of(ACCOUNT_TYPE_CAPITAL)
    pl_codes = chart.codes_of(*PL_TYPES)
    equity_codes = capital_codes | pl_codes
    specs = {}
    for column in columns:
        specs[f"m:{column.key}"] = without_close(range_q(column.start, column.end))
        specs[f"e:{column.key}"] = Q(voucher_date__lte=column.end)
        if column.start:
            specs[f"o:{column.key}"] = Q(voucher_date__lt=column.start)
    figures = aggregate(specs, codes=equity_codes, posted_only=posted_only)
    openings = -sum((chart.raw_opening(code) for code in equity_codes), ZERO)

    def equity(prefix, key):
        return openings - sum(((values.get(f"{prefix}:{key}") or ZERO) for values in figures.values()), ZERO)

    begin = {key: equity("o", key) for key in keys}
    end = {key: equity("e", key) for key in keys}
    net_income = {key: -sum((figures[code][f"m:{key}"] for code in pl_codes if code in figures), ZERO) for key in keys}
    rows = [_row("computed", 0, "Equity at beginning of period", begin, row_id="equity_begin")]
    moved = dict(begin)
    for code in chart.ordered_codes():
        if code not in capital_codes or code not in figures:
            continue
        values = {key: -figures[code][f"m:{key}"] for key in keys}
        if not any(values.values()) and show != SHOW_ALL:
            continue
        node = chart.by_code[code]
        rows.append(_row("account", 1, node.title, values, code=code, inactive=node.inactive))
        moved = _add(moved, values)
    rows.append(_row("computed", 1, "Net Income", net_income, row_id="net_income"))
    computed_end = _add(moved, net_income)
    rows.append(_row("grand", 0, "Equity at end of period", end, row_id="equity_end"))
    difference = _add(end, computed_end, -1)
    if any(difference.values()):
        rows.append(_row("error", 0, "Out of balance", difference, row_id="out_of_balance"))
    return {"rows": rows, "totals": {"begin": begin, "end": end, "net_income": net_income, "difference": difference}}


def sum_values(items, keys) -> dict:
    total = _zeros(keys)
    for values in items:
        total = _add(total, values)
    return total


# ---------------------------------------------------------------------------
# Customise options (all state in the querystring)
# ---------------------------------------------------------------------------

PRESET_MONTH = "month"
PRESET_LAST_MONTH = "last_month"
PRESET_QUARTER = "quarter"
PRESET_LAST_QUARTER = "last_quarter"
PRESET_YTD = "ytd"
PRESET_FISCAL = "fiscal"
PRESET_FISCAL_YTD = "fiscal_ytd"
PRESET_LAST_FISCAL = "last_fiscal"
PRESET_ALL = "all"
PRESET_CUSTOM = "custom"
PRESET_CHOICES = (
    (PRESET_MONTH, "This Month"),
    (PRESET_LAST_MONTH, "Last Month"),
    (PRESET_QUARTER, "This Quarter"),
    (PRESET_LAST_QUARTER, "Last Quarter"),
    (PRESET_YTD, "Year to Date"),
    (PRESET_FISCAL, "This Fiscal Year"),
    (PRESET_FISCAL_YTD, "Fiscal Year to Date"),
    (PRESET_LAST_FISCAL, "Last Fiscal Year"),
    (PRESET_ALL, "All Dates"),
    (PRESET_CUSTOM, "Custom"),
)

BY_TOTAL = "total"
BY_MONTH = "month"
BY_QUARTER = "quarter"
BY_YEAR = "year"
BY_CHOICES = ((BY_TOTAL, "Total only"), (BY_MONTH, "Months"), (BY_QUARTER, "Quarters"), (BY_YEAR, "Years"))

COMPARE_PP = "pp"
COMPARE_PY = "py"
COMPARE_CHOICES = (("", "None"), (COMPARE_PP, "Previous period"), (COMPARE_PY, "Previous year"))

NEG_PAREN = "paren"
NEG_MINUS = "minus"
NEG_CHOICES = ((NEG_PAREN, "(1,234.00)"), (NEG_MINUS, "-1,234.00"))


def _parse_date(raw):
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def month_end(day: date) -> date:
    following = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return following - timedelta(days=1)


def shift_months(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    first = date(year, month + 1, 1)
    return first.replace(day=min(day.day, month_end(first).day))


def _is_month_end(day: date) -> bool:
    return day == month_end(day)


def _quarter_start(day: date) -> date:
    return date(day.year, (day.month - 1) // 3 * 3 + 1, 1)


def _fiscal_bounds(day: date, years):
    for start, end in years:
        if start <= day <= end:
            return start, end
    start = fiscal_year_start(day, years)
    return start, shift_months(start, 12) - timedelta(days=1)


def _preset_bounds(preset, today, years):
    if preset == PRESET_MONTH:
        return today.replace(day=1), today
    if preset == PRESET_LAST_MONTH:
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if preset == PRESET_QUARTER:
        return _quarter_start(today), today
    if preset == PRESET_LAST_QUARTER:
        end = _quarter_start(today) - timedelta(days=1)
        return _quarter_start(end), end
    if preset == PRESET_YTD:
        return today.replace(month=1, day=1), today
    if preset == PRESET_FISCAL:
        return _fiscal_bounds(today, years)
    if preset == PRESET_FISCAL_YTD:
        return _fiscal_bounds(today, years)[0], today
    if preset == PRESET_LAST_FISCAL:
        start, _ = _fiscal_bounds(today, years)
        return _fiscal_bounds(start - timedelta(days=1), years)
    if preset == PRESET_ALL:
        return None, today
    return None, None


@dataclass
class Options:
    preset: str
    start: date | None
    end: date
    label: str
    by: str = BY_TOTAL
    compare: str = ""
    change: bool = False
    pct_change: bool = False
    pct_income: bool = False
    show: str = SHOW_ACTIVE
    neg: str = NEG_PAREN
    red: bool = False
    thousands: bool = False
    no_paisa: bool = False


def resolve_options(request, *, as_of=False, default_preset=PRESET_FISCAL_YTD, today=None) -> Options:
    """Every Customise control read from the querystring, with QuickBooks defaults."""
    get = request.GET
    today = today or timezone.localdate()
    labels = dict(PRESET_CHOICES)
    preset = get.get("preset") or default_preset
    if preset not in labels:
        preset = default_preset

    if as_of:
        end = _parse_date(get.get("as_of")) or today
        start, label, preset = None, f"As of {end:%d %b %Y}", PRESET_CUSTOM
    else:
        start, end = _preset_bounds(preset, today, _fiscal_years())
        if end is None:
            start = _parse_date(get.get("date_from")) or today.replace(day=1)
            end = _parse_date(get.get("date_to")) or today
            if end < start:
                start, end = end, start
        label = f"{start:%d %b %Y} – {end:%d %b %Y}" if start else f"All dates to {end:%d %b %Y}"

    def pick(name, choices, default):
        value = get.get(name, default)
        return value if value in dict(choices) else default

    def flag(name):
        return get.get(name) == "1"

    return Options(
        preset=preset, start=start, end=end, label=label,
        by=pick("by", BY_CHOICES, BY_TOTAL), compare=pick("compare", COMPARE_CHOICES, ""),
        change=flag("chg"), pct_change=flag("pct"), pct_income=flag("poi"),
        show=pick("show", SHOW_CHOICES, SHOW_ACTIVE), neg=pick("neg", NEG_CHOICES, NEG_PAREN),
        red=flag("red"), thousands=flag("k"), no_paisa=flag("np"),
    )


def _first_posting_date():
    return (
        AccountVoucherLine.objects.filter(voucher__posted=YES).order_by("voucher_date")
        .values_list("voucher_date", flat=True).first()
    )


def split_period(start, end, by) -> list:
    """Base columns for ``start..end`` cut by month / quarter / year (``start=None`` runs from inception)."""
    if by == BY_TOTAL:
        return [Column("c0", "Total", start, end)]
    start = start or _first_posting_date() or end
    step = {BY_MONTH: 1, BY_QUARTER: 3, BY_YEAR: 12}[by]
    cursor = {BY_MONTH: start.replace(day=1), BY_QUARTER: _quarter_start(start), BY_YEAR: start.replace(month=1, day=1)}[by]
    columns = []
    while cursor <= end:
        stop = shift_months(cursor, step) - timedelta(days=1)
        label = {BY_MONTH: f"{cursor:%b %Y}", BY_QUARTER: f"Q{(cursor.month - 1) // 3 + 1} {cursor:%Y}", BY_YEAR: f"{cursor:%Y}"}[by]
        columns.append(Column(f"c{len(columns)}", label, max(cursor, start), min(stop, end)))
        cursor = shift_months(cursor, step)
    return columns


def _back(day: date, months: int) -> date:
    shifted = shift_months(day, -months)
    return month_end(shifted) if _is_month_end(day) else shifted


def compare_column(column, compare, *, span=None, point=False):
    """Twin of ``column``: same dates a year back (PY) or the stretch just before the report (PP).

    ``point`` columns (balance sheet) move their as-of date back one month for PP.
    """
    suffix = " (PY)" if compare == COMPARE_PY else " (PP)"
    key = f"{column.key}_c"
    if compare == COMPARE_PY:
        start = shift_months(column.start, -12) if column.start else None
        end = _back(column.end, 12)
    elif point:
        start, end = None, _back(column.end, 1)
    else:
        span_start, span_end = span or (column.start, column.end)
        if span_start and span_start.day == 1 and _is_month_end(span_end):
            months = (span_end.year - span_start.year) * 12 + span_end.month - span_start.month + 1
            start, end = shift_months(column.start, -months), _back(column.end, months)
        else:
            days = (span_end - span_start).days + 1 if span_start else 0
            start = column.start - timedelta(days=days) if column.start else None
            end = column.end - timedelta(days=days)
    if point or not start:
        label = f"{end:%d %b %Y}{suffix}"
    else:
        label = f"{start:%d %b %y} – {end:%d %b %y}{suffix}"
    return Column(key, label, start, end)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _percent(part, whole):
    if not whole:
        return None
    return (Decimal(part) / abs(Decimal(whole)) * 100).quantize(Decimal("0.01"))


def display_columns(base, compared, options, *, with_income=False) -> list:
    """Screen columns in order: each base column, % of Income, its twin, Change, % Change."""
    twins = {column.key: column for column in compared}
    out = []
    for column in base:
        out.append({"key": column.key, "label": column.label, "kind": "money", "column": column})
        if options.pct_income and with_income:
            out.append({"key": f"{column.key}_poi", "label": "% of Income", "kind": "pct", "source": column.key})
        twin = twins.get(f"{column.key}_c")
        if not twin:
            continue
        out.append({"key": twin.key, "label": twin.label, "kind": "money", "column": twin})
        if options.pct_income and with_income:
            out.append({"key": f"{twin.key}_poi", "label": "% of Income", "kind": "pct", "source": twin.key})
        if options.change:
            out.append({"key": f"{column.key}_chg", "label": "Change", "kind": "money", "base": column.key, "twin": twin.key})
        if options.pct_change:
            out.append({"key": f"{column.key}_pct", "label": "% Change", "kind": "pct", "base": column.key, "twin": twin.key})
    return out


def format_money(value, options) -> str:
    value = Decimal(value or 0)
    if options.thousands:
        value = value / 1000
    text = f"{abs(value):,.{0 if options.no_paisa else 2}f}"
    if value < 0:
        return f"({text})" if options.neg == NEG_PAREN else f"-{text}"
    return text


def present(rows, columns, options, *, income=None, drill=None, computed_drill=None, blank_zero=False) -> list:
    """Rows with ready-to-render ``cells`` (text, negative flag, drill URL) per screen column."""
    out = []
    for row in rows:
        values = row["values"]
        cells = []
        for column in columns:
            if "source" in column:
                value = _percent(values.get(column["source"], ZERO), (income or {}).get(column["source"]))
            elif "twin" in column:
                base, twin = values.get(column["base"], ZERO), values.get(column["twin"], ZERO)
                value = base - twin if column["kind"] == "money" else _percent(base - twin, twin)
            else:
                value = values.get(column["key"], ZERO)
            if value is None or (blank_zero and not value):
                cells.append({"text": "", "negative": False, "url": "", "value": None})
                continue
            url = ""
            if column.get("column"):
                if row["kind"] == "account" and drill:
                    url = drill(row["code"], column["column"])
                elif row["kind"] in ("computed", "grand") and computed_drill:
                    url = computed_drill(row, column["column"])
            text = f"{value:,.2f}%" if column["kind"] == "pct" else format_money(value, options)
            cells.append({"text": text, "negative": value < 0, "url": url, "value": value})
        out.append({**row, "cells": cells})
    return out
