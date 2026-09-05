from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.constants import (
    PRD_SPECIFICATION_CHOICES,
    PRD_STATUS_CHOICES,
)
from apps.core.mixins import PagePermissionRequiredMixin, SearchFilterPaginationMixin

from . import selectors, services
from .forms import ProductForm
from .models import (
    FinishBardanaLink,
    ProductAccountLink,
    ProductNode,
    ProductOpeningBalance,
    ProductRate,
    RawBardanaLink,
)
from apps.finance.models import ChartOfAccount


def _crumbs(*trail):
    return [("Dashboard", reverse("portal:dashboard")), ("Products", reverse("products:product_list")), *trail]


class ProductListView(PagePermissionRequiredMixin, SearchFilterPaginationMixin, ListView):
    """The tree as a list: headings in place, items indented beneath them."""

    page = "products.products"
    template_name = "products/product_list.html"
    context_object_name = "rows"
    paginate_by = 50
    search_fields = ("name", "complete_code", "quick_code")
    filter_fields = {"specification": "specification", "status": "status", "code": "complete_code__startswith"}

    def get_queryset(self):
        self.model = ProductNode
        queryset = selectors.items_with_stock()
        # The account filter reaches across the link table rather than storing
        # the account on the product, so a re-link is picked up here for free.
        account = self.request.GET.get("account", "").strip()
        if account:
            queryset = queryset.filter(account_link__purchase_account_id=account)
        self.queryset = queryset
        return super().get_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Headings are added around the page's own items, so a paged list is
        # still readable as a tree rather than as a run of orphan codes.
        context["tree_rows"] = selectors.tree_rows(context["rows"])
        context["title"] = "Products"
        context["create_url"] = reverse("products:product_create")
        context["breadcrumbs"] = _crumbs()
        context["item_count"] = selectors.items().count()
        return context

    def get_filter_specs(self):
        return [
            {
                "name": "specification",
                "label": "All item types",
                "choices": PRD_SPECIFICATION_CHOICES,
                "value": self.request.GET.get("specification", ""),
            },
            {
                "name": "status",
                "label": "All statuses",
                "choices": PRD_STATUS_CHOICES,
                "value": self.request.GET.get("status", ""),
            },
            {
                "name": "account",
                "label": "All purchase accounts",
                "choices": [
                    (str(account.pk), f"{account.code} {account.title}".strip())
                    for account in ChartOfAccount.objects.filter(product_purchase_links__isnull=False).distinct()
                ],
                "value": self.request.GET.get("account", ""),
            },
        ]


