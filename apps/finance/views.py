from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.core.constants import FIN_ACCOUNT_LEDGER_CHOICES, FIN_ACCOUNT_TYPE_CHOICES, FIN_VOUCHER_STATUS_CHOICES, FIN_VOUCHER_TYPE_CHOICES, RECORD_STATUS_CHOICES, STATUS_ACTIVE, YES_NO_CHOICES
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, SearchFilterPaginationMixin

from apps.core.constants import STATUS_INACTIVE

from .forms import AccountConfigurationForm, AccountVoucherForm, AccountVoucherLineForm, FiscalYearForm
from .models import AccountConfiguration, AccountVoucher, AccountVoucherLine, FiscalPeriod, FiscalYear


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


class AccountVoucherUpdateView(AccountVoucherCreateView, UpdateView):
    success_message = "Voucher updated."

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
