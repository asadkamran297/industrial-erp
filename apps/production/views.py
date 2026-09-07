import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, View

from apps.core.mixins import PagePermissionRequiredMixin, PrintContextMixin, SearchFilterPaginationMixin
from apps.godowns.selectors import active_godowns, default_godown

from . import selectors, services
from .forms import GrindingVoucherForm, ProductConversionForm, parse_output_lines
from .models import GrindingVoucher, ProductConversion

GRINDING_PAGE = "production.grinding"
CONVERSION_PAGE = "production.conversions"
REPORT_PAGE = "production.reports"


def _crumbs(*trail):
    return [
        ("Dashboard", reverse("portal:dashboard")),
        ("Grinding", reverse("production:grinding_list")),
        *trail,
    ]


def _messages(error) -> list[str]:
    """Flatten whatever the save raised into lines the screen can print."""
    if isinstance(error, ValidationError):
        return list(error.messages)
    return [str(error)]


def _parse_date(raw):
    return raw.strip() or None if isinstance(raw, str) else raw


# ---------------------------------------------------------------------------
# Grinding
# ---------------------------------------------------------------------------
class GrindingListView(PagePermissionRequiredMixin, SearchFilterPaginationMixin, ListView):
    page = GRINDING_PAGE
    model = GrindingVoucher
    template_name = "production/grinding_list.html"
    context_object_name = "rows"
    paginate_by = 50
    search_fields = ("voucher_no", "issue_area", "wheat_item__name")
    filter_fields = {"wheat_item": "wheat_item_id", "godown": "godown_id", "voucher_no": "voucher_no"}
    date_filters = [{"field": "date", "label": "Voucher date"}]

    def get_queryset(self):
        self.queryset = selectors.grinding_with_bags()
        return super().get_queryset()

    def get_filter_specs(self):
        return [
            {"name": "wheat_item", "label": "All wheat items",
             "choices": [(str(item.pk), item.name) for item in selectors.wheat_options()],
             "value": self.request.GET.get("wheat_item", "")},
            {"name": "godown", "label": "All godowns",
             "choices": [(str(godown.pk), godown.name) for godown in active_godowns()],
             "value": self.request.GET.get("godown", "")},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Grinding"
        context["create_url"] = reverse("production:grinding_create")
        context["breadcrumbs"] = _crumbs()
        context["totals"] = selectors.grinding_totals(self.get_queryset())
        return context


class GrindingFormView(PagePermissionRequiredMixin, View):
    """Add and edit are one screen: the same grid, the same totals, the same
    save. Splitting them would mean keeping two copies of the yield footer."""

    page = GRINDING_PAGE
    action = "add"
    template_name = "production/grinding_form.html"

    def get_object(self, pk):
        return selectors.grinding_detail(pk) if pk else None

    def context(self, request, form, voucher, lines=None, errors=None):
        on_date = (voucher.date if voucher else None) or _parse_date(request.POST.get("date") or request.GET.get("date"))
        return {
            "title": f"Edit {voucher.voucher_no}" if voucher else "Add Grinding",
            "form": form,
            "voucher": voucher,
            "voucher_no": voucher.voucher_no if voucher else services.next_grinding_number(),
            "breadcrumbs": _crumbs(("Edit" if voucher else "Add", "")),
            "line_rows": lines if lines is not None else _stored_lines(voucher),
            "line_errors": errors or [],
            "product_options": json.dumps(selectors.product_payload(on_date), default=str),
            "wheat_options": json.dumps(selectors.wheat_payload(on_date), default=str),
            "pack_options": [{"id": item.pk, "name": str(item)} for item in selectors.pack_options()],
            "pack_stock": json.dumps(selectors.pack_stock_payload(on_date), default=str),
            "default_godown": default_godown(),
            "cancel_url": reverse("production:grinding_list"),
        }

    def get(self, request, pk=None):
        voucher = self.get_object(pk)
        form = GrindingVoucherForm(instance=voucher)
        if voucher is None:
            form.initial.setdefault("date", services.today())
            godown = default_godown()
            if godown:
                form.initial.setdefault("godown", godown.pk)
        return render(request, self.template_name, self.context(request, form, voucher))

    def post(self, request, pk=None):
        voucher = self.get_object(pk)
        form = GrindingVoucherForm(request.POST, instance=voucher)
        lines, errors = parse_output_lines(request.POST)

        if form.is_valid() and not errors:
            instance = form.save(commit=False)
            if voucher is None:
                instance.prepared_by = request.user
            try:
                services.save_grinding_voucher(instance, lines, request.user)
            except (ValueError, ValidationError) as error:
                errors.extend(_messages(error))
            else:
                messages.success(request, f"{instance.voucher_no} saved.")
                return redirect(reverse("production:grinding_detail", args=[instance.pk]))

        posted = [
            {
                "product_id": line["product"].pk,
                "product": line["product"],
                "quantity": line["quantity"],
                "unit_weight": line["unit_weight"],
                "pack_product_id": line["pack_product"].pk if line["pack_product"] else "",
                "pack_qty": line["pack_qty"],
            }
            for line in lines
        ]
        return render(request, self.template_name, self.context(request, form, voucher, posted, errors))


class GrindingUpdateView(GrindingFormView):
    action = "edit"


def _stored_lines(voucher):
    if voucher is None:
        return []
    return [
        {
            "product_id": line.product_id,
            "product": line.product,
            "quantity": line.quantity,
            "unit_weight": line.unit_weight,
            "pack_product_id": line.pack_product_id or "",
            "pack_qty": line.pack_qty,
        }
        for line in voucher.outputs.all()
    ]


class GrindingDetailView(PagePermissionRequiredMixin, View):
    page = GRINDING_PAGE
    action = "view"
    template_name = "production/grinding_detail.html"

    def get(self, request, pk):
        voucher = selectors.grinding_detail(pk)
        if voucher is None:
            messages.error(request, "That grinding voucher no longer exists.")
            return redirect("production:grinding_list")
        return render(request, self.template_name, {
            "voucher": voucher,
            "title": voucher.voucher_no,
            "breadcrumbs": _crumbs((voucher.voucher_no, "")),
        })


class GrindingPrintView(PagePermissionRequiredMixin, PrintContextMixin, View):
    page = GRINDING_PAGE
    action = "view"
    template_name = "production/grinding_print.html"

    def get(self, request, pk):
        voucher = get_object_or_404(GrindingVoucher, pk=pk)
        context = {"voucher": selectors.grinding_detail(pk), "title": voucher.voucher_no}
        context.update(self.get_print_context(request))
        return render(request, self.template_name, context)


class GrindingDeleteView(PagePermissionRequiredMixin, View):
    page = GRINDING_PAGE
    action = "delete"

    def post(self, request, pk):
        voucher = get_object_or_404(GrindingVoucher, pk=pk)
        services.delete_grinding_voucher(voucher, request.user)
        messages.success(request, f"{voucher.voucher_no} reversed and removed.")
        return redirect("production:grinding_list")


class GrindingOptionsView(PagePermissionRequiredMixin, View):
    """Stock as at the voucher's date, for a back-dated entry.

    The screen re-asks whenever the date changes, because a voucher written for
    last Tuesday must show last Tuesday's stock, not today's.
    """

    page = GRINDING_PAGE
    action = "add"

    def get(self, request):
        on_date = _parse_date(request.GET.get("date"))
        godown = request.GET.get("godown") or None
        return JsonResponse({
            "wheat": selectors.wheat_payload(on_date, godown),
            "products": selectors.product_payload(on_date, godown),
            "pack_stock": selectors.pack_stock_payload(on_date, godown),
        })


# ---------------------------------------------------------------------------
# Product conversion
# ---------------------------------------------------------------------------
class ConversionListView(PagePermissionRequiredMixin, SearchFilterPaginationMixin, ListView):
    page = CONVERSION_PAGE
    model = ProductConversion
    template_name = "production/conversion_list.html"
    context_object_name = "rows"
    paginate_by = 50
    search_fields = ("voucher_no", "source_product__name")
    filter_fields = {"godown": "godown_id"}
    date_filters = [{"field": "date", "label": "Voucher date"}]

    def get_queryset(self):
        self.queryset = selectors.conversions()
        return super().get_queryset()

    def get_filter_specs(self):
        return [
            {"name": "godown", "label": "All godowns",
             "choices": [(str(godown.pk), godown.name) for godown in active_godowns()],
             "value": self.request.GET.get("godown", "")},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Products Conversion"
        context["create_url"] = reverse("production:conversion_create")
        context["breadcrumbs"] = _crumbs(("Products Conversion", ""))
        return context


class ConversionFormView(PagePermissionRequiredMixin, View):
    page = CONVERSION_PAGE
    action = "add"
    template_name = "production/conversion_form.html"

    def get_object(self, pk):
        return selectors.conversion_detail(pk) if pk else None

    def context(self, request, form, conversion, lines=None, errors=None):
        on_date = (conversion.date if conversion else None) or _parse_date(request.POST.get("date"))
        return {
            "title": f"Edit {conversion.voucher_no}" if conversion else "Add Conversion",
            "form": form,
            "conversion": conversion,
            "voucher_no": conversion.voucher_no if conversion else services.next_conversion_number(),
            "breadcrumbs": _crumbs(("Products Conversion", reverse("production:conversion_list")),
                                   ("Edit" if conversion else "Add", "")),
            "line_rows": lines if lines is not None else _stored_conversion_lines(conversion),
            "line_errors": errors or [],
            "product_options": json.dumps(selectors.product_payload(on_date), default=str),
            "pack_options": [{"id": item.pk, "name": str(item)} for item in selectors.pack_options()],
            "cancel_url": reverse("production:conversion_list"),
        }

    def get(self, request, pk=None):
        conversion = self.get_object(pk)
        form = ProductConversionForm(instance=conversion)
        if conversion is None:
            form.initial.setdefault("date", services.today())
            godown = default_godown()
            if godown:
                form.initial.setdefault("godown", godown.pk)
        return render(request, self.template_name, self.context(request, form, conversion))

    def post(self, request, pk=None):
        conversion = self.get_object(pk)
        form = ProductConversionForm(request.POST, instance=conversion)
        lines, errors = parse_output_lines(request.POST)

        if form.is_valid() and not errors:
            instance = form.save(commit=False)
            instance.source_unit_weight = instance.source_product.effective_unit_weight
            if conversion is None:
                instance.prepared_by = request.user
            try:
                services.save_conversion(instance, lines, request.user)
            except (ValueError, ValidationError) as error:
                errors.extend(_messages(error))
            else:
                messages.success(request, f"{instance.voucher_no} saved.")
                return redirect(reverse("production:conversion_detail", args=[instance.pk]))

        posted = [
            {
                "product_id": line["product"].pk,
                "product": line["product"],
                "quantity": line["quantity"],
                "unit_weight": line["unit_weight"],
                "pack_product_id": line["pack_product"].pk if line["pack_product"] else "",
                "pack_qty": line["pack_qty"],
            }
            for line in lines
        ]
        return render(request, self.template_name, self.context(request, form, conversion, posted, errors))


class ConversionUpdateView(ConversionFormView):
    action = "edit"


def _stored_conversion_lines(conversion):
    if conversion is None:
        return []
    return [
        {
            "product_id": line.product_id,
            "product": line.product,
            "quantity": line.quantity,
            "unit_weight": line.unit_weight,
            "pack_product_id": line.pack_product_id or "",
            "pack_qty": line.pack_qty,
        }
        for line in conversion.outputs.all()
    ]


class ConversionDetailView(PagePermissionRequiredMixin, View):
    page = CONVERSION_PAGE
    action = "view"

    def get(self, request, pk):
        conversion = selectors.conversion_detail(pk)
        if conversion is None:
            messages.error(request, "That conversion no longer exists.")
            return redirect("production:conversion_list")
        return render(request, "production/conversion_detail.html", {
            "conversion": conversion,
            "title": conversion.voucher_no,
            "breadcrumbs": _crumbs(("Products Conversion", reverse("production:conversion_list")),
                                   (conversion.voucher_no, "")),
        })


class ConversionDeleteView(PagePermissionRequiredMixin, View):
    page = CONVERSION_PAGE
    action = "delete"

    def post(self, request, pk):
        conversion = get_object_or_404(ProductConversion, pk=pk)
        services.delete_conversion(conversion, request.user)
        messages.success(request, f"{conversion.voucher_no} reversed and removed.")
        return redirect("production:conversion_list")


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
class ReportBase(PagePermissionRequiredMixin, View):
    page = REPORT_PAGE
    action = "index"

    def filters(self, request):
        return {
            "date_from": _parse_date(request.GET.get("date_from", "")),
            "date_to": _parse_date(request.GET.get("date_to", "")),
            "wheat_item": request.GET.get("wheat_item", "").strip() or None,
            "godown": request.GET.get("godown", "").strip() or None,
        }

    def base_context(self, request):
        applied = self.filters(request)
        return {
            "filters": applied,
            "wheat_options": selectors.wheat_options(),
            "godown_options": active_godowns(),
            "breadcrumbs": _crumbs(("Reports", "")),
        }


class DailyGrindingReportView(ReportBase):
    def get(self, request):
        applied = self.filters(request)
        rows = selectors.daily_grinding(**applied)
        context = self.base_context(request)
        context.update({
            "title": "Daily Grinding",
            "rows": rows,
            "totals": selectors.grinding_totals(rows),
        })
        return render(request, "production/report_daily_grinding.html", context)


class YieldTrendReportView(ReportBase):
    def get(self, request):
        applied = self.filters(request)
        context = self.base_context(request)
        context.update({
            "title": "Yield Trend",
            "daily": selectors.yield_by_day(applied["date_from"], applied["date_to"]),
            "monthly": selectors.yield_by_month(applied["date_from"], applied["date_to"]),
            "average": selectors.period_average_yield(applied["date_from"], applied["date_to"]),
        })
        return render(request, "production/report_yield_trend.html", context)


class ProductionSummaryReportView(ReportBase):
    def get(self, request):
        applied = self.filters(request)
        rows = selectors.production_summary(applied["date_from"], applied["date_to"], applied["godown"])
        context = self.base_context(request)
        context.update({
            "title": "Production Summary",
            "rows": rows,
            "categories": selectors.summary_by_category(rows),
        })
        return render(request, "production/report_production_summary.html", context)
