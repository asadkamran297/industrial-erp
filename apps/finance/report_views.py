"""Accounts reporting screens (catalogue group H)."""

from django.shortcuts import redirect
from django.urls import reverse

from apps.core.constants import FIN_COA_ACCOUNT_TYPE_CHOICES, FIN_VOUCHER_STATUS_CHOICES, FIN_VOUCHER_TYPE_CHOICES
from apps.core.formatting import format_amount
from apps.core.reporting import PRESET_FISCAL, ReportColumnsView, ReportExportView, ReportView, preset_bounds, resolve_as_of
from apps.core.table_columns import ColumnSet, col
from apps.inventory.report_views import _tile
from apps.inventory.report_views_purchase import _views

from . import report_selectors as sel

PAGE = "reports.accounts"
VOUCHER_LINK = "finance:account_voucher_detail"


# 50 ------------------------------------------------------------------------

CASH_BOOK_COLUMNS = ColumnSet("reports.cash_book", (
    col("date", "Date", "date", locked=True),
    col("opening", "Opening", "money"),
    col("receipts", "Receipts", "money", total=True),
    col("payments", "Payments", "money", total=True),
    col("closing", "Closing", "money", locked=True, tone_key="negative"),
    col("entries", "Entries", "int", total=True, default=False),
))


