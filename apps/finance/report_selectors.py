"""Accounts reporting reads (catalogue group H). Voucher lines are the only source of money figures."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Max, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from apps.core.constants import (
    ACCOUNT_TYPE_EXPENSE,
    GL_PAYABLES_PARENT,
    GL_PAYABLES_TITLES,
    FIN_VOUCHER_STATUS_CHOICES,
    FIN_VOUCHER_TYPE_CHOICES,
    STATUS_ACTIVE,
    STATUS_REVERSED,
    YES,
)
from apps.core.reporting import ZERO, money

from .models import AccountVoucher, AccountVoucherLine, ChartOfAccount, FiscalYear
from .services import DEBIT_NATURE_TYPES

MONEY = DecimalField(max_digits=18, decimal_places=2)
TYPE_LABELS = dict(FIN_VOUCHER_TYPE_CHOICES)
STATUS_LABELS = dict(FIN_VOUCHER_STATUS_CHOICES)
PARTY_CUSTOMER = "customer"
PARTY_SUPPLIER = "supplier"
PARTY_TYPE_CHOICES = ((PARTY_CUSTOMER, "Customer"), (PARTY_SUPPLIER, "Supplier"))
SOURCE_DOCS = (
    ("inv_pos_masters:", "Sale"),
    ("inv_pos_return_masters:", "Sale Return"),
    ("inv_purchase_invoices_paid:", "Payment"),
    ("inv_purchase_invoices:", "Purchase"),
    ("inv_purchase_return_masters:", "Purchase Return"),
    ("period_close:", "Period Close"),
    ("inventory_adjustment:", "Stock Adjustment"),
)


def _sum(expression, **kw):
    return Coalesce(Sum(expression, **kw), Value(Decimal("0")), output_field=MONEY)


def _titles():
    return dict(ChartOfAccount.objects.exclude(code="").values_list("code", "title"))


def _user_name(user):
    return (user.get_full_name() or user.username) if user else ""


def _source_kind(source_ref):
    if "_reversal:" in source_ref:
        return "Reversal"
    for prefix, label in SOURCE_DOCS:
        if source_ref.startswith(prefix):
            return label
    return ""


# ---------------------------------------------------------------------------
# Filter options
# ---------------------------------------------------------------------------

def money_codes(group_title):
    """Leaf codes under Current Assets > ``group_title`` from one read of the active chart."""
    nodes = list(ChartOfAccount.objects.filter(status=STATUS_ACTIVE).values_list("pk", "parent_id", "title", "code"))
    children = defaultdict(list)
    for pk, parent_id, _title, _code in nodes:
        children[parent_id].append(pk)
    by_pk = {pk: (title, code) for pk, _parent, title, code in nodes}
    roots = [pk for pk in children[None] if by_pk[pk][0] == "ASSETS"]
    current = [pk for root in roots for pk in children[root] if by_pk[pk][0] == "Current Assets"]
    groups = [pk for parent in current for pk in children[parent] if by_pk[pk][0] == group_title]
    codes = set()

    def walk(pk):
        if not children[pk]:
            if by_pk[pk][1]:
                codes.add(by_pk[pk][1])
            return
        for child in children[pk]:
            walk(child)

    for group in groups:
        walk(group)
    return codes


def cash_account_options():
    return ChartOfAccount.objects.filter(code__in=money_codes("Cash")).order_by("code").values_list("code", "title")


def bank_account_options():
    return ChartOfAccount.objects.filter(code__in=money_codes("Bank")).order_by("code").values_list("code", "title")


def leaf_account_options():
    return ChartOfAccount.objects.filter(children__isnull=True, status=STATUS_ACTIVE).exclude(code="").order_by("code").values_list("code", "title")


def receivables_group():
    return ChartOfAccount.objects.filter(title="Receivables", parent__title="Current Assets", parent__parent__title="ASSETS").first()


def payables_group():
    return ChartOfAccount.objects.filter(title__in=GL_PAYABLES_TITLES, parent__title=GL_PAYABLES_PARENT[-1], parent__parent__title=GL_PAYABLES_PARENT[0]).first()


def party_options():
    groups = [g for g in (receivables_group(), payables_group()) if g]
    return ChartOfAccount.objects.filter(parent__in=groups, children__isnull=True).order_by("parent__sort_order", "title").values_list("code", "title")


def fiscal_year_options():
    return FiscalYear.objects.order_by("-start_date").values_list("pk", "title")


def voucher_user_options():
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(pk__in=AccountVoucher.objects.values("created_by_id")).order_by("username")
    return [(u.pk, u.get_full_name() or u.username) for u in users]


# ---------------------------------------------------------------------------
# 50. Cash Book
# ---------------------------------------------------------------------------

def _money_book(codes, start, end):
    """Opening before ``start`` and the day-wise receipts/payments over ``codes``: two queries."""
    lines = AccountVoucherLine.objects.filter(account_no__in=codes)
    opening_master = ChartOfAccount.objects.filter(code__in=codes).aggregate(v=_sum("opening_balance"))["v"]
    earlier = lines.filter(voucher_date__lt=start).aggregate(d=_sum("debit_amount"), c=_sum("credit_amount"))
    opening = money(opening_master + earlier["d"] - earlier["c"])
    daily = {
        r["voucher_date"]: r for r in lines.filter(voucher_date__range=(start, end)).values("voucher_date")
        .annotate(d=_sum("debit_amount"), c=_sum("credit_amount"), n=Count("id")).order_by("voucher_date")
    }
    return opening, daily


def cash_book(start, end, account=None):
    codes = {account} if account else money_codes("Cash")
    opening, daily = _money_book(codes, start, end)
    rows, balance = [], opening
    for day, r in sorted(daily.items()):
        receipts, payments = money(r["d"]), money(r["c"])
        closing = money(balance + receipts - payments)
        rows.append({"date": day, "opening": balance, "receipts": receipts, "payments": payments, "closing": closing, "entries": r["n"], "negative": closing < 0})
        balance = closing
    totals = {"receipts": sum((r["receipts"] for r in rows), ZERO), "payments": sum((r["payments"] for r in rows), ZERO), "entries": sum(r["entries"] for r in rows)}
    totals.update({"opening": opening, "closing": balance, "days": len(rows)})
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 51. Bank Book
# ---------------------------------------------------------------------------

def bank_book(start, end, account=None):
    codes = {account} if account else money_codes("Bank")
    opening, _daily = _money_book(codes, start, end)
    titles = _titles()
    lines = list(
        AccountVoucherLine.objects.filter(account_no__in=codes, voucher_date__range=(start, end))
        .select_related("voucher", "voucher__payment_method").order_by("voucher_date", "voucher_no", "line_number")
    )
    voucher_ids = {l.voucher_id for l in lines}
    counterparts = defaultdict(set)
    for vid, code in AccountVoucherLine.objects.filter(voucher_id__in=voucher_ids).exclude(account_no__in=codes).values_list("voucher_id", "account_no"):
        counterparts[vid].add(titles.get(code, code))
    rows, balance = [], opening
    for l in lines:
        v = l.voucher
        deposit, withdrawal = money(l.debit_amount), money(l.credit_amount)
        balance = money(balance + deposit - withdrawal)
        rows.append({
            "pk": v.pk, "date": l.voucher_date, "voucher_no": l.voucher_no, "type": TYPE_LABELS.get(v.voucher_type, v.voucher_type),
            "bank": titles.get(l.account_no, l.account_no), "counterpart": ", ".join(sorted(counterparts.get(v.pk, ()))),
            "method": v.payment_method.title if v.payment_method_id else "", "cheque_no": v.cheque_no, "cheque_date": v.cheque_date,
            "reference": v.transaction_ref, "remarks": l.remarks or v.remarks, "deposit": deposit, "withdrawal": withdrawal, "balance": balance, "negative": balance < 0,
        })
    totals = {"deposit": sum((r["deposit"] for r in rows), ZERO), "withdrawal": sum((r["withdrawal"] for r in rows), ZERO), "opening": opening, "closing": balance, "entries": len(rows)}
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 53. Party Ledger
# ---------------------------------------------------------------------------

def party_account(code):
    return ChartOfAccount.objects.filter(code=code, children__isnull=True).select_related("parent").first()


def party_ledger(start, end, code):
    """A customer or supplier statement: every voucher line on the party account, tagged with its source document, plus sacks held for a wheat supplier."""
    from apps.inventory.models import Supplier
    from apps.products.models import PartyBardanaLedger

    account = party_account(code) if code else None
    if account is None:
        return {"rows": [], "totals": {"opening": ZERO, "debit": ZERO, "credit": ZERO, "closing": ZERO, "sacks": ZERO, "entries": 0}, "account": None, "party_type": ""}
    debit_natured = account.account_type in DEBIT_NATURE_TYPES
    party_type = PARTY_CUSTOMER if debit_natured else PARTY_SUPPLIER
    signed = (lambda d, c: d - c) if debit_natured else (lambda d, c: c - d)
    lines = AccountVoucherLine.objects.filter(account_no=code)
    earlier = lines.filter(voucher_date__lt=start).aggregate(d=_sum("debit_amount"), c=_sum("credit_amount"))
    opening = money((account.opening_balance or ZERO) + signed(earlier["d"], earlier["c"]))

    supplier = Supplier.objects.filter(name=account.title).first() if party_type == PARTY_SUPPLIER else None
    sack_rows = []
    sacks_opening = ZERO
    if supplier:
        sacks = PartyBardanaLedger.objects.filter(party=supplier)
        sacks_opening = sacks.filter(entry_date__lt=start).aggregate(q=Coalesce(Sum("quantity"), Value(Decimal("0")), output_field=DecimalField(max_digits=18, decimal_places=3)))["q"]
        sack_rows = list(sacks.filter(entry_date__range=(start, end)).select_related("bardana_item").order_by("entry_date", "id"))

    rows = []
    for l in lines.filter(voucher_date__range=(start, end)).select_related("voucher").order_by("voucher_date", "voucher_no", "line_number"):
        v = l.voucher
        kind = _source_kind(v.source_ref)
        rows.append({
            "date": l.voucher_date, "voucher_no": l.voucher_no, "voucher_pk": v.pk, "kind": kind or TYPE_LABELS.get(v.voucher_type, v.voucher_type),
            "remarks": l.remarks or v.remarks, "debit": money(l.debit_amount), "credit": money(l.credit_amount), "sacks_in": ZERO, "sacks_out": ZERO, "_seq": 0,
        })
    for s in sack_rows:
        rows.append({
            "date": s.entry_date, "voucher_no": s.reference, "voucher_pk": None, "kind": "Sacks", "remarks": f"{s.bardana_item.name} {s.remarks}".strip(),
            "debit": ZERO, "credit": ZERO, "sacks_in": s.quantity if s.quantity > 0 else ZERO, "sacks_out": -s.quantity if s.quantity < 0 else ZERO, "_seq": 1,
        })
    rows.sort(key=lambda r: (r["date"], r["_seq"], r["voucher_no"]))
    balance, sack_balance = opening, sacks_opening
    for r in rows:
        balance = money(balance + signed(r["debit"], r["credit"]))
        sack_balance += r["sacks_in"] - r["sacks_out"]
        r["balance"], r["sacks"] = balance, sack_balance
        r.pop("_seq")
    totals = {
        "opening": opening, "debit": sum((r["debit"] for r in rows), ZERO), "credit": sum((r["credit"] for r in rows), ZERO), "closing": balance,
        "sacks_in": sum((r["sacks_in"] for r in rows), ZERO), "sacks_out": sum((r["sacks_out"] for r in rows), ZERO), "sacks": sack_balance, "entries": len(rows),
    }
    return {"rows": rows, "totals": totals, "account": account, "party_type": party_type, "has_sacks": supplier is not None}


# ---------------------------------------------------------------------------
# 54. Voucher Register by Type
# ---------------------------------------------------------------------------

def voucher_register(start, end, voucher_type=None, status=None, account=None, posted=None):
    qs = AccountVoucher.objects.filter(voucher_date__range=(start, end)).select_related("created_by")
    if voucher_type:
        qs = qs.filter(voucher_type=voucher_type)
    if status:
        qs = qs.filter(status=status)
    if posted:
        qs = qs.filter(posted=posted)
    if account:
        qs = qs.filter(Q(account_no=account) | Q(party_account_no=account) | Q(lines__account_no=account)).distinct()
    titles = _titles()
    rows = []
    for v in qs.order_by("-voucher_date", "-id"):
        kind = _source_kind(v.source_ref)
        rows.append({
            "pk": v.pk, "voucher_no": v.voucher_no, "date": v.voucher_date, "type": TYPE_LABELS.get(v.voucher_type, v.voucher_type), "type_code": v.voucher_type,
            "source": kind, "account": titles.get(v.account_no, v.account_no), "party": titles.get(v.party_account_no, v.party_account_no),
            "debit": money(v.debit_amount), "credit": money(v.credit_amount), "status": v.status, "status_label": STATUS_LABELS.get(v.status, v.status),
            "posted": "Yes" if v.posted == YES else "", "posted_by": _user_name(v.created_by), "attachment": "Yes" if v.payment_receipt else "",
            "cheque_no": v.cheque_no, "remarks": v.remarks, "unbalanced": v.debit_amount != v.credit_amount,
        })
    totals = {"debit": sum((r["debit"] for r in rows), ZERO), "credit": sum((r["credit"] for r in rows), ZERO), "vouchers": len(rows)}
    by_type = defaultdict(lambda: {"count": 0, "amount": ZERO})
    for r in rows:
        by_type[r["type_code"]]["count"] += 1
        by_type[r["type_code"]]["amount"] += r["debit"]
    totals["by_type"] = dict(by_type)
    totals["unposted"] = sum(1 for r in rows if not r["posted"])
    totals["attachments"] = sum(1 for r in rows if r["attachment"])
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 59. Expense Analysis
# ---------------------------------------------------------------------------

def month_keys(start, end):
    """``[(key, label, first_day)]`` for every month the period touches; keys stay stable across requests."""
    months, cursor = [], start.replace(day=1)
    while cursor <= end:
        months.append((f"m_{cursor:%Y_%m}", f"{cursor:%b %y}", cursor))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def expense_analysis(start, end, group=None):
    months = month_keys(start, end)
    accounts = ChartOfAccount.objects.filter(account_type=ACCOUNT_TYPE_EXPENSE, children__isnull=True, status=STATUS_ACTIVE).exclude(code="").select_related("parent")
    if group:
        accounts = accounts.filter(parent_id=group)
    accounts = list(accounts.order_by("code"))
    codes = [a.code for a in accounts]
    figures = defaultdict(dict)
    for r in (
        AccountVoucherLine.objects.filter(account_no__in=codes, voucher_date__range=(start, end))
        .annotate(month=TruncMonth("voucher_date")).values("account_no", "month").annotate(v=_sum(F("debit_amount") - F("credit_amount")))
    ):
        figures[r["account_no"]][f"m_{r['month']:%Y_%m}"] = money(r["v"])
    rows = []
    for a in accounts:
        row = {"code": a.code, "account": a.title, "group": a.parent.title if a.parent_id else ""}
        total = ZERO
        for key, _label, _day in months:
            row[key] = figures[a.code].get(key, ZERO)
            total += row[key]
        if not total and not any(row[k] for k, *_ in months):
            continue
        row["total"] = money(total)
        rows.append(row)
    grand = sum((r["total"] for r in rows), ZERO)
    for r in rows:
        r["share"] = (r["total"] / grand * 100).quantize(Decimal("0.01")) if grand else ZERO
    totals = {key: sum((r[key] for r in rows), ZERO) for key, *_ in months}
    totals.update({"total": grand, "share": Decimal("100.00") if grand else ZERO, "accounts": len(rows)})
    months_seen = sum(1 for key, *_ in months if totals[key])
    totals["avg_month"] = money(grand / months_seen) if months_seen else ZERO
    top = max(rows, key=lambda r: r["total"], default=None)
    totals["top"] = (top["account"], top["total"]) if top else ("", ZERO)
    return {"rows": rows, "totals": totals, "months": months}


def expense_group_options():
    return ChartOfAccount.objects.filter(account_type=ACCOUNT_TYPE_EXPENSE, children__isnull=False).distinct().order_by("code").values_list("pk", "title")


# ---------------------------------------------------------------------------
# 60. Receivable / Payable Summary
# ---------------------------------------------------------------------------

def receivable_payable(as_of, party_type=None):
    groups = []
    receivables, payables = receivables_group(), payables_group()
    if party_type in (None, "", PARTY_CUSTOMER) and receivables:
        groups.append((receivables, PARTY_CUSTOMER, "Customer"))
    if party_type in (None, "", PARTY_SUPPLIER) and payables:
        groups.append((payables, PARTY_SUPPLIER, "Supplier"))
    accounts = list(ChartOfAccount.objects.filter(parent__in=[g for g, *_ in groups], children__isnull=True).exclude(code="").order_by("title"))
    kinds = {g.pk: (kind, label) for g, kind, label in groups}
    figures = {
        r["account_no"]: r for r in AccountVoucherLine.objects.filter(account_no__in=[a.code for a in accounts], voucher_date__lte=as_of)
        .values("account_no").annotate(d=_sum("debit_amount"), c=_sum("credit_amount"), last=Max("voucher_date"), n=Count("id"))
    }
    rows = []
    for a in accounts:
        f = figures.get(a.code, {})
        kind, label = kinds[a.parent_id]
        debit, credit = money(f.get("d")), money(f.get("c"))
        opening = money(a.opening_balance)
        balance = money(opening + (debit - credit if kind == PARTY_CUSTOMER else credit - debit))
        if not (opening or debit or credit):
            continue
        last = f.get("last")
        rows.append({
            "code": a.code, "party": a.title, "party_type": kind, "type": label, "opening": opening, "debit": debit, "credit": credit,
            "balance": balance, "receivable": balance if kind == PARTY_CUSTOMER else ZERO, "payable": balance if kind == PARTY_SUPPLIER else ZERO,
            "last_activity": last, "idle_days": (as_of - last).days if last else None, "entries": f.get("n", 0), "negative": balance < 0,
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("opening", "debit", "credit", "balance", "receivable", "payable")}
    totals["customers"] = sum(1 for r in rows if r["party_type"] == PARTY_CUSTOMER)
    totals["suppliers"] = sum(1 for r in rows if r["party_type"] == PARTY_SUPPLIER)
    totals["net"] = money(totals["receivable"] - totals["payable"])
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 61. Opening Balance Report
# ---------------------------------------------------------------------------

def fiscal_year_for(pk=None, today=None):
    if pk:
        fiscal = FiscalYear.objects.filter(pk=pk).first()
        if fiscal:
            return fiscal
    if today:
        return FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).order_by("-start_date").first() or FiscalYear.objects.order_by("-start_date").first()
    return FiscalYear.objects.order_by("-start_date").first()


def opening_balances(start, account_type=None):
    """Every account's balance at the first day of a fiscal year: the master opening plus everything posted before ``start``."""
    accounts = ChartOfAccount.objects.filter(children__isnull=True, status=STATUS_ACTIVE).exclude(code="").select_related("parent")
    if account_type:
        accounts = accounts.filter(account_type=account_type)
    accounts = list(accounts.order_by("code"))
    carried = {
        r["account_no"]: r for r in AccountVoucherLine.objects.filter(voucher_date__lt=start, account_no__in=[a.code for a in accounts])
        .values("account_no").annotate(d=_sum("debit_amount"), c=_sum("credit_amount"))
    }
    closed = AccountVoucher.objects.filter(source_ref__startswith="period_close:", voucher_date__lt=start).order_by("-voucher_date").first()
    rows = []
    for a in accounts:
        f = carried.get(a.code)
        manual = money(a.opening_balance)
        brought = money(f["d"] - f["c"]) if f else ZERO
        if a.account_type not in DEBIT_NATURE_TYPES:
            brought = -brought
        balance = money(manual + brought)
        if not (manual or brought):
            continue
        debit, credit = (balance, ZERO) if a.account_type in DEBIT_NATURE_TYPES else (ZERO, balance)
        if balance < 0:
            debit, credit = (ZERO, -balance) if a.account_type in DEBIT_NATURE_TYPES else (-balance, ZERO)
        rows.append({
            "code": a.code, "account": a.title, "group": a.parent.title if a.parent_id else "", "account_type": a.account_type, "type": a.get_account_type_display(),
            "manual": manual, "carried": brought, "debit": debit, "credit": credit, "source": "Carried" if f else "Manual",
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("manual", "carried", "debit", "credit")}
    totals.update({"accounts": len(rows), "difference": money(totals["debit"] - totals["credit"]), "closed": closed, "manual_count": sum(1 for r in rows if r["source"] == "Manual"), "carried_count": sum(1 for r in rows if r["source"] == "Carried")})
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 63. Audit Trail
# ---------------------------------------------------------------------------

KIND_GL_REVERSAL = "gl_reversal"
KIND_INVOICE_REVERSAL = "invoice_reversal"
KIND_RETURN_REVERSAL = "return_reversal"
KIND_VOUCHER_EDIT = "voucher_edit"
KIND_MANUAL_VOUCHER = "manual_voucher"
AUDIT_KIND_CHOICES = (
    (KIND_GL_REVERSAL, "GL Reversal"),
    (KIND_INVOICE_REVERSAL, "Invoice Reversal"),
    (KIND_RETURN_REVERSAL, "Return Reversal"),
    (KIND_VOUCHER_EDIT, "Voucher Edited"),
    (KIND_MANUAL_VOUCHER, "Manual Voucher"),
)
AUDIT_KIND_LABELS = dict(AUDIT_KIND_CHOICES)
EDIT_GRACE = timedelta(minutes=1)


def audit_trail(start, end, kind=None, user=None):
    from apps.inventory.models import PurchaseInvoice, PurchaseReturnMaster

    wanted = {kind} if kind else set(AUDIT_KIND_LABELS)
    rows = []
    vouchers = AccountVoucher.objects.filter(created_at__date__range=(start, end)).select_related("created_by", "updated_by")
    if user:
        vouchers = vouchers.filter(Q(created_by_id=user) | Q(updated_by_id=user))
    edited = AccountVoucher.objects.filter(updated_at__date__range=(start, end), updated_at__gt=F("created_at") + EDIT_GRACE).select_related("created_by", "updated_by")
    if user:
        edited = edited.filter(updated_by_id=user)
    titles = _titles()
    if wanted & {KIND_GL_REVERSAL, KIND_MANUAL_VOUCHER}:
        for v in vouchers:
            is_reversal = "_reversal:" in v.source_ref
            k = KIND_GL_REVERSAL if is_reversal else KIND_MANUAL_VOUCHER if not v.source_ref else None
            if k is None or k not in wanted:
                continue
            rows.append(_audit_row(v.created_at, k, v.voucher_no, v.pk, "finance:account_voucher_detail", titles.get(v.account_no, v.account_no), v.debit_amount, v.remarks, _user_name(v.created_by), v.status, STATUS_LABELS.get(v.status, v.status)))
    if KIND_VOUCHER_EDIT in wanted:
        for v in edited:
            rows.append(_audit_row(v.updated_at, KIND_VOUCHER_EDIT, v.voucher_no, v.pk, "finance:account_voucher_detail", titles.get(v.account_no, v.account_no), v.debit_amount, f"created {v.created_at:%d %b %Y %H:%M}", _user_name(v.updated_by), v.status, STATUS_LABELS.get(v.status, v.status)))
    if KIND_INVOICE_REVERSAL in wanted:
        invoices = PurchaseInvoice.objects.filter(status=STATUS_REVERSED, reversed_on__range=(start, end)).select_related("supplier", "updated_by")
        if user:
            invoices = invoices.filter(updated_by_id=user)
        for i in invoices:
            rows.append(_audit_row(i.reversed_on, KIND_INVOICE_REVERSAL, i.invoice_num, i.pk, "inventory:purchase_invoice_detail", i.supplier.name, i.total_amount, i.reverse_reason, _user_name(i.updated_by), i.status, i.get_status_display()))
    if KIND_RETURN_REVERSAL in wanted:
        returns = PurchaseReturnMaster.objects.filter(status=STATUS_REVERSED, reversed_on__range=(start, end)).select_related("supplier", "updated_by")
        if user:
            returns = returns.filter(updated_by_id=user)
        for r in returns:
            rows.append(_audit_row(r.reversed_on, KIND_RETURN_REVERSAL, r.return_num or r.transaction_id, r.pk, "inventory:purchase_return_detail", r.supplier.name, r.returned_amount, r.reverse_reason, _user_name(r.updated_by), r.status, r.get_status_display()))
    rows.sort(key=lambda r: (r["date"], r["time"].isoformat() if r["time"] else ""), reverse=True)
    totals = {"entries": len(rows), "amount": sum((r["amount"] for r in rows), ZERO)}
    for k in AUDIT_KIND_LABELS:
        totals[k] = sum(1 for r in rows if r["kind_code"] == k)
    totals["reversed_amount"] = sum((r["amount"] for r in rows if r["kind_code"] in (KIND_GL_REVERSAL, KIND_INVOICE_REVERSAL, KIND_RETURN_REVERSAL)), ZERO)
    return {"rows": rows, "totals": totals}


def _audit_row(when, kind, number, pk, url, party, amount, reason, user, status, status_label):
    from django.utils import timezone

    stamp = timezone.localtime(when) if hasattr(when, "hour") else None
    return {
        "date": stamp.date() if stamp else when, "time": stamp, "kind_code": kind, "kind": AUDIT_KIND_LABELS[kind], "number": number, "pk": pk, "url": url,
        "voucher_pk": pk if url == "finance:account_voucher_detail" else None, "party": party, "amount": money(amount), "reason": reason, "user": user, "status": status, "status_label": status_label,
    }
