import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from apps.core.constants import FIN_ACCOUNT_LEDGER_CHOICES, FIN_ACCOUNT_TYPE_CHOICES, FIN_COA_ACCOUNT_TYPE_CHOICES, FIN_ACCOUNT_ROLE_LABELS, FIN_PAYMENT_CONDITIONAL_FIELDS, FIN_PAYMENT_METHOD_FIELDS, FIN_SETTLEMENT_HEADER_ROLES, FIN_VOUCHER_HEADER_ROLES, FIN_VOUCHER_LABELS, FIN_VOUCHER_LINE_ROLES, FIN_VOUCHER_PARTY_ROLES, FIN_VOUCHER_STATUS_CHOICES, FIN_VOUCHER_TYPE_CHOICES, FIN_VOUCHER_TYPE_META, RECORD_STATUS_CHOICES, STATUS_ACTIVE, VOUCHER_SETTLEMENT_TYPES, VOUCHER_SIMPLE_SIDES, YES_NO_CHOICES
from apps.configurations.models import PaymentMethod
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, SearchFilterPaginationMixin

from apps.core.constants import STATUS_INACTIVE

from .forms import AccountConfigurationForm, AccountVoucherForm, AccountVoucherLineForm, FiscalYearForm
from .models import AccountConfiguration, AccountVoucher, AccountVoucherLine, ChartOfAccount, FiscalPeriod, FiscalYear
from .services import account_balances, account_role, balance_sheet, cash_bank_account_codes, cash_flow_statement, close_period_to_retained_earnings, dr_cr_to_signed, income_statement, money_account_codes, receivable_account_codes, signed_to_dr_cr, sync_customer_from_coa


class AuditSaveMixin:
    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