class ProductCreateView(PagePermissionRequiredMixin, CreateView):
    page = "products.products"
    model = ProductNode
    form_class = ProductForm
    template_name = "products/product_form.html"
    success_url = reverse_lazy("products:product_list")

    def form_valid(self, form):
        self.object = services.save_product(form.instance, self.request.user)
        messages.success(self.request, f"{self.object.display_code} {self.object.name} saved.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Add Product"
        context["breadcrumbs"] = _crumbs(("Add", ""))
        context["sub_groups"] = selectors.sub_groups()
        return context


class ProductUpdateView(ProductCreateView, UpdateView):
    def get_queryset(self):
        return ProductNode.objects.filter(level=3)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit {self.object.name}"
        context["breadcrumbs"] = _crumbs((self.object.name, ""))
        return context


class ProductStatusToggleView(PagePermissionRequiredMixin, View):
    """Deactivate, never delete. A closed product refuses to come back."""

    page = "products.products"
    action = "edit"

    def post(self, request, pk):
        product = get_object_or_404(ProductNode, pk=pk)
        try:
            services.toggle_status(product, request.user)
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"{product.name} is now {product.get_status_display().lower()}.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("products:product_list"))


class CodePreviewView(PagePermissionRequiredMixin, View):
    """Live code for the form: the picked parent plus the next free segment."""

    page = "products.products"
    action = "add"

    def get(self, request):
        parent = ProductNode.objects.filter(pk=request.GET.get("parent") or 0).first()
        if parent is None:
            return HttpResponse("--")
        return HttpResponse(f"{parent.complete_code}-{selectors.next_code_segment(parent, 3)}")


class LinkGridView(PagePermissionRequiredMixin, View):
    """One screen shape for the three linking grids.

    All three are the same job -- a list of products, one dropdown each, saved
    in a single post -- so they are one view with three configurations rather
    than three near-identical views that would drift apart.
    """

    template_name = "products/link_grid.html"
    row_source = staticmethod(lambda: ProductNode.objects.none())
    option_source = staticmethod(lambda: ProductNode.objects.none())
    link_model = None
    link_field = "product"
    target_field = "purchase_account"
    save_link = None
    title = ""
    column_label = ""
    empty_note = ""

    def get_rows(self):
        return list(self.row_source())

    def get_links(self):
        return {
            getattr(link, f"{self.link_field}_id"): getattr(link, f"{self.target_field}_id")
            for link in self.link_model.objects.all()
        }

    def get(self, request):
        links = self.get_links()
        rows = [
            {"product": product, "selected": links.get(product.pk)}
            for product in self.get_rows()
        ]
        return render(
            request,
            self.template_name,
            {
                "title": self.title,
                "column_label": self.column_label,
                "empty_note": self.empty_note,
                "rows": rows,
                "options": list(self.option_source()),
                "breadcrumbs": _crumbs((self.title, "")),
            },
        )

    def post(self, request):
        saved = 0
        for product in self.get_rows():
            raw = request.POST.get(f"target_{product.pk}", "").strip()
            target = self.resolve_target(raw)
            try:
                type(self).save_link(product, target, request.user)
            except ValueError as error:
                messages.error(request, str(error))
                continue
            saved += 1
        messages.success(request, f"{saved} link(s) saved.")
        return redirect(request.path)

    def resolve_target(self, raw):
        if not raw:
            return None
        return ProductNode.objects.filter(pk=raw).first()


class AccountLinkView(LinkGridView):
    page = "products.account_links"
    link_model = ProductAccountLink
    link_field = "product"
    target_field = "purchase_account"
    title = "Account Linking"
    column_label = "Purchase account"
    empty_note = "Produced items are not listed: they are never bought."
    row_source = staticmethod(selectors.buyable_items)
    save_link = staticmethod(services.link_purchase_account)

    @staticmethod
    def option_source():
        from apps.core.constants import STATUS_ACTIVE

        return ChartOfAccount.objects.filter(is_group=False, status=STATUS_ACTIVE).order_by("code")

    def resolve_target(self, raw):
        if not raw:
            return None
        return ChartOfAccount.objects.filter(pk=raw).first()

    def get_rows(self):
        return list(selectors.buyable_items())


class RawBardanaLinkView(LinkGridView):
    page = "products.raw_bardana"
    link_model = RawBardanaLink
    link_field = "wheat_item"
    target_field = "bardana_item"
    title = "Raw Bardana Linking"
    column_label = "Arrives in"
    empty_note = "The sack a wheat item is delivered in, emptied at grinding."
    row_source = staticmethod(selectors.wheat_items)
    option_source = staticmethod(selectors.raw_packing_items)
    save_link = staticmethod(services.link_raw_bardana)


class FinishBardanaLinkView(LinkGridView):
    page = "products.finish_bardana"
    link_model = FinishBardanaLink
    link_field = "finish_item"
    target_field = "bag_item"
    title = "Finish Bardana Linking"
    column_label = "Packed in"
    empty_note = "Grinding reads this to decide which bag to consume."
    row_source = staticmethod(selectors.packable_items)
    option_source = staticmethod(selectors.finish_packing_items)
    save_link = staticmethod(services.link_finish_bardana)


class OpeningBalanceView(PagePermissionRequiredMixin, View):
    """Opening quantity per product, posted straight into the ledger."""

    page = "products.opening_balances"
    template_name = "products/opening_balances.html"

    def get(self, request):
        openings = {row.product_id: row for row in ProductOpeningBalance.objects.all()}
        rows = [
            {"product": product, "opening": openings.get(product.pk)}
            for product in selectors.stocked_items()
        ]
        return render(
            request,
            self.template_name,
            {"title": "Opening Balance", "rows": rows, "breadcrumbs": _crumbs(("Opening Balance", ""))},
        )

    def post(self, request):
        saved = 0
        for key, value in request.POST.items():
            if not key.startswith("qty_"):
                continue
            product = ProductNode.objects.filter(pk=key[4:]).first()
            if product is None or not (value or "").strip():
                continue
            services.set_opening_balance(
                product,
                value,
                as_of_date=request.POST.get(f"date_{product.pk}") or None,
                rate=request.POST.get(f"rate_{product.pk}") or 0,
                user=request.user,
            )
            saved += 1
        messages.success(request, f"{saved} opening balance(s) saved.")
        return redirect(request.path)


class RateUpdateView(PagePermissionRequiredMixin, View):
    """A rate per product. Saving writes history, it does not overwrite."""

    page = "products.rates"
    template_name = "products/rate_update.html"

    def get(self, request):
        current = {row.product_id: row for row in ProductRate.objects.filter(is_current=True)}
        rows = [
            {"product": product, "rate": current.get(product.pk)}
            for product in selectors.active_items()
        ]
        return render(
            request,
            self.template_name,
            {"title": "Rate Update", "rows": rows, "breadcrumbs": _crumbs(("Rate Update", ""))},
        )

    def post(self, request):
        saved = 0
        for key, value in request.POST.items():
            if not key.startswith("rate_"):
                continue
            product = ProductNode.objects.filter(pk=key[5:]).first()
            if product is None or not (value or "").strip():
                continue
            services.set_rate(product, value, request.POST.get(f"date_{product.pk}") or None, request.user)
            saved += 1
        messages.success(request, f"{saved} rate(s) saved.")
        return redirect(request.path)
