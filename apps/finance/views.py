from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.core.constants import FIN_ACCOUNT_LEDGER_CHOICES, FIN_ACCOUNT_TYPE_CHOICES, FIN_VOUCHER_STATUS_CHOICES, FIN_VOUCHER_TYPE_CHOICES, RECORD_STATUS_CHOICES, YES_NO_CHOICES
from apps.core.mixins import PortalPermissionRequiredMixin, SearchFilterPaginationMixin

from .forms import AccountConfigurationForm, AccountVoucherForm, AccountVoucherLineForm, FiscalYearForm
from .models import AccountConfiguration, AccountVoucher, AccountVoucherLine, FiscalYear


class AuditSaveMixin:
    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


class FiscalYearListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "finance.view"
    template_name = "finance/fiscal_year_list.html"
    context_object_name = "fiscal_years"
    queryset = FiscalYear.objects.order_by("-start_date")
    search_fields = ("title", "code")
    filter_fields = {"status": "status"}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class FiscalYearCreateView(AuditSaveMixin, PortalPermissionRequiredMixin, CreateView):
    permission_required = "finance.manage"
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


class AccountConfigurationListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "finance.view"
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


class AccountConfigurationCreateView(AuditSaveMixin, PortalPermissionRequiredMixin, CreateView):
    permission_required = "finance.manage"
    model = AccountConfiguration
    form_class = AccountConfigurationForm
    template_name = "finance/account_configuration_form.html"
    success_url = reverse_lazy("finance:account_configuration_list")
    success_message = "Account saved."


class AccountConfigurationUpdateView(AccountConfigurationCreateView, UpdateView):
    success_message = "Account updated."


class AccountVoucherListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "finance.view"
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


class AccountVoucherCreateView(AuditSaveMixin, PortalPermissionRequiredMixin, CreateView):
    permission_required = "finance.manage"
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


class AccountVoucherDetailView(PortalPermissionRequiredMixin, DetailView):
    permission_required = "finance.view"
    model = AccountVoucher
    template_name = "finance/account_voucher_detail.html"
    context_object_name = "voucher"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["line_form"] = AccountVoucherLineForm()
        context["balance_difference"] = self.object.balance_difference
        return context


class AccountVoucherLineCreateView(PortalPermissionRequiredMixin, View):
    permission_required = "finance.manage"

    @transaction.atomic
    def post(self, request, voucher_pk):
        voucher = get_object_or_404(AccountVoucher, pk=voucher_pk)
        if voucher.posted == "Y":
            messages.error(request, "Posted voucher cannot be updated.")
            return redirect("finance:account_voucher_detail", pk=voucher.pk)
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


class AccountVoucherLineDeleteView(PortalPermissionRequiredMixin, View):
    permission_required = "finance.manage"

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
