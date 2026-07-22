import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from apps.core.constants import FIN_ACCOUNT_LEDGER_CHOICES, FIN_ACCOUNT_TYPE_CHOICES, FIN_COA_ACCOUNT_TYPE_CHOICES, FIN_VOUCHER_STATUS_CHOICES, FIN_VOUCHER_TYPE_CHOICES, FIN_VOUCHER_TYPE_META, RECORD_STATUS_CHOICES, STATUS_ACTIVE, YES_NO_CHOICES
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, SearchFilterPaginationMixin

from apps.core.constants import STATUS_INACTIVE

from .forms import AccountConfigurationForm, AccountVoucherForm, AccountVoucherLineForm, FiscalYearForm
from .models import AccountConfiguration, AccountVoucher, AccountVoucherLine, ChartOfAccount, FiscalPeriod, FiscalYear


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
        context["voucher_accounts"] = ChartOfAccount.objects.filter(status=STATUS_ACTIVE, children__isnull=True).order_by("code")
        return context

    def _parse_line_rows(self):
        """Read the entry-grid arrays; skip fully empty rows."""
        accounts = self.request.POST.getlist("line_account[]")
        descriptions = self.request.POST.getlist("line_description[]")
        debits = self.request.POST.getlist("line_debit[]")
        credits = self.request.POST.getlist("line_credit[]")
        rows = []
        for index in range(max(len(accounts), len(debits), len(credits), len(descriptions))):
            account_no = (accounts[index] if index < len(accounts) else "").strip()
            description = (descriptions[index] if index < len(descriptions) else "").strip()
            try:
                debit = Decimal((debits[index] if index < len(debits) else "") or "0")
                credit = Decimal((credits[index] if index < len(credits) else "") or "0")
            except InvalidOperation:
                debit = credit = Decimal("0")
            if not account_no and not description and debit == 0 and credit == 0:
                continue
            rows.append({"account_no": account_no, "remarks": description, "debit_amount": debit, "credit_amount": credit})
        return rows

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
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