class FiscalYearListView(SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "finance.fiscal_years"
    template_name = "finance/fiscal_year_list.html"
    context_object_name = "fiscal_years"
    queryset = (
        FiscalYear.objects.prefetch_related("periods")
        .annotate(
            month_period_count=Count(
                "periods",
                filter=~Q(periods__code__endswith="-00") & ~Q(periods__code__endswith="-99"),
            )
        )
        .order_by("-start_date")
    )
    search_fields = ("title", "code")
    filter_fields = {"status": "status"}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class FiscalYearCreateView(AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
    page = "finance.fiscal_years"
    model = FiscalYear
    form_class = FiscalYearForm
    template_name = "finance/fiscal_year_form.html"
    success_url = reverse_lazy("finance:fiscal_year_list")
    success_message = "Fiscal year saved."

    def form_valid(self, form):
        response = super().form_valid(form)
        self.object.generate_periods()
        return response


class FiscalYearUpdateView(FiscalYearCreateView, UpdateView):
    success_message = "Fiscal year updated."


class FiscalYearToggleActiveView(PagePermissionRequiredMixin, View):
    page = "finance.fiscal_years"
    action = "edit"

    def post(self, request, pk):
        fiscal_year = get_object_or_404(FiscalYear, pk=pk)
        fiscal_year.status = STATUS_INACTIVE if fiscal_year.status == STATUS_ACTIVE else STATUS_ACTIVE
        fiscal_year.updated_by = request.user
        fiscal_year.save(update_fields=["status", "updated_by", "updated_at"])
        messages.success(request, f"{fiscal_year.title} set to {fiscal_year.get_status_display()}.")
        return redirect("finance:fiscal_year_list")


class FiscalPeriodSetActiveView(PagePermissionRequiredMixin, View):
    page = "finance.fiscal_years"
    action = "edit"

    def post(self, request, pk):
        fiscal_year = get_object_or_404(FiscalYear, pk=pk)
        period = get_object_or_404(FiscalPeriod, pk=request.POST.get("period"), fiscal_year=fiscal_year)
        with transaction.atomic():
            fiscal_year.periods.filter(status=STATUS_ACTIVE).exclude(pk=period.pk).update(
                status=STATUS_INACTIVE, updated_by=request.user, updated_at=timezone.now()
            )
            period.status = STATUS_ACTIVE
            period.updated_by = request.user
            period.save(update_fields=["status", "updated_by", "updated_at"])
        messages.success(request, f"{period.title} set active.")
        return redirect("finance:fiscal_year_list")


class AccountConfigurationListView(SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "finance.accounts"
    template_name = "finance/account_configuration_list.html"
    context_object_name = "accounts"
    queryset = AccountConfiguration.objects.select_related("post_to_account").order_by("account_no")
    search_fields = ("title", "code", "account_no")
    filter_fields = {"status": "status", "account_ledger": "account_ledger", "account_type": "account_type"}

    def get_filter_specs(self):
        return [
            {"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")},
            {"name": "account_ledger", "label": "All ledgers", "choices": FIN_ACCOUNT_LEDGER_CHOICES, "value": self.request.GET.get("account_ledger", "")},
            {"name": "account_type", "label": "All account types", "choices": FIN_ACCOUNT_TYPE_CHOICES, "value": self.request.GET.get("account_type", "")},
        ]


class AccountConfigurationCreateView(AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
    page = "finance.accounts"
    model = AccountConfiguration
    form_class = AccountConfigurationForm
    template_name = "finance/account_configuration_form.html"
    success_url = reverse_lazy("finance:account_configuration_list")
    success_message = "Account saved."


class AccountConfigurationUpdateView(AccountConfigurationCreateView, UpdateView):
    success_message = "Account updated."


class AccountVoucherListView(SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "finance.vouchers"
    template_name = "finance/account_voucher_list.html"
    context_object_name = "vouchers"
    queryset = AccountVoucher.objects.select_related("payment_method").order_by("-voucher_date", "-id")
    search_fields = ("voucher_no", "account_no", "remarks")
    filter_fields = {"status": "status", "voucher_type": "voucher_type", "posted": "posted"}

    def get_filter_specs(self):
        return [
            {"name": "status", "label": "All statuses", "choices": FIN_VOUCHER_STATUS_CHOICES, "value": self.request.GET.get("status", "")},
            {"name": "voucher_type", "label": "All voucher types", "choices": FIN_VOUCHER_TYPE_CHOICES, "value": self.request.GET.get("voucher_type", "")},
            {"name": "posted", "label": "Posted?", "choices": YES_NO_CHOICES, "value": self.request.GET.get("posted", "")},
        ]


class AccountVoucherCreateView(AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
    page = "finance.vouchers"
    model = AccountVoucher
    form_class = AccountVoucherForm
    template_name = "finance/account_voucher_form.html"
    success_url = reverse_lazy("finance:account_voucher_list")
    success_message = "Voucher saved."

    def _selected_type(self):
        value = self.request.GET.get("type", "")
        if value in dict(FIN_VOUCHER_TYPE_CHOICES):
            return value
        return FIN_VOUCHER_TYPE_META[0][0]  # default to first (Contra)

    def get_initial(self):
        initial = super().get_initial()
        initial["voucher_type"] = self._selected_type()
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["voucher_type_meta"] = FIN_VOUCHER_TYPE_META
        context["selected_voucher_type"] = self._selected_type()
        # Last (childless) nodes of the chart of accounts are the postable ones.
        money_groups = money_account_codes()
        customer_codes = receivable_account_codes()
        accounts = list(ChartOfAccount.objects.filter(status=STATUS_ACTIVE, children__isnull=True).order_by("code"))
        for account in accounts:
            account.role = account_role(account, money_groups, customer_codes)
            account.group_label = FIN_ACCOUNT_ROLE_LABELS[account.role]
        context["voucher_accounts"] = accounts
        context["simple_voucher_types"] = list(VOUCHER_SIMPLE_SIDES)
        context["voucher_header_roles"] = FIN_VOUCHER_HEADER_ROLES
        context["voucher_line_roles"] = FIN_VOUCHER_LINE_ROLES
        context["settlement_header_roles"] = FIN_SETTLEMENT_HEADER_ROLES
        context["voucher_party_roles"] = FIN_VOUCHER_PARTY_ROLES
        context["voucher_labels"] = FIN_VOUCHER_LABELS
        context["settlement_voucher_types"] = list(VOUCHER_SETTLEMENT_TYPES)
        # Kept on the form but off the screen: date defaults to today and the
        # workflow fields stay at their model defaults until the detail page.
        context["hidden_header_fields"] = ["voucher_type", "voucher_date", "status", "adj_entry", "adj_voucher"]
        # {payment_method_id: [extra field names]} — drives the conditional fields.
        context["payment_method_fields"] = {
            str(pk): list(FIN_PAYMENT_METHOD_FIELDS.get((title or "").strip().lower(), ()))
            for pk, title in PaymentMethod.objects.values_list("id", "title")
        }
        context["payment_conditional_fields"] = list(FIN_PAYMENT_CONDITIONAL_FIELDS)
        return context

    @staticmethod
    def _decimal(values, index):
        try:
            return Decimal((values[index] if index < len(values) else "") or "0")
        except InvalidOperation:
            return Decimal("0")

    def _parse_line_rows(self):
        """Read the entry-grid arrays; skip fully empty rows.

        Simple-mode vouchers (Payment/Receipt) post one ``line_amount[]`` per row
        instead of a debit/credit pair; the voucher type decides the side.
        """
        sides = VOUCHER_SIMPLE_SIDES.get(self.request.POST.get("voucher_type", ""))
        accounts = self.request.POST.getlist("line_account[]")
        descriptions = self.request.POST.getlist("line_description[]")
        debits = self.request.POST.getlist("line_debit[]")
        credits = self.request.POST.getlist("line_credit[]")
        amounts = self.request.POST.getlist("line_amount[]")
        rows = []
        for index in range(max(len(accounts), len(debits), len(credits), len(amounts), len(descriptions))):
            account_no = (accounts[index] if index < len(accounts) else "").strip()
            description = (descriptions[index] if index < len(descriptions) else "").strip()
            if sides:
                amount = self._decimal(amounts, index)
                debit = amount if sides[1] == "debit" else Decimal("0")
                credit = amount if sides[1] == "credit" else Decimal("0")
            else:
                debit = self._decimal(debits, index)
                credit = self._decimal(credits, index)
            if not account_no and not description and debit == 0 and credit == 0:
                continue
            rows.append({"account_no": account_no, "remarks": description, "debit_amount": debit, "credit_amount": credit})
        return rows

    def _append_money_line(self, line_number):
        """Simple mode: the header Cash/Bank account is the contra leg, so post it for the user."""
        sides = VOUCHER_SIMPLE_SIDES.get(self.object.voucher_type)
        if not sides:
            return
        header_side = sides[0]
        self.object.recalculate_totals()
        # The reason lines all sit on one side; the money leg mirrors their total.
        amount = self.object.debit_amount if header_side == "credit" else self.object.credit_amount
        if amount <= 0:
            return
        AccountVoucherLine.objects.create(
            voucher=self.object,
            line_number=line_number,
            voucher_no=self.object.voucher_no,
            account_no=self.object.account_no,
            voucher_date=self.object.voucher_date,
            payment_method=self.object.payment_method,
            debit_amount=amount if header_side == "debit" else Decimal("0"),
            credit_amount=amount if header_side == "credit" else Decimal("0"),
            remarks=self.object.remarks,
            receipt_no=self.object.transaction_ref,
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            number = 0
            for number, row in enumerate(self._parse_line_rows(), start=1):
                line_form = AccountVoucherLineForm(row)
                if line_form.is_valid():
                    line = line_form.save(commit=False)
                    line.voucher = self.object
                    line.line_number = number
                    line.voucher_no = self.object.voucher_no
                    line.voucher_date = self.object.voucher_date
                    line.created_by = self.request.user
                    line.updated_by = self.request.user
                    line.save()
                else:
                    for errors in line_form.errors.values():
                        for error in errors:
                            messages.error(self.request, f"Line {number}: {error}")
            self._append_money_line(number + 1)
        self.object.refresh_from_db()
        if self.object.lines.exists() and not self.object.is_balanced:
            messages.warning(self.request, "Voucher totals are not balanced yet. Debit and credit must match before posting.")
        return response


class AccountVoucherUpdateView(AccountVoucherCreateView, UpdateView):
    success_message = "Voucher updated."

    def form_valid(self, form):
        # Header-only update; lines are managed on the detail page.
        return super(AccountVoucherCreateView, self).form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_voucher_type"] = self.object.voucher_type
        return context

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.posted == "Y":
            messages.error(request, "Posted voucher cannot be updated.")
            return redirect("finance:account_voucher_list")
        return super().dispatch(request, *args, **kwargs)


class AccountVoucherDetailView(PagePermissionRequiredMixin, DetailView):
    page = "finance.vouchers"
    model = AccountVoucher
    template_name = "finance/account_voucher_detail.html"
    context_object_name = "voucher"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["line_form"] = AccountVoucherLineForm()
        context["active_accounts"] = AccountConfiguration.objects.filter(status=STATUS_ACTIVE).order_by("account_no")
        context["balance_difference"] = self.object.balance_difference
        return context


class AccountVoucherLineCreateView(PagePermissionRequiredMixin, View):
    page = "finance.vouchers"
    action = "edit"

    @transaction.atomic
    def post(self, request, voucher_pk):
        voucher = get_object_or_404(AccountVoucher, pk=voucher_pk)
        if voucher.posted == "Y":
            messages.error(request, "Posted voucher cannot be updated.")
            return redirect("finance:account_voucher_detail", pk=voucher.pk)

        raw_accounts = request.POST.getlist("account_no[]") or request.POST.getlist("line_account[]") or request.POST.getlist("account_no")
        raw_remarks = request.POST.getlist("remarks[]") or request.POST.getlist("description[]") or request.POST.getlist("line_description[]") or request.POST.getlist("remarks")
        raw_debits = request.POST.getlist("debit_amount[]") or request.POST.getlist("line_debit[]") or request.POST.getlist("debit[]")
        raw_credits = request.POST.getlist("credit_amount[]") or request.POST.getlist("line_credit[]") or request.POST.getlist("credit[]")

        created_any = False
        if raw_accounts or raw_debits or raw_credits or raw_remarks:
            rows = list(zip(raw_accounts, raw_remarks, raw_debits, raw_credits))
            for account_no, remarks, debit_amount, credit_amount in rows:
                account_no = (account_no or "").strip()
                remarks = (remarks or "").strip()
                debit_amount = debit_amount or "0"
                credit_amount = credit_amount or "0"
                if not account_no and not remarks and Decimal(debit_amount or "0") == 0 and Decimal(credit_amount or "0") == 0:
                    continue

                form = AccountVoucherLineForm(
                    {
                        "account_no": account_no,
                        "remarks": remarks,
                        "debit_amount": debit_amount,
                        "credit_amount": credit_amount,
                    }
                )
                if form.is_valid():
                    line = form.save(commit=False)
                    line.voucher = voucher
                    line.line_number = (voucher.lines.order_by("-line_number").values_list("line_number", flat=True).first() or 0) + 1
                    line.voucher_no = voucher.voucher_no
                    line.voucher_date = voucher.voucher_date
                    line.created_by = request.user
                    line.updated_by = request.user
                    line.save()
                    created_any = True
                else:
                    for errors in form.errors.values():
                        for error in errors:
                            messages.error(request, error)
            if created_any:
                if voucher.is_balanced:
                    messages.success(request, "Voucher lines saved. Voucher is balanced.")
                else:
                    messages.success(request, "Voucher lines saved.")
                    messages.warning(request, "Voucher totals are not balanced yet. Debit and credit must match before submission or posting.")
        else:
            form = AccountVoucherLineForm(request.POST)
            if form.is_valid():
                line = form.save(commit=False)
                line.voucher = voucher
                line.line_number = (voucher.lines.order_by("-line_number").values_list("line_number", flat=True).first() or 0) + 1
                line.voucher_no = voucher.voucher_no
                line.voucher_date = voucher.voucher_date
                line.created_by = request.user
                line.updated_by = request.user
                line.save()
                created_any = True
                if voucher.is_balanced:
                    messages.success(request, "Voucher line saved. Voucher is balanced.")
                else:
                    messages.success(request, "Voucher line saved.")
                    messages.warning(request, "Voucher totals are not balanced yet. Debit and credit must match before submission or posting.")
            else:
                for errors in form.errors.values():
                    for error in errors:
                        messages.error(request, error)

        return redirect("finance:account_voucher_detail", pk=voucher.pk)


class AccountVoucherLineDeleteView(PagePermissionRequiredMixin, View):
    page = "finance.vouchers"
    action = "edit"

    @transaction.atomic
    def post(self, request, voucher_pk, pk):
        voucher = get_object_or_404(AccountVoucher, pk=voucher_pk)
        if voucher.posted == "Y":
            messages.error(request, "Posted voucher cannot be updated.")
            return redirect("finance:account_voucher_detail", pk=voucher.pk)
        line = get_object_or_404(AccountVoucherLine, pk=pk, voucher=voucher)
        line.soft_delete(request.user)
        messages.success(request, "Voucher line deleted.")
        return redirect("finance:account_voucher_detail", pk=voucher.pk)


# ---------------------------------------------------------------------------
# Chart of Accounts (hierarchical tree with drag-and-drop)
# ---------------------------------------------------------------------------

def _serialize_coa_node(node, children_map, depth=0):
    return {
        "id": node.id,
        "title": node.title,
        "code": node.code,
        "is_group": node.is_group,
        "is_root": depth == 0,
        "account_type": node.account_type,
        "account_type_display": node.get_account_type_display(),
        "children": [_serialize_coa_node(child, children_map, depth + 1) for child in children_map.get(node.id, [])],
    }


def _build_coa_forest():
    nodes = list(ChartOfAccount.objects.filter(status=STATUS_ACTIVE).order_by("sort_order", "id"))
    children_map: dict[int, list] = {}
    roots = []
    for node in nodes:
        if node.parent_id is None:
            roots.append(node)
        else:
            children_map.setdefault(node.parent_id, []).append(node)
    return [_serialize_coa_node(root, children_map) for root in roots]


class ChartOfAccountTreeView(PagePermissionRequiredMixin, TemplateView):
    page = "finance.chart_of_accounts"
    template_name = "finance/chart_of_accounts.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["coa_tree"] = _build_coa_forest()
        context["account_types"] = FIN_COA_ACCOUNT_TYPE_CHOICES
        return context


# ---------------------------------------------------------------------------
# Opening balances (same tree, one amount field per postable account)
# ---------------------------------------------------------------------------

def _serialize_opening_node(node, children_map, balances, depth=0):
    children = [_serialize_opening_node(child, children_map, balances, depth + 1) for child in children_map.get(node.id, [])]
    zero = Decimal("0.00")
    own = balances.get(node.code) or {"opening": zero, "movement": zero, "closing": zero}
    opening_dr, opening_cr = signed_to_dr_cr(own["opening"], node.account_type)
    movement_dr, movement_cr = signed_to_dr_cr(own["movement"], node.account_type)
    closing_dr, closing_cr = signed_to_dr_cr(own["closing"], node.account_type)
    data = {
        "id": node.id,
        "title": node.title,
        "code": node.code,
        "account_type": node.account_type,
        "is_root": depth == 0,
        "postable": not children,  # only leaves take an opening balance
        "opening": own["opening"],
        "opening_dr": opening_dr,
        "opening_cr": opening_cr,
        "movement": own["movement"],
        "movement_dr": movement_dr,
        "movement_cr": movement_cr,
        "closing": own["closing"],
        "closing_dr": closing_dr,
        "closing_cr": closing_cr,
        "children": children,
    }
    if children:  # headings roll their subtree up rather than holding a balance
        for key in ("opening", "movement", "closing"):
            data[key] = sum(child[key] for child in children)
        for key in ("opening_dr", "opening_cr", "movement_dr", "movement_cr", "closing_dr", "closing_cr"):
            data[key] = sum(child[key] for child in children)
    return data


def _build_opening_forest():
    nodes = list(ChartOfAccount.objects.filter(status=STATUS_ACTIVE).order_by("sort_order", "id"))
    balances = account_balances()
    children_map: dict[int, list] = {}
    roots = []
    for node in nodes:
        if node.parent_id is None:
            roots.append(node)
        else:
            children_map.setdefault(node.parent_id, []).append(node)
    return [_serialize_opening_node(root, children_map, balances) for root in roots]


class OpeningBalanceView(PagePermissionRequiredMixin, TemplateView):
    page = "finance.opening_balances"
    template_name = "finance/opening_balances.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tree = _build_opening_forest()
        context["opening_tree"] = tree
        # Roots are ASSETS / LIABILITIES / CAPITAL / REVENUE / EXPENSE — summing their
        # debit vs credit sides across the whole tree is the accounting-equation check:
        # total debit-natured (assets, expenses) must equal total credit-natured
        # (liabilities, capital, revenue) once opening balances are entered correctly.
        keys = ("opening_dr", "opening_cr", "movement_dr", "movement_cr", "closing_dr", "closing_cr")
        context["grand_totals"] = {key: sum((root[key] for root in tree), Decimal("0.00")) for key in keys}
        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        # Only leaves may carry an opening balance; headings roll their subtree up.
        leaves = {node.id: node for node in ChartOfAccount.objects.filter(status=STATUS_ACTIVE, children__isnull=True)}

        def parse(prefix, node_id):
            raw = (request.POST.get(f"{prefix}-{node_id}") or "").strip()
            return Decimal(raw) if raw else Decimal("0.00")

        changed, rejected = [], 0
        for node_id in leaves:
            if f"opening_dr-{node_id}" not in request.POST and f"opening_cr-{node_id}" not in request.POST:
                continue
            node = leaves[node_id]
            try:
                debit, credit = parse("opening_dr", node_id), parse("opening_cr", node_id)
            except InvalidOperation:
                rejected += 1
                continue
            amount = dr_cr_to_signed(debit, credit, node.account_type)
            if amount != node.opening_balance:
                node.opening_balance = amount
                node.updated_by = request.user
                changed.append(node)
        if changed:
            ChartOfAccount.objects.bulk_update(changed, ["opening_balance", "updated_by", "updated_at"])
        if rejected:
            messages.error(request, f"{rejected} opening balance(s) were not a number and were skipped.")
        messages.success(request, f"{len(changed)} opening balance(s) saved.")
        return redirect("finance:opening_balances")


class TrialBalanceView(PagePermissionRequiredMixin, TemplateView):
    page = "finance.trial_balance"
    template_name = "finance/trial_balance.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        balances = account_balances()
        zero = Decimal("0.00")
        rows, totals = [], {"opening_dr": zero, "opening_cr": zero, "movement_dr": zero, "movement_cr": zero, "closing_dr": zero, "closing_cr": zero}
        accounts = ChartOfAccount.objects.filter(status=STATUS_ACTIVE, children__isnull=True).order_by("code")
        for account in accounts:
            own = balances.get(account.code) or {"opening": zero, "movement": zero, "closing": zero}
            opening_dr, opening_cr = signed_to_dr_cr(own["opening"], account.account_type)
            movement_dr, movement_cr = signed_to_dr_cr(own["movement"], account.account_type)
            closing_dr, closing_cr = signed_to_dr_cr(own["closing"], account.account_type)
            if not any((opening_dr, opening_cr, movement_dr, movement_cr, closing_dr, closing_cr)):
                continue
            rows.append({
                "code": account.code, "title": account.title, "account_type": account.account_type,
                "opening_dr": opening_dr, "opening_cr": opening_cr,
                "movement_dr": movement_dr, "movement_cr": movement_cr,
                "closing_dr": closing_dr, "closing_cr": closing_cr,
            })
            for key in totals:
                totals[key] += rows[-1][key]
        context["rows"] = rows
        context["totals"] = totals
        return context


class IncomeStatementView(PagePermissionRequiredMixin, TemplateView):
    page = "finance.income_statement"
    template_name = "finance/income_statement.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(income_statement())
        return context


class BalanceSheetView(PagePermissionRequiredMixin, TemplateView):
    page = "finance.balance_sheet"
    template_name = "finance/balance_sheet.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(balance_sheet())
        return context


class CashFlowView(PagePermissionRequiredMixin, TemplateView):
    page = "finance.cash_flow"
    template_name = "finance/cash_flow.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(cash_flow_statement())
        return context


class PeriodCloseView(PagePermissionRequiredMixin, TemplateView):
    """Preview and run the closing entry that zeroes income into Capital."""

    page = "finance.period_close"
    template_name = "finance/period_close.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        statement = income_statement()
        context.update(statement)
        context["closing_date"] = timezone.localdate()
        context["closings"] = AccountVoucher.objects.filter(
            source_ref__startswith="period_close:"
        ).order_by("-voucher_date")[:10]
        context["has_balances"] = bool(statement["revenue"] or statement["expense"])
        return context

    def post(self, request, *args, **kwargs):
        raw = (request.POST.get("closing_date") or "").strip()
        closing_date = parse_date(raw) or timezone.localdate()
        try:
            voucher = close_period_to_retained_earnings(closing_date=closing_date, user=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("finance:period_close")
        if voucher is None:
            messages.info(request, "Nothing to close — no revenue or expense balances.")
        elif voucher.voucher_date != closing_date:
            messages.warning(request, f"This period was already closed by voucher {voucher.voucher_no}.")
        else:
            messages.success(request, f"Period closed. Closing entry {voucher.voucher_no} posted.")
        return redirect("finance:period_close")


class ChartOfAccountCreateView(PagePermissionRequiredMixin, View):
    page = "finance.chart_of_accounts"
    action = "add"

    @transaction.atomic
    def post(self, request):
        title = (request.POST.get("title") or "").strip()
        if not title:
            return JsonResponse({"ok": False, "error": "Title is required."}, status=400)
        parent_id = request.POST.get("parent_id")
        if not parent_id:
            return JsonResponse({"ok": False, "error": "The five roots are fixed; a parent is required."}, status=400)
        parent = get_object_or_404(ChartOfAccount, pk=parent_id)
        if parent.depth >= ChartOfAccount.MAX_LEVELS:
            return JsonResponse({"ok": False, "error": f"Maximum {ChartOfAccount.MAX_LEVELS} levels reached."}, status=400)
        siblings = ChartOfAccount.objects.filter(parent=parent)
        next_order = (siblings.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0) + 1
        node = ChartOfAccount(
            parent=parent,
            title=title,
            account_type=parent.account_type,
            is_group=request.POST.get("is_group", "true") != "false",
            sort_order=next_order,
            created_by=request.user,
            updated_by=request.user,
        )
        node.save()  # code assigned by rebuild below
        ChartOfAccount.rebuild_codes()
        sync_customer_from_coa(node=node, user=request.user)
        return JsonResponse({"ok": True, "id": node.id})


class ChartOfAccountRenameView(PagePermissionRequiredMixin, View):
    page = "finance.chart_of_accounts"
    action = "edit"

    def post(self, request, pk):
        node = get_object_or_404(ChartOfAccount, pk=pk)
        title = (request.POST.get("title") or "").strip()
        if not title:
            return JsonResponse({"ok": False, "error": "Title is required."}, status=400)
        node.title = title
        # Codes are auto-generated by position; only title/is_group are editable.
        if node.parent_id is not None and "is_group" in request.POST:
            node.is_group = request.POST.get("is_group") != "false"
        node.updated_by = request.user
        node.save()
        return JsonResponse({"ok": True, "id": node.id, "title": node.title, "code": node.code, "is_group": node.is_group})


class ChartOfAccountDeleteView(PagePermissionRequiredMixin, View):
    page = "finance.chart_of_accounts"
    action = "delete"

    def post(self, request, pk):
        node = get_object_or_404(ChartOfAccount, pk=pk)
        if node.parent_id is None:
            return JsonResponse({"ok": False, "error": "Root accounts cannot be deleted."}, status=400)
        node.delete()  # cascades to descendants
        codes = ChartOfAccount.rebuild_codes()  # siblings shift up
        return JsonResponse({"ok": True, "codes": codes})


class ChartOfAccountReorderView(PagePermissionRequiredMixin, View):
    page = "finance.chart_of_accounts"
    action = "edit"

    @transaction.atomic
    def post(self, request):
        try:
            moves = json.loads(request.body.decode("utf-8")).get("moves", [])
        except (ValueError, AttributeError):
            return JsonResponse({"ok": False, "error": "Invalid payload."}, status=400)

        nodes = {n.id: n for n in ChartOfAccount.objects.all()}
        root_ids = {n.id for n in nodes.values() if n.parent_id is None}
        for move in moves:
            node = nodes.get(move.get("id"))
            if node is None:
                continue
            parent_id = move.get("parent_id")
            # The five roots are fixed: they can be reordered but never re-parented.
            node.parent_id = None if node.id in root_ids else (parent_id or None)
            node.sort_order = move.get("sort_order", node.sort_order)
            node.updated_at = timezone.now()

        # Validate no cycles against the in-memory batch, then cascade
        # account_type down from each node's resolved root.
        def walk_to_root(node):
            seen = set()
            cursor = node
            while cursor.parent_id is not None:
                if cursor.id in seen or cursor.parent_id not in nodes:
                    return None
                seen.add(cursor.id)
                cursor = nodes[cursor.parent_id]
            return cursor

        for node in nodes.values():
            if node.parent_id is None and node.id not in root_ids:
                return JsonResponse({"ok": False, "error": "Only the five fixed roots may sit at the top level."}, status=400)
            if walk_to_root(node) is None:
                return JsonResponse({"ok": False, "error": "Invalid move: would create a cycle."}, status=400)

        # Enforce the 5-level cap after the moves are applied.
        def level_of(node):
            depth, cursor = 1, node
            while cursor.parent_id is not None:
                depth += 1
                cursor = nodes[cursor.parent_id]
            return depth

        for node in nodes.values():
            if level_of(node) > ChartOfAccount.MAX_LEVELS:
                return JsonResponse({"ok": False, "error": f"Move exceeds the {ChartOfAccount.MAX_LEVELS}-level limit."}, status=400)
            node.account_type = walk_to_root(node).account_type

        ChartOfAccount.objects.bulk_update(nodes.values(), ["parent_id", "sort_order", "account_type", "updated_at"])
        codes = ChartOfAccount.rebuild_codes()
        return JsonResponse({"ok": True, "codes": codes})