class CashBookView(ReportView):
    page = PAGE
    title = "Cash Book"
    template_name = "reports/generic.html"
    columns = CASH_BOOK_COLUMNS
    url_name = "finance:report_cash_book"
    default_sort = "date"
    sort_fields = {k: k for k in CASH_BOOK_COLUMNS.keys}
    filter_specs = (("account", "Cash Account", sel.cash_account_options),)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.cash_book(p.start, p.end, f["account"] or None)
        t = data["totals"]
        tiles = [
            _tile("Opening", format_amount(t["opening"]), "slate", "cash"),
            _tile("Receipts", format_amount(t["receipts"]), "green", "plus", f"{t['entries']} entries"),
            _tile("Payments", format_amount(t["payments"]), "rose", "minus"),
            _tile("Closing", format_amount(t["closing"]), "amber" if t["closing"] < 0 else "sky", "cash", f"{t['days']} days"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


CashBookExportView, CashBookColumnsView = _views(CashBookView)


# 51 ------------------------------------------------------------------------

BANK_BOOK_COLUMNS = ColumnSet("reports.bank_book", (
    col("date", "Date", "date", locked=True),
    col("voucher_no", "Voucher", "link", locked=True, link=VOUCHER_LINK),
    col("type", "Type"),
    col("bank", "Bank Account"),
    col("counterpart", "Counter Account"),
    col("method", "Method", default=False),
    col("cheque_no", "Cheque No"),
    col("cheque_date", "Cheque Date", "date"),
    col("reference", "Reference", default=False),
    col("remarks", "Remarks", "muted", default=False),
    col("deposit", "Deposit", "money", total=True),
    col("withdrawal", "Withdrawal", "money", total=True),
    col("balance", "Balance", "money", locked=True, tone_key="negative"),
))


class BankBookView(ReportView):
    page = PAGE
    title = "Bank Book"
    template_name = "reports/generic.html"
    columns = BANK_BOOK_COLUMNS
    url_name = "finance:report_bank_book"
    default_sort = "date"
    sort_fields = {k: k for k in BANK_BOOK_COLUMNS.keys}
    filter_specs = (("account", "Bank Account", sel.bank_account_options),)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.bank_book(p.start, p.end, f["account"] or None)
        t = data["totals"]
        tiles = [
            _tile("Opening", format_amount(t["opening"]), "slate", "ledger"),
            _tile("Deposits", format_amount(t["deposit"]), "green", "plus", f"{t['entries']} entries"),
            _tile("Withdrawals", format_amount(t["withdrawal"]), "rose", "minus"),
            _tile("Closing", format_amount(t["closing"]), "amber" if t["closing"] < 0 else "sky", "ledger"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


BankBookExportView, BankBookColumnsView = _views(BankBookView)


# 53 ------------------------------------------------------------------------

PARTY_LEDGER_COLUMNS = ColumnSet("reports.party_ledger", (
    col("date", "Date", "date", locked=True),
    col("voucher_no", "Voucher", "link", locked=True, link=VOUCHER_LINK, link_key="voucher_pk"),
    col("kind", "Type"),
    col("remarks", "Remarks", "muted"),
    col("debit", "Debit", "money", total=True),
    col("credit", "Credit", "money", total=True),
    col("balance", "Balance", "money", locked=True),
    col("sacks_in", "Sacks In", "qty", total=True, default=False),
    col("sacks_out", "Sacks Out", "qty", total=True, default=False),
    col("sacks", "Sacks Held", "qty"),
))


class PartyLedgerView(ReportView):
    page = PAGE
    title = "Party Ledger"
    template_name = "reports/generic.html"
    columns = PARTY_LEDGER_COLUMNS
    url_name = "finance:report_party_ledger"
    default_sort = "date"
    sort_fields = {k: k for k in PARTY_LEDGER_COLUMNS.keys}
    filter_specs = (("party", "Party", sel.party_options),)

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.party_ledger(p.start, p.end, f["party"])
        t = data["totals"]
        side = "Receivable" if data["party_type"] == sel.PARTY_CUSTOMER else "Payable" if data["party_type"] else "Balance"
        tiles = [
            _tile("Opening", format_amount(t["opening"]), "slate", "users", data["account"].title if data["account"] else ""),
            _tile("Debits", format_amount(t["debit"]), "green", "plus", f"{t['entries']} entries"),
            _tile("Credits", format_amount(t["credit"]), "rose", "minus"),
            _tile(side, format_amount(t["closing"]), "amber" if t["closing"] < 0 else "sky", "cash"),
        ]
        if data.get("has_sacks"):
            tiles.append(_tile("Sacks held", f"{t['sacks']:,.0f}", "violet", "layers"))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


PartyLedgerExportView, PartyLedgerColumnsView = _views(PartyLedgerView)


# 54 ------------------------------------------------------------------------

VOUCHER_REGISTER_COLUMNS = ColumnSet("reports.voucher_register", (
    col("voucher_no", "Voucher", "link", locked=True, link=VOUCHER_LINK),
    col("date", "Date", "date", locked=True),
    col("type", "Type"),
    col("source", "Source", default=False),
    col("account", "Account"),
    col("party", "Party"),
    col("cheque_no", "Cheque No", default=False),
    col("debit", "Debit", "money", total=True),
    col("credit", "Credit", "money", total=True, tone_key="unbalanced"),
    col("status", "Status", "status"),
    col("posted", "Posted", default=False),
    col("posted_by", "Posted By"),
    col("attachment", "Attachment"),
    col("remarks", "Remarks", "muted", default=False),
))


class VoucherRegisterView(ReportView):
    page = PAGE
    title = "Voucher Register"
    template_name = "reports/generic.html"
    columns = VOUCHER_REGISTER_COLUMNS
    url_name = "finance:report_voucher_register"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in VOUCHER_REGISTER_COLUMNS.keys}
    filter_specs = (
        ("voucher_type", "Type", FIN_VOUCHER_TYPE_CHOICES),
        ("status", "Status", FIN_VOUCHER_STATUS_CHOICES),
        ("account", "Account", sel.leaf_account_options),
    )

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.voucher_register(p.start, p.end, f["voucher_type"] or None, f["status"] or None, f["account"] or None)
        t = data["totals"]
        base = f"{p.query}&status={f['status']}&account={f['account']}"
        tiles = [_tile("Vouchers", str(t["vouchers"]), "slate", "file", f"Rs {format_amount(t['debit'])}", href=f"?{base}", on=not f["voucher_type"])]
        tones = {"PV": "rose", "RV": "green", "JV": "sky", "CN": "violet", "SV": "teal", "PU": "amber"}
        for code, label in FIN_VOUCHER_TYPE_CHOICES:
            figures = t["by_type"].get(code)
            if figures:
                tiles.append(_tile(label, str(figures["count"]), tones.get(code, "slate"), "file", f"Rs {format_amount(figures['amount'])}", href=f"?{base}&voucher_type={code}", on=f["voucher_type"] == code))
        tiles.append(_tile("Attachments", str(t["attachments"]), "slate", "file"))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


VoucherRegisterExportView, VoucherRegisterColumnsView = _views(VoucherRegisterView)


# 59 ------------------------------------------------------------------------

def expense_columns(months):
    fixed = [col("code", "Code", default=False), col("account", "Expense Account", locked=True), col("group", "Group")]
    months = [col(key, label, "money", locked=True, total=True) for key, label, _day in months]
    tail = [col("total", "Total", "money", locked=True, total=True), col("share", "Share %", "pct", total=True)]
    return ColumnSet("reports.expense_analysis", fixed + months + tail)


class ExpenseAnalysisView(ReportView):
    page = PAGE
    title = "Expense Analysis"
    template_name = "reports/generic.html"
    url_name = "finance:report_expense_analysis"
    default_preset = PRESET_FISCAL
    default_sort = "total"
    default_sort_dir = "desc"
    filter_specs = (("group", "Group", sel.expense_group_options),)

    @property
    def columns(self):
        if not hasattr(self, "_columns"):
            p = self.period()
            self._columns = expense_columns(sel.month_keys(p.start, p.end))
        return self._columns

    @property
    def sort_fields(self):
        return {k: k for k in self.columns.keys}

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.expense_analysis(p.start, p.end, f["group"] or None)
        t = data["totals"]
        top_name, top_amount = t["top"]
        tiles = [
            _tile("Total expenses", format_amount(t["total"]), "rose", "cash", f"{t['accounts']} accounts"),
            _tile("Monthly average", format_amount(t["avg_month"]), "sky", "calendar"),
            _tile("Largest head", format_amount(top_amount), "amber", "alert", top_name),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


class ExpenseAnalysisExportView(ReportExportView):
    page = PAGE
    report_view = ExpenseAnalysisView

    @property
    def columns(self):
        return self.screen().columns


class ExpenseAnalysisColumnsView(ReportColumnsView):
    page = PAGE
    report_view = ExpenseAnalysisView

    def post(self, request, *args, **kwargs):
        self.report_view(request=request, kwargs={}, args=()).columns.choose(request.session, request.POST.getlist("columns"))
        back = request.POST.get("back", "")
        target = reverse(self.report_view.url_name)
        return redirect(f"{target}?{back}" if back else target)


# 60 ------------------------------------------------------------------------

RECEIVABLE_PAYABLE_COLUMNS = ColumnSet("reports.receivable_payable", (
    col("code", "Code", default=False),
    col("party", "Party", locked=True),
    col("type", "Type"),
    col("opening", "Opening", "money", total=True, default=False),
    col("debit", "Debit", "money", total=True),
    col("credit", "Credit", "money", total=True),
    col("receivable", "Receivable", "money", total=True),
    col("payable", "Payable", "money", total=True),
    col("balance", "Balance", "money", locked=True, tone_key="negative"),
    col("last_activity", "Last Activity", "date"),
    col("idle_days", "Idle Days", "int"),
    col("entries", "Entries", "int", default=False),
))


class ReceivablePayableView(ReportView):
    page = PAGE
    title = "Receivable / Payable Summary"
    template_name = "reports/generic.html"
    columns = RECEIVABLE_PAYABLE_COLUMNS
    url_name = "finance:report_receivable_payable"
    as_of_report = True
    default_sort = "balance"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in RECEIVABLE_PAYABLE_COLUMNS.keys}
    filter_specs = (("party_type", "Type", sel.PARTY_TYPE_CHOICES),)

    def build(self):
        f = self.filters()
        data = sel.receivable_payable(self.as_of(), f["party_type"] or None)
        t = data["totals"]
        base = f"as_of={self.as_of():%Y-%m-%d}"
        tiles = [
            _tile("Receivable", format_amount(t["receivable"]), "green", "users", f"{t['customers']} customers", href=f"?{base}&party_type=customer", on=f["party_type"] == "customer"),
            _tile("Payable", format_amount(t["payable"]), "rose", "box", f"{t['suppliers']} suppliers", href=f"?{base}&party_type=supplier", on=f["party_type"] == "supplier"),
            _tile("Net position", format_amount(t["net"]), "amber" if t["net"] < 0 else "sky", "cash", href=f"?{base}", on=not f["party_type"]),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


ReceivablePayableExportView, ReceivablePayableColumnsView = _views(ReceivablePayableView)


# 61 ------------------------------------------------------------------------

OPENING_COLUMNS = ColumnSet("reports.opening_balances", (
    col("code", "Code"),
    col("account", "Account", locked=True),
    col("group", "Group"),
    col("type", "Type"),
    col("manual", "Master Opening", "money", total=True, default=False),
    col("carried", "Brought Forward", "money", total=True, default=False),
    col("debit", "Debit", "money", total=True, locked=True),
    col("credit", "Credit", "money", total=True, locked=True),
    col("source", "Source"),
))


class OpeningBalancesView(ReportView):
    page = PAGE
    title = "Opening Balances"
    template_name = "reports/generic.html"
    columns = OPENING_COLUMNS
    url_name = "finance:report_opening_balances"
    as_of_report = True
    default_sort = "code"
    sort_fields = {k: k for k in OPENING_COLUMNS.keys}
    filter_specs = (("fiscal_year", "Fiscal Year", sel.fiscal_year_options), ("account_type", "Type", FIN_COA_ACCOUNT_TYPE_CHOICES))

    def as_of(self):
        if not hasattr(self, "_as_of"):
            raw = resolve_as_of(self.request)
            fiscal = sel.fiscal_year_for(self.filters()["fiscal_year"] or None, raw)
            self._as_of = fiscal.start_date if fiscal else preset_bounds(PRESET_FISCAL, raw)[0]
        return self._as_of

    def build(self):
        f = self.filters()
        data = sel.opening_balances(self.as_of(), f["account_type"] or None)
        t = data["totals"]
        tiles = [
            _tile("Debits", format_amount(t["debit"]), "green", "plus", f"{t['accounts']} accounts"),
            _tile("Credits", format_amount(t["credit"]), "rose", "minus"),
            _tile("Difference", format_amount(t["difference"]), "amber" if t["difference"] else "sky", "alert"),
            _tile("Carried", str(t["carried_count"]), "violet", "reverse", t["closed"].voucher_no if t["closed"] else "no period close"),
            _tile("Manual", str(t["manual_count"]), "slate", "edit"),
        ]
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


OpeningBalancesExportView, OpeningBalancesColumnsView = _views(OpeningBalancesView)


# 63 ------------------------------------------------------------------------

AUDIT_COLUMNS = ColumnSet("reports.audit_trail", (
    col("date", "Date", "date", locked=True),
    col("time", "Time", "time"),
    col("kind", "Event", locked=True),
    col("number", "Document", "link", link=VOUCHER_LINK, link_key="voucher_pk"),
    col("party", "Account / Party"),
    col("amount", "Amount", "money", total=True),
    col("reason", "Reason", "muted"),
    col("user", "User"),
    col("status", "Status", "status"),
))


class AuditTrailView(ReportView):
    page = PAGE
    title = "Audit Trail"
    template_name = "reports/generic.html"
    columns = AUDIT_COLUMNS
    url_name = "finance:report_audit_trail"
    default_sort = "date"
    default_sort_dir = "desc"
    sort_fields = {k: k for k in AUDIT_COLUMNS.keys}
    filter_specs = (("kind", "Event", sel.AUDIT_KIND_CHOICES), ("user", "User", sel.voucher_user_options))

    def build(self):
        p, f = self.period(), self.filters()
        data = sel.audit_trail(p.start, p.end, f["kind"] or None, f["user"] or None)
        t = data["totals"]
        base = f"{p.query}&user={f['user']}"
        tiles = [_tile("Events", str(t["entries"]), "slate", "clock", href=f"?{base}", on=not f["kind"])]
        tones = {sel.KIND_GL_REVERSAL: "rose", sel.KIND_INVOICE_REVERSAL: "amber", sel.KIND_RETURN_REVERSAL: "violet", sel.KIND_VOUCHER_EDIT: "sky", sel.KIND_MANUAL_VOUCHER: "teal"}
        for code, label in sel.AUDIT_KIND_CHOICES:
            tiles.append(_tile(label, str(t[code]), tones[code], "edit", href=f"?{base}&kind={code}", on=f["kind"] == code))
        tiles.append(_tile("Reversed value", format_amount(t["reversed_amount"]), "rose", "reverse"))
        return {"rows": data["rows"], "totals": t, "tiles": tiles}


AuditTrailExportView, AuditTrailColumnsView = _views(AuditTrailView)
