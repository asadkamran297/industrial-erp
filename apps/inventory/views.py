import csv
import io
import json

from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView, View

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apps.core.constants import INV_RETURN_DRAFT_STATUSES, GL_BROKERS_GROUP_TITLE, INV_BARDANA_OWNERSHIP_CHOICES, INV_SALES_ORDER_STATUS_CHOICES, STATUS_CLOSED, STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED, STATUS_FULLY_INVOICED, INV_PO_CANCEL_REASONS, INV_PO_CLOSE_SHORT_REASONS, INV_REVERSAL_REASONS, INVENTORY_KIND_PRODUCT, INVENTORY_KIND_SERVICE, INV_POS_STATUS_CHOICES, INV_PURCHASE_ORDER_STATUS_CHOICES, INV_TRANSACTION_TYPE_CHOICES, NO, RECORD_STATUS_CHOICES, STATUS_ACTIVE, STATUS_CREATED, STATUS_DRAFT, STATUS_INACTIVE, STATUS_CANCELLED, STATUS_POSTED, STATUS_REVERSED, YES
from apps.access_control.selectors import user_has_permission
from apps.core.models import SystemSetting
from apps.core.table_export import TableExportView
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, PrintContextMixin, SearchFilterPaginationMixin, SortableListMixin
from apps.finance.models import AccountVoucherLine, ChartOfAccount
from apps.finance.services import account_balances, account_ledger, create_customer_receivable_account, sync_supplier_opening_balance
from apps.finance.views import AuditSaveMixin

from .forms import PurchaseApprovalLimitForm, PurchaseOrderCancelForm, PurchaseOrderCloseShortForm, ReversalReasonForm, CustomerForm, InventoryClassForm, InventoryItemForm, InventoryItemImportForm, ManualTransactionForm, POSDetailForm, POSMasterForm, POSReturnDetailForm, POSReturnMasterForm, PurchaseOrderForm, PurchaseOrderItemForm, PurchaseReturnDetailForm, PurchaseReturnMasterForm, UOMConversionForm, UOMForm, SupplierForm
from .models import PurchaseInvoice, PurchaseInvoiceLine, SalesOrder, SalesOrderItem, Customer, CustomerLedger, InventoryClass, InventoryItem, ItemLedger, ManualTransaction, POSDetail, POSMaster, POSReturnDetail, POSReturnMaster, PurchaseOrder, PurchaseOrderItem, PurchaseReturnDetail, PurchaseReturnMaster, Stock, UOM, UOMConversion, Supplier
from .purchase_board import RETURN_COLUMNS, RETURN_TAB_ALL, RETURN_TAB_DRAFT, RETURN_TAB_POSTED, RETURN_TAB_REVERSED, RETURN_TABS, COLUMNS, PURCHASE_INVOICE_COLUMNS, SALE_COLUMNS, TAB_ALL, TAB_LIVE, TABS, TAB_STATUSES, column_menu, decorate, export_columns, linked_documents, set_visible_columns, summarise, visible_columns
from .form_layout import EXTRA_FIELD_TYPES, FORM_PURCHASE_INVOICE, FORM_PURCHASE_ORDER, add_extra_field, get_layout, read_extra_values, remove_extra_field, set_hidden
from .models import TWO_DP
from .services import create_purchase_return, next_purchase_return_number, purchase_return_lines, reverse_purchase_return, close_sales_order, create_sales_order, customer_has_open_orders, next_sales_order_number, open_sales_order_lines, submit_sales_order, _refresh_order_invoiced_status, can_reverse_invoice, create_purchase_invoice, next_purchase_invoice_number, open_order_lines, reverse_purchase_invoice, supplier_has_open_orders, approve_purchase_order, cancel_purchase_order, close_purchase_order_short, needs_approval, purchase_order_approval_limit, reopen_purchase_order, set_purchase_order_approval_limit, user_can_approve, amount_in_words, create_direct_sale, create_purchase_order, finalize_manual_transaction, set_opening_stock, generate_transaction_id, next_purchase_order_number, next_sale_invoice_number, post_purchase_return, post_sale, post_sale_return

User = get_user_model()


def decimal_of(raw, default="0"):
    """A posted money or quantity box, read as the number it is.

    Money boxes are grouped with commas on screen; the grouping is stripped
    before the form posts, but a figure that arrives grouped anyway is read
    rather than rejected.
    """
    text = (raw or "").strip().replace(",", "") or default
    return Decimal(text)


def uom_title(record):
    """The unit shown against a record, blank where it carries none.

    An item is allowed to have no unit, so every screen that prints one has to
    survive the empty case rather than reaching through a null relation.
    """
    return record.uom.title if record and record.uom_id else ""


def godown_options():
    """Every godown a document may name, cheapest query that answers it."""
    from apps.godowns.models import Godown

    return Godown.objects.filter(status=STATUS_ACTIVE).order_by("code")


def broker_options():
    """The brokers on file: postable accounts under the Brokers heading.

    Not every account in the chart — a broker is owed brokerage, so it is one of
    the accounts kept for that, and offering the whole chart would let a purchase
    name the bank as its broker.
    """
    return (
        ChartOfAccount.objects
        .filter(is_group=False, status=STATUS_ACTIVE, parent__title=GL_BROKERS_GROUP_TITLE)
        .order_by("title")
    )


def wheat_product_options():
    """The wheat the mill buys: raw items on the product tree, nothing else.

    Read off the tree rather than a list of codes on this screen, so a second
    variety of wheat is added by the people who add products and needs no
    release here.
    """
    from apps.products.selectors import wheat_items

    return wheat_items().order_by("complete_code")


def bardana_product_options():
    """The sacks: raw packing items on the product tree."""
    from apps.products.selectors import raw_packing_items

    return raw_packing_items().order_by("complete_code")


def picked(posted, name, queryset):
    """The row a select posted, or None where nothing was chosen.

    Looked up through the same queryset the picker was built from, so a value
    typed into the request that the operator was never offered is not accepted.
    """
    raw = (posted.get(name) or "").strip()
    if not raw.isdigit():
        return None
    return queryset.filter(pk=raw).first()


def item_unit_options(item):
    """The units an item is actually handled in, and what each is worth in its own.

    Its own unit, the second one it is bought or issued in, and the other side
    of whatever conversion is set against it. An item with none configured
    returns nothing, and the caller falls back to the full list rather than
    leaving the operator with an empty dropdown.

    ``factor`` is how many base units one of that unit makes, so a screen can
    show what a quantity comes to in stock terms without asking the server.
    """
    units, seen = [], set()
    candidates = [item.uom, item.secondary_uom]
    if item.conversion_id:
        candidates += [item.conversion.uom_from, item.conversion.uom_to]
    for unit in candidates:
        if unit and unit.pk not in seen:
            seen.add(unit.pk)
            units.append({"id": unit.pk, "name": unit.title, "factor": unit_factor_to_base(item, unit)})
    return units


def unit_factor_to_base(item, unit):
    """How many of the item's own units one ``unit`` makes; 0 where none is set."""
    base = item.uom
    if not base or not unit:
        return 0
    if unit.pk == base.pk:
        return 1
    down = UOMConversion.objects.filter(uom_from=base, uom_to=unit, status=STATUS_ACTIVE).first()
    if down and down.conversion_factor:
        return float(1 / down.conversion_factor)
    up = UOMConversion.objects.filter(uom_from=unit, uom_to=base, status=STATUS_ACTIVE).first()
    if up and up.conversion_factor:
        return float(up.conversion_factor)
    return 0


class InventoryListMixin(SearchFilterPaginationMixin, PagePermissionRequiredMixin):
    pass


class InventoryManageMixin(AuditSaveMixin, PagePermissionRequiredMixin):
    pass


class BaseSimpleListView(InventoryListMixin, ListView):
    template_name = "inventory/simple_list.html"
    context_object_name = "records"
    extra_context = {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.extra_context)
        return context


class InventoryClassListView(BaseSimpleListView):
    """Categories on the left, the items filed under one of them on the right.

    Same shape as the units screen: nothing here navigates, every exchange
    swaps the two panes. "Items not in any category" is a row in the list but
    not a record -- it stands for item_class being null.
    """

    page = "inventory.classes"
    model = InventoryClass
    template_name = "inventory/class_list.html"
    queryset = InventoryClass.objects.order_by("title")
    paginate_by = 100
    search_fields = ("title", "class_code")
    extra_context = {"title": "Item Categories", "active_tab": "category"}

    UNFILED = "none"

    def _is_ajax(self):
        return self.request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def get_queryset(self):
        return super().get_queryset().annotate(item_count=Count("inventoryitem", distinct=True))

    def get_selected(self):
        """The category on show, or the sentinel for the unfiled row.

        Returns (selected_class, is_unfiled). Nothing chosen means the unfiled
        row, so the screen always opens on something.
        """
        raw = self.request.GET.get("selected_class") or self.request.POST.get("selected_class") or ""
        if raw in ("", self.UNFILED):
            return None, True
        return InventoryClass.objects.filter(pk=raw).first(), False

    def get_items(self, selected_class, is_unfiled, search=""):
        items = InventoryItem.objects.select_related("stock").order_by("item_name")
        items = items.filter(item_class__isnull=True) if is_unfiled else items.filter(item_class=selected_class)
        if search:
            items = items.filter(Q(item_name__icontains=search) | Q(code__icontains=search))
        return items

    @staticmethod
    def _decorate_items(rows):
        """Stock value per row, so the table does no arithmetic of its own."""
        rows = list(rows)
        for row in rows:
            stock = getattr(row, "stock", None)
            quantity = stock.current_quantity if stock else Decimal("0.0000")
            price = stock.current_price if stock else Decimal("0.00")
            row.stock_quantity = quantity
            row.stock_value = (quantity * price).quantize(Decimal("0.01"))
        return rows

    def _pane_context(self, selected_class, is_unfiled):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["selected_class"] = selected_class
        context["is_unfiled"] = is_unfiled
        context["item_search"] = self.request.GET.get("item_q", "").strip()
        context["items"] = self._decorate_items(
            self.get_items(selected_class, is_unfiled, context["item_search"])
        )
        return context

    def _fragments(self, selected_class, is_unfiled):
        context = self._pane_context(selected_class, is_unfiled)
        return {
            "rows_html": render_to_string("inventory/_class_rows.html", context, request=self.request),
            "detail_html": render_to_string("inventory/_class_detail.html", context, request=self.request),
            "selected_class": "" if is_unfiled else selected_class.pk,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unfiled_count"] = InventoryItem.objects.filter(item_class__isnull=True).count()
        context["category_form"] = InventoryClassForm()
        context.setdefault("selected_class", None)
        context.setdefault("is_unfiled", True)
        return context

    def get(self, request, *args, **kwargs):
        if not self._is_ajax():
            return super().get(request, *args, **kwargs)
        selected_class, is_unfiled = self.get_selected()
        if request.GET.get("mode") == "picker":
            return JsonResponse({"picker_html": self._picker_html(selected_class, is_unfiled)})
        return JsonResponse(self._fragments(selected_class, is_unfiled))

    def _picker_html(self, selected_class, is_unfiled):
        """Rows for the Select Items dialog: everything not already filed here."""
        search = self.request.GET.get("pick_q", "").strip()
        items = InventoryItem.objects.select_related("item_class", "stock").order_by("item_name")
        items = items.filter(item_class__isnull=False) if is_unfiled else items.exclude(item_class=selected_class)
        if search:
            items = items.filter(Q(item_name__icontains=search) | Q(code__icontains=search))
        context = {"items": self._decorate_items(items[:200])}
        return render_to_string("inventory/_class_picker.html", context, request=self.request)

    def _refused(self, message, status):
        if self._is_ajax():
            return JsonResponse({"ok": False, "errors": {"__all__": [message]}}, status=status)
        messages.error(self.request, message)
        return redirect("inventory:class_list")

    def _saved(self, selected_class, is_unfiled, message):
        if self._is_ajax():
            payload = self._fragments(selected_class, is_unfiled)
            payload.update(ok=True, message=message)
            return JsonResponse(payload)
        messages.success(self.request, message)
        base = str(reverse_lazy("inventory:class_list"))
        return redirect(base if is_unfiled else f"{base}?selected_class={selected_class.pk}")

    def _rejected(self, form):
        if self._is_ajax():
            errors = {field: [str(e) for e in errs] for field, errs in form.errors.items()}
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        for errs in form.errors.values():
            for error in errs:
                messages.error(self.request, error)
        return redirect("inventory:class_list")

    def post(self, request, *args, **kwargs):
        if not user_has_permission(request.user, f"{self.page}.add"):
            return self._refused("You cannot change categories.", 403)

        action = request.POST.get("action")
        if action == "category":
            return self._save_category(request)
        if action == "category_delete":
            return self._delete_category(request)
        if action == "move":
            return self._move_items(request)
        return self._refused("Unknown action.", 400)

    def _save_category(self, request):
        category_id = request.POST.get("category_id")
        instance = InventoryClass.objects.filter(pk=category_id).first() if category_id else None
        if category_id and not instance:
            return self._refused("That category no longer exists.", 404)

        data = request.POST.copy()
        if not data.get("class_code"):
            data["class_code"] = instance.class_code if instance else InventoryItemForm._next_class_code(data.get("title", ""))
        data.setdefault("status", STATUS_ACTIVE)

        form = InventoryClassForm(data, instance=instance)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = category.created_by or request.user
            category.updated_by = request.user
            category.save()
            return self._saved(category, False, "Category updated." if instance else "Category created.")
        return self._rejected(form)

    def _delete_category(self, request):
        if not user_has_permission(request.user, f"{self.page}.delete"):
            return self._refused("You cannot delete categories.", 403)

        category = InventoryClass.objects.filter(pk=request.POST.get("category_id")).first()
        if not category:
            return self._refused("That category no longer exists.", 404)

        held = InventoryItem.objects.filter(item_class=category).count()
        if held:
            return self._refused(
                f"{category.title} still holds {held} item{'s' if held > 1 else ''}. Move them out first.", 400
            )

        category.soft_delete(user=request.user)
        return self._saved(None, True, f"{category.title} deleted.")

    def _move_items(self, request):
        """File the ticked items under the open category.

        item_class holds one category, so a move is a reassignment. Items that
        already sit somewhere else are only touched when the operator says so,
        which is what the tick box on the dialog asks.
        """
        selected_class, is_unfiled = self.get_selected()
        if not is_unfiled and not selected_class:
            return self._refused("That category no longer exists.", 404)

        ids = request.POST.getlist("item_ids")
        if not ids:
            return self._refused("Pick at least one item.", 400)

        items = InventoryItem.objects.filter(pk__in=ids)
        take_filed = request.POST.get("remove_existing") == "1"
        if not take_filed:
            already = items.filter(item_class__isnull=False).count()
            items = items.filter(item_class__isnull=True)
            if not items.exists():
                return self._refused(
                    f"{already} of those already sit in another category. "
                    "Tick 'Remove selected items from existing category' to move them.", 400
                )

        moved = 0
        for item in items:
            item.item_class = None if is_unfiled else selected_class
            item.updated_by = request.user
            item.save(update_fields=["item_class", "updated_by", "updated_at"])
            moved += 1

        where = "no category" if is_unfiled else selected_class.title
        return self._saved(selected_class, is_unfiled, f"{moved} item{'s' if moved > 1 else ''} moved to {where}.")


class InventoryClassToggleStatusView(InventoryManageMixin, View):
    page = "inventory.classes"
    action = "edit"
    def post(self, request, pk):
        record = get_object_or_404(InventoryClass, pk=pk)
        record.status = STATUS_INACTIVE if record.status == STATUS_ACTIVE else STATUS_ACTIVE
        record.updated_by = request.user
        record.save(update_fields=["status", "updated_by", "updated_at"])
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("inventory:class_list"))


class UOMToggleStatusView(InventoryManageMixin, View):
    page = "inventory.uoms"
    action = "edit"
    def post(self, request, pk):
        record = get_object_or_404(UOM, pk=pk)
        record.status = STATUS_INACTIVE if record.status == STATUS_ACTIVE else STATUS_ACTIVE
        record.updated_by = request.user
        record.save(update_fields=["status", "updated_by", "updated_at"])
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("inventory:uom_list"))


class InventoryClassCreateView(InventoryManageMixin, CreateView):
    page = "inventory.classes"
    model = InventoryClass
    form_class = InventoryClassForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:class_list")
    success_message = "Inventory class saved."
    extra_context = {"title": "Item Category"}


class InventoryClassUpdateView(InventoryClassCreateView, UpdateView):
    success_message = "Inventory class updated."


class UOMListView(BaseSimpleListView):
    page = "inventory.uoms"
    model = UOM
    template_name = "inventory/uom_list.html"
    queryset = UOM.objects.order_by("title")
    paginate_by = 100
    search_fields = ("title", "code")
    filter_fields = {"status": "status"}
    extra_context = {"title": "Units of Measure", "create_url": reverse_lazy("inventory:uom_create"), "edit_url_name": "inventory:uom_update", "active_tab": "units", "columns": [("Title", "title"), ("Code", "code"), ("Status", "get_status_display")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 

    def get_selected_uom(self):
        selected_uom_id = self.request.GET.get("selected_uom") or self.request.POST.get("selected_uom")
        if not selected_uom_id:
            return None
        return UOM.objects.filter(pk=selected_uom_id).first()

    def get_conversions(self, selected_uom):
        """Every conversion held against the selected unit.

        A unit can be measured more than one way -- a bag is 20kg on one line
        and 50kg on another -- so the panel lists them rather than holding one.
        """
        if not selected_uom:
            return UOMConversion.objects.none()
        return UOMConversion.objects.filter(uom_from=selected_uom).select_related("uom_from", "uom_to")

    def get_conversion_form(self, selected_uom, instance=None, data=None):
        form = UOMConversionForm(data=data, instance=instance)
        form.fields["uom_from"].queryset = UOM.objects.filter(pk=selected_uom.pk) if selected_uom else UOM.objects.none()
        form.fields["uom_to"].queryset = UOM.objects.exclude(pk=selected_uom.pk) if selected_uom else UOM.objects.none()
        if selected_uom and not form.is_bound:
            form.initial.setdefault("uom_from", selected_uom.pk)
        return form


    def _is_ajax(self):
        return self.request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def _fragments(self, selected_uom, **extra):
        self.object_list = self.get_queryset()
        context = self.get_context_data(**extra)
        context["selected_uom"] = selected_uom
        context["uom_conversions"] = self.get_conversions(selected_uom)
        payload = {
            "rows_html": render_to_string("inventory/_uom_rows.html", context, request=self.request),
            "detail_html": render_to_string("inventory/_uom_detail.html", context, request=self.request),
            "selected_uom": selected_uom.pk if selected_uom else "",
        }
        return payload

    @staticmethod
    def _errors(form):
        return {field: [str(e) for e in errors] for field, errors in form.errors.items()}

    def get(self, request, *args, **kwargs):
        if not self._is_ajax():
            return super().get(request, *args, **kwargs)
        return JsonResponse(self._fragments(self.get_selected_uom()))

    def _redirect_to_unit(self, selected_uom):
        base = str(reverse_lazy("inventory:uom_list"))
        return redirect(f"{base}?selected_uom={selected_uom.pk}" if selected_uom else base)

    def _saved(self, selected_uom, message):
        if self._is_ajax():
            payload = self._fragments(selected_uom)
            payload.update(ok=True, message=message)
            return JsonResponse(payload)
        messages.success(self.request, message)
        return self._redirect_to_unit(selected_uom)

    def _not_found(self, message):
        return self._refused(message, status=404)

    def _forbidden(self, message):
        return self._refused(message, status=403)

    def _rejected_message(self, message):
        return self._refused(message, status=400)

    def _refused(self, message, status):
        if self._is_ajax():
            return JsonResponse({"ok": False, "errors": {"__all__": [message]}}, status=status)
        messages.error(self.request, message)
        return redirect("inventory:uom_list")

    def _rejected(self, form):
        if self._is_ajax():
            return JsonResponse({"ok": False, "errors": self._errors(form)}, status=400)
        for errors in form.errors.values():
            for error in errors:
                messages.error(self.request, error)
        return self._redirect_to_unit(self.get_selected_uom())

    def post(self, request, *args, **kwargs):
        if not user_has_permission(request.user, f"{self.page}.add"):
            return self._forbidden("You cannot change units.")

        action = request.POST.get("action")
        if action == "unit":
            return self._save_unit(request)
        if action == "unit_delete":
            return self._delete_unit(request)
        if action == "conversion_delete":
            return self._delete_conversion(request)
        return self._save_conversion(request)

    def _save_unit(self, request):
        unit_id = request.POST.get("unit_id")
        instance = UOM.objects.filter(pk=unit_id).first() if unit_id else None
        if unit_id and not instance:
            return self._not_found("That unit no longer exists.")

        form = UOMForm(request.POST, instance=instance)
        if form.is_valid():
            unit = form.save(commit=False)
            unit.created_by = unit.created_by or request.user
            unit.updated_by = request.user
            unit.save()
            return self._saved(unit, "Unit updated." if instance else "Unit saved.")
        return self._rejected(form)

    @staticmethod
    def _usage(record, ignore=()):
        """Everything in the database still pointing at this record.

        Walked off the model's own relations rather than a hand-written list,
        so a table added later is counted without anyone remembering to come
        back here. A figure that was measured in a unit has to keep reading
        back the same way, so anything still referenced is never deleted.
        """
        found = []
        for relation in record._meta.related_objects:
            model = relation.related_model
            if model in ignore:
                continue
            manager = getattr(model, "objects", model._default_manager)
            count = manager.filter(**{relation.field.name: record}).count()
            if count:
                label = model._meta.verbose_name if count == 1 else model._meta.verbose_name_plural
                found.append(f"{count} {label}")
        return found

    def _delete_unit(self, request):
        """Retire a unit, provided nothing anywhere is measured in it."""
        if not user_has_permission(request.user, f"{self.page}.delete"):
            return self._forbidden("You cannot delete units.")

        unit = UOM.objects.filter(pk=request.POST.get("unit_id")).first()
        if not unit:
            return self._not_found("That unit no longer exists.")

        blockers = self._usage(unit, ignore=(UOMConversion,))
        own_conversions = UOMConversion.objects.filter(Q(uom_from=unit) | Q(uom_to=unit))
        for conversion in own_conversions:
            blockers += self._usage(conversion)
        if blockers:
            return self._rejected_message(
                f"{unit.title} cannot be deleted: it is still used by {', '.join(blockers)}. "
                "Deactivate it instead, so past figures keep reading back."
            )

        for conversion in own_conversions:
            conversion.soft_delete(user=request.user)
        unit.soft_delete(user=request.user)

        selected_uom = self.get_selected_uom()
        if selected_uom and selected_uom.pk == unit.pk:
            selected_uom = None  # the pane was showing what just went away
        return self._saved(selected_uom, f"{unit.title} deleted.")

    def _delete_conversion(self, request):
        if not user_has_permission(request.user, f"{self.page}.delete"):
            return self._forbidden("You cannot delete conversions.")

        selected_uom = self.get_selected_uom()
        conversion = self.get_conversions(selected_uom).filter(pk=request.POST.get("conversion_id")).first()
        if not conversion:
            return self._not_found("That conversion no longer exists.")

        blockers = self._usage(conversion)
        if blockers:
            return self._rejected_message(
                f"This conversion cannot be deleted: it is still used by {', '.join(blockers)}. "
                "Deactivate it instead, so past figures keep reading back."
            )

        conversion.soft_delete(user=request.user)
        return self._saved(selected_uom, "Conversion deleted.")

    def _save_conversion(self, request):
        selected_uom = self.get_selected_uom()
        if not selected_uom:
            return self._rejected_message("Select a unit first.")

        conversion_id = request.POST.get("conversion_id")
        instance = self.get_conversions(selected_uom).filter(pk=conversion_id).first() if conversion_id else None

        form = self.get_conversion_form(selected_uom, instance=instance, data=request.POST)
        if form.is_valid():
            conversion = form.save(commit=False)
            conversion.created_by = conversion.created_by or request.user
            conversion.updated_by = request.user
            conversion.save()
            return self._saved(selected_uom, "Conversion updated." if instance else "Conversion saved.")
        return self._rejected(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_uom = self.get_selected_uom()
        context["selected_uom"] = selected_uom
        context["uom_conversions"] = self.get_conversions(selected_uom)
        context["unit_form"] = UOMForm()
        context["all_units"] = UOM.objects.order_by("title")
        return context


class UOMCreateView(InventoryManageMixin, CreateView):
    page = "inventory.uoms"
    model = UOM
    form_class = UOMForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:uom_list")
    success_message = "UOM saved."
    extra_context = {"title": "UOM"}


class UOMUpdateView(UOMCreateView, UpdateView):
    success_message = "UOM updated."


class UOMConversionListView(BaseSimpleListView):
    page = "inventory.uom_conversions"
    model = UOMConversion
    queryset = UOMConversion.objects.select_related("uom_from", "uom_to").order_by("uom_from__title")
    search_fields = ("uom_from__title", "uom_to__title")
    filter_fields = {"status": "status"}
    extra_context = {"title": "UOM Conversions", "create_url": reverse_lazy("inventory:conversion_create"), "edit_url_name": "inventory:conversion_update", "status_toggle_url_name": "inventory:conversion_toggle_status", "columns": [("From", "uom_from"), ("To", "uom_to"), ("Factor", "conversion_factor"), ("Status", "status_toggle")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class UOMConversionToggleStatusView(InventoryManageMixin, View):
    page = "inventory.uom_conversions"
    action = "edit"
    def post(self, request, pk):
        record = get_object_or_404(UOMConversion, pk=pk)
        record.status = STATUS_INACTIVE if record.status == STATUS_ACTIVE else STATUS_ACTIVE
        record.updated_by = request.user
        record.save(update_fields=["status", "updated_by", "updated_at"])
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "status": record.status, "message": "Conversion activated." if record.status == STATUS_ACTIVE else "Conversion deactivated."})
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("inventory:conversion_list"))


class UOMConversionCreateView(InventoryManageMixin, CreateView):
    page = "inventory.uom_conversions"
    model = UOMConversion
    form_class = UOMConversionForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:conversion_list")
    success_message = "UOM conversion saved."
    extra_context = {"title": "UOM Conversion"}


class UOMConversionUpdateView(UOMConversionCreateView, UpdateView):
    success_message = "UOM conversion updated."


class SupplierListView(SortableListMixin, BaseSimpleListView):
    """Suppliers, each row opening onto what the business has bought from them."""

    page = "inventory.suppliers"
    model = Supplier
    template_name = "inventory/supplier_list.html"
    queryset = Supplier.objects.select_related("city").order_by("-id")
    search_fields = ("name", "code", "email", "tel1")
    sort_fields = {"name": "name", "code": "code", "city": "city__title", "status": ("status", "name"), "added": "-id"}
    python_sort_fields = {"payable": "payable_balance"}
    default_sort = "added"
    filter_fields = {"status": "status"}
    extra_context = {"title": "Suppliers", "create_url": reverse_lazy("inventory:supplier_create"), "edit_url_name": "inventory:supplier_update", "status_toggle_url_name": "inventory:supplier_toggle_status"}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        suppliers = list(context.get("records") or [])
        if not suppliers:
            return context

        zero = Decimal("0.00")
        purchases = {
            row["supplier_id"]: row
            for row in PurchaseInvoice.objects.filter(supplier__in=suppliers, status=STATUS_POSTED)
            .values("supplier_id")
            .annotate(total=Sum("total_amount"), count=Count("id"))
        }
        returns = {
            row["supplier_id"]: row
            for row in PurchaseReturnMaster.objects.filter(supplier__in=suppliers)
            .values("supplier_id")
            .annotate(total=Sum("returned_amount"), count=Count("id"))
        }
        orders = {
            row["supplier_id"]: row["count"]
            for row in PurchaseOrder.objects.filter(supplier__in=suppliers).values("supplier_id").annotate(count=Count("id"))
        }
        payable_codes = dict(
            ChartOfAccount.objects.filter(title__in=[supplier.name for supplier in suppliers])
            .values_list("title", "code")
        )
        balances = account_balances()

        entries = {}
        if payable_codes:
            lines = (
                AccountVoucherLine.objects.filter(account_no__in=payable_codes.values())
                .select_related("voucher")
                .order_by("voucher_date", "voucher_no", "line_number")
            )
            for line in lines:
                entries.setdefault(line.account_no, []).append(line)

        def ledger_rows(code):
            """Payables are credit-natured: a purchase raises the balance, a payment lowers it."""
            running = (balances.get(code) or {}).get("opening") or zero
            rows = []
            for line in entries.get(code, []):
                debit = line.debit_amount or zero
                credit = line.credit_amount or zero
                running += credit - debit
                rows.append({"line": line, "debit": debit, "credit": credit, "balance": running})
            return rows[::-1][:8]  # newest first, the last few dealings

        for supplier in suppliers:
            bought = purchases.get(supplier.id) or {}
            sent_back = returns.get(supplier.id) or {}
            supplier.purchase_total = bought.get("total") or zero
            supplier.purchase_count = bought.get("count") or 0
            supplier.return_total = sent_back.get("total") or zero
            supplier.return_count = sent_back.get("count") or 0
            supplier.order_count = orders.get(supplier.id, 0)
            supplier.payable_code = payable_codes.get(supplier.name, "")
            supplier.payable_balance = (balances.get(supplier.payable_code) or {}).get("closing") or zero
            supplier.ledger_rows = ledger_rows(supplier.payable_code) if supplier.payable_code else []

        context["records"] = self.sort_rows(suppliers)
        all_suppliers = self.get_queryset()
        context["supplier_count"] = all_suppliers.count()
        context["purchased_total"] = (
            PurchaseInvoice.objects.filter(supplier__in=all_suppliers, status=STATUS_POSTED)
            .aggregate(total=Sum("total_amount"))["total"] or zero
        )
        all_codes = ChartOfAccount.objects.filter(
            title__in=all_suppliers.values_list("name", flat=True), is_group=False
        ).values_list("code", flat=True)
        context["payable_total"] = sum(((balances.get(code) or {}).get("closing") or zero for code in all_codes), zero)
        return context


class SupplierDetailView(PagePermissionRequiredMixin, DetailView):
    """Everything on file for one supplier, with their ledger underneath."""

    page = "inventory.suppliers"
    model = Supplier
    template_name = "inventory/supplier_detail.html"
    context_object_name = "supplier"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier = self.object
        zero = Decimal("0.00")

        bought = PurchaseInvoice.objects.filter(supplier=supplier, status=STATUS_POSTED).aggregate(total=Sum("total_amount"), count=Count("id"))
        sent_back = PurchaseReturnMaster.objects.filter(supplier=supplier).aggregate(total=Sum("returned_amount"), count=Count("id"))
        context["purchase_total"] = bought["total"] or zero
        context["purchase_count"] = bought["count"] or 0
        context["return_total"] = sent_back["total"] or zero
        context["return_count"] = sent_back["count"] or 0
        context["order_count"] = PurchaseOrder.objects.filter(supplier=supplier).count()
        context["recent_invoices"] = PurchaseInvoice.objects.filter(supplier=supplier, status=STATUS_POSTED).order_by("-invoice_date", "-id")[:10]

        account = ChartOfAccount.objects.filter(title=supplier.name, is_group=False).first()
        context["payable_code"] = account.code if account else ""
        ledger = account_ledger(account.code) if account else None
        context["ledger"] = ledger
        context["payable_balance"] = ledger["closing"] if ledger else zero
        return context


class SupplierToggleStatusView(InventoryManageMixin, View):
    page = "inventory.suppliers"
    action = "edit"
    def post(self, request, pk):
        record = get_object_or_404(Supplier, pk=pk)
        record.status = STATUS_INACTIVE if record.status == STATUS_ACTIVE else STATUS_ACTIVE
        record.updated_by = request.user
        record.save(update_fields=["status", "updated_by", "updated_at"])
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("inventory:supplier_list"))


class EmbeddedCreateMixin:
    """A create screen that can also be opened in a modal on another screen.

    The whole form is framed rather than a thinner copy of it being written for
    the modal, so a record added mid-entry is the same record, with the same
    validation, as one added from its own menu. On save the frame tells the
    screen underneath what was created and that screen closes the modal.
    """

    embed_message_type = ""

    def embed_payload(self, obj):
        raise NotImplementedError

    def is_embedded(self):
        return self.request.GET.get("embed") == "1"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if self.is_embedded():
            response.xframe_options_exempt = True
            response["X-Frame-Options"] = "SAMEORIGIN"
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.is_embedded():
            context["embed"] = True
            context["embed_layout"] = "layouts/embed.html"
        return context

    def embed_saved_response(self):
        return render(self.request, "inventory/_embed_saved.html", {
            "message_type": self.embed_message_type,
            "payload_json": json.dumps(self.embed_payload(self.object)),
        })


class SupplierCreateView(EmbeddedCreateMixin, InventoryManageMixin, CreateView):
    page = "inventory.suppliers"
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/supplier_form.html"
    success_url = reverse_lazy("inventory:supplier_list")
    success_message = "Supplier saved."
    embed_message_type = "supplier:saved"
    extra_context = {
        "title": "Supplier",
        "registration_fields": ("code", "ntn_number", "sale_tax_num", "web_url"),
        "extra_fields": ("fax", "tel2", "status", "supplier_current_status", "remarks"),
    }

    def embed_payload(self, obj):
        return {"id": obj.pk, "name": obj.name, "balance": str(obj.opening_balance or "")}

    def form_valid(self, form):
        response = super().form_valid(form)
        sync_supplier_opening_balance(supplier=self.object, user=self.request.user)
        if self.is_embedded():
            return self.embed_saved_response()
        return response

    def get_success_url(self):
        if "save_and_new" in self.request.POST:
            return reverse_lazy("inventory:supplier_create")
        return super().get_success_url()


class SupplierUpdateView(SupplierCreateView, UpdateView):
    success_message = "Supplier updated."


class ItemStockListMixin(InventoryListMixin):
    """Items with the stock figures that used to live on their own page.

    Stock is one row per item, so the two are read together rather than kept as
    separate screens; the item list is the only place either is now shown.
    """

    page = "inventory.items"
    model = InventoryItem
    context_object_name = "records"
    queryset = InventoryItem.objects.select_related("uom", "item_class", "stock").order_by("item_name")
    search_fields = ("item_name", "code", "item_bar_code", "stock__item_code", "stock__item_name")
    filter_fields = {"status": "status", "item_class": "item_class_id"}

    def item_kind(self):
        """Which tab is being viewed. Products unless Services is asked for."""
        return INVENTORY_KIND_SERVICE if self.request.GET.get("kind") == INVENTORY_KIND_SERVICE else INVENTORY_KIND_PRODUCT

    def get_queryset(self):
        return super().get_queryset().filter(item_kind=self.item_kind())

    def get_filter_specs(self):
        class_choices = list(InventoryClass.objects.order_by("title").values_list("id", "title"))
        return [
            {"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")},
            {"name": "item_class", "label": "All classes", "choices": class_choices, "value": self.request.GET.get("item_class", "")},
        ]

    @staticmethod
    def _decorate(rows):
        """Attach the per-row stock value and return the (quantity, value) totals."""
        total_quantity = Decimal("0.0000")
        total_value = Decimal("0.00")
        for row in rows:
            stock = getattr(row, "stock", None)
            quantity = stock.current_quantity if stock else Decimal("0.0000")
            price = stock.current_price if stock else row.price
            row.stock_value = (quantity * price).quantize(Decimal("0.01"))
            total_quantity += quantity
            total_value += row.stock_value
        return total_quantity, total_value

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_quantity, total_value = self._decorate(context["records"])
        context["page_total_quantity"] = total_quantity
        context["page_total_value"] = total_value
        is_service = self.item_kind() == INVENTORY_KIND_SERVICE
        context["active_tab"] = "services" if is_service else "products"
        context["is_service_tab"] = is_service
        context["product_value"] = INVENTORY_KIND_PRODUCT
        context["service_value"] = INVENTORY_KIND_SERVICE
        return context


class ItemListView(ItemStockListMixin, ListView):
    template_name = "inventory/item_list.html"

    def get_context_data(self, **kwargs):
        from apps.finance.services import inventory_control_summary  # lazy: finance imports inventory

        context = super().get_context_data(**kwargs)
        context["title"] = "Services" if context["is_service_tab"] else "Inventory Items"
        context["create_url"] = reverse_lazy("inventory:item_create")
        context["control_account"] = None if context["is_service_tab"] else inventory_control_summary()
        return context


class ItemPrintView(PrintContextMixin, ItemStockListMixin, ListView):
    """Every item under the filters currently applied, unpaginated."""

    action = "index"
    template_name = "inventory/item_print.html"
    paginate_by = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["print_back_url"] = reverse_lazy("inventory:item_list")
        return context


class ItemExportView(ItemStockListMixin, ListView):
    """The item list as a spreadsheet, under the filters currently applied.

    Written as UTF-8 CSV rather than a real workbook: Excel opens it directly
    and it keeps the export dependency-free, matching the voucher export.
    """

    action = "index"
    paginate_by = None

    def get(self, request, *args, **kwargs):
        rows = list(self.get_queryset())
        total_quantity, total_value = self._decorate(rows)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        stamp = timezone.localdate().isoformat()
        response["Content-Disposition"] = f'attachment; filename="inventory-items-{stamp}.csv"'
        response.write("﻿")
        writer = csv.writer(response)
        writer.writerow(["Item Name", "Code", "Category", "UOM", "Stock Qty", "Current Price", "Last Price", "Stock Value", "Status"])
        for row in rows:
            stock = getattr(row, "stock", None)
            writer.writerow([
                row.item_name,
                row.code,
                row.item_class.title if row.item_class_id else "",
                uom_title(row),
                stock.current_quantity if stock else "",
                stock.current_price if stock else "",
                stock.last_price if stock else "",
                row.stock_value,
                row.get_status_display(),
            ])
        writer.writerow(["Totals", "", "", "", total_quantity, "", "", total_value, ""])
        return response


class ItemImportView(PagePermissionRequiredMixin, FormView):
    """Create items in bulk from a CSV.

    Every row is validated through ``InventoryItemForm`` so an import cannot
    write anything the Add Item screen would have rejected, and the whole file
    is applied in one transaction: a partly-imported list is worse than none.
    """

    page = "inventory.items"
    action = "add"
    form_class = InventoryItemImportForm
    template_name = "inventory/item_import.html"
    success_url = reverse_lazy("inventory:item_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Import Items"
        context["sample_url"] = reverse_lazy("inventory:item_import_sample")
        return context

    @staticmethod
    def _lookup(model, value, fields):
        """Find a master record by any of ``fields``, case-insensitively."""
        value = (value or "").strip()
        if not value:
            return None
        for field in fields:
            match = model.objects.filter(**{f"{field}__iexact": value}).first()
            if match:
                return match
        return None

    @staticmethod
    def _read_csv(upload):
        """(header names, row dicts) from a CSV upload."""
        # utf-8-sig strips Excel's BOM.
        text = upload.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = [(name or "").strip().lower() for name in (reader.fieldnames or [])]
        rows = [{(k or "").strip().lower(): str(v or "").strip() for k, v in raw.items() if k} for raw in reader]
        return headers, rows

    @staticmethod
    def _read_xlsx(upload):
        """(header names, row dicts) from the first sheet of an .xlsx upload."""
        from openpyxl import load_workbook

        workbook = load_workbook(upload, data_only=True, read_only=True)
        try:
            sheet = workbook.worksheets[0]
            grid = sheet.iter_rows(values_only=True)
            try:
                header_row = next(grid)
            except StopIteration:
                return [], []
            headers = [str(name or "").strip().lower() for name in header_row]
            rows = []
            for values in grid:
                row = {}
                for index, name in enumerate(headers):
                    if not name:
                        continue
                    value = values[index] if index < len(values) else None
                    row[name] = "" if value is None else str(value).strip()
                rows.append(row)
            return headers, rows
        finally:
            workbook.close()

    def form_valid(self, form):
        upload = form.cleaned_data["file"]
        update_existing = form.cleaned_data["update_existing"]
        try:
            if upload.name.lower().endswith(".xlsx"):
                headers, data_rows = self._read_xlsx(upload)
            else:
                headers, data_rows = self._read_csv(upload)
        except UnicodeDecodeError:
            form.add_error("file", "File is not valid UTF-8 text. Re-save it as CSV UTF-8, or upload the .xlsx instead.")
            return self.form_invalid(form)
        except Exception:
            form.add_error("file", "File could not be read. Check it is a real .xlsx workbook or a plain CSV.")
            return self.form_invalid(form)

        missing = [name for name in ("item_name", "item_class", "uom") if name not in headers]
        if missing:
            form.add_error("file", f"Missing required column(s): {', '.join(missing)}.")
            return self.form_invalid(form)

        created = updated = 0
        errors = []
        try:
            with transaction.atomic():
                for line_no, row in enumerate(data_rows, start=2):  # row 1 is the header
                    if not any(row.values()):
                        continue  # trailing blank line

                    item_class = self._lookup(InventoryClass, row.get("item_class"), ("title", "class_code"))
                    uom = self._lookup(UOM, row.get("uom"), ("title", "code"))
                    if not item_class:
                        errors.append(f"Row {line_no}: unknown item class '{row.get('item_class', '')}'.")
                        continue
                    if not uom and (row.get("uom") or "").strip():
                        errors.append(f"Row {line_no}: unknown UOM '{row.get('uom', '')}'.")
                        continue

                    existing = InventoryItem.objects.filter(item_name__iexact=row.get("item_name", "")).first()
                    if existing and not update_existing:
                        errors.append(f"Row {line_no}: '{existing.item_name}' already exists.")
                        continue

                    data = {
                        "item_name": row.get("item_name", ""),
                        "code": existing.code if existing else "",
                        "category": item_class.title,
                        "uom": uom.pk,
                        "item_bar_code": row.get("item_bar_code", ""),
                        "price": row.get("price") or "0",
                        "purchase_price": row.get("purchase_price") or "0",
                        "item_kind": INVENTORY_KIND_PRODUCT,
                        "status": STATUS_ACTIVE,
                        "imported": "L",
                        "inventory": "I",
                    }
                    item_form = InventoryItemForm(data, instance=existing)
                    if not item_form.is_valid():
                        detail = "; ".join(f"{field}: {msg[0]}" for field, msg in item_form.errors.items())
                        errors.append(f"Row {line_no}: {detail}")
                        continue

                    item = item_form.save(commit=False)
                    if not existing:
                        item.created_by = self.request.user
                    item.updated_by = self.request.user
                    item.save()
                    if existing:
                        updated += 1
                    else:
                        created += 1

                if errors:
                    raise _ImportRowError
        except _ImportRowError:
            context = self.get_context_data(form=form)
            context["row_errors"] = errors
            return self.render_to_response(context)

        messages.success(self.request, f"{created} item(s) created, {updated} updated.")
        return super().form_valid(form)


class _ImportRowError(Exception):
    """Internal: rolls the import transaction back when any row is rejected."""


class ItemImportSampleView(PagePermissionRequiredMixin, View):
    """A one-row template in the shape the importer expects.

    Defaults to .xlsx, since that is what most item lists are kept in;
    ``?format=csv`` hands back the same row as CSV.
    """

    page = "inventory.items"
    action = "add"

    @staticmethod
    def _sample_row():
        item_class = InventoryClass.objects.order_by("title").first()
        uom = UOM.objects.order_by("title").first()
        return [
            "Example Item",
            item_class.title if item_class else "Raw Material",
            uom.title if uom else "Each",
            "100.00",
            "80.00",
            "8901234567890",
        ]

    def get(self, request, *args, **kwargs):
        columns = list(InventoryItemImportForm.COLUMNS)
        if request.GET.get("format") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="item-import-sample.csv"'
            response.write("﻿")
            writer = csv.writer(response)
            writer.writerow(columns)
            writer.writerow(self._sample_row())
            return response

        from openpyxl import Workbook
        from openpyxl.styles import Font

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Items"
        sheet.append(columns)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.append(self._sample_row())
        for index, name in enumerate(columns, start=1):
            sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = max(len(name) + 4, 16)

        buffer = io.BytesIO()
        workbook.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="item-import-sample.xlsx"'
        return response


class ItemToggleStatusView(InventoryManageMixin, View):
    page = "inventory.items"
    action = "edit"
    def post(self, request, pk):
        record = get_object_or_404(InventoryItem, pk=pk)
        record.status = STATUS_INACTIVE if record.status == STATUS_ACTIVE else STATUS_ACTIVE
        record.updated_by = request.user
        record.save(update_fields=["status", "updated_by", "updated_at"])
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("inventory:item_list"))


class ItemNextCodeView(InventoryManageMixin, View):
    """The code the item form would assign under a typed category.

    A preview only: the number is settled again on save, so two operators
    filling the form at once still end up with different codes.
    """

    page = "inventory.items"

    def get(self, request, *args, **kwargs):
        title = (request.GET.get("category") or "").strip()
        item_class = InventoryClass.objects.filter(title__iexact=title).first() if title else None
        if item_class:
            prefix = (item_class.class_code or "ITM").upper()
        elif title:
            prefix = InventoryItemForm._next_class_code(title)
        else:
            prefix = "ITM"
        return JsonResponse({"prefix": prefix, "code": InventoryItem.next_code(prefix)})


class SupplierPurchaseOrderOptionsView(InventoryListMixin, View):
    """This supplier's open orders, as the purchase invoice screen needs them.

    Answers the picker rather than a page: the screen asks the moment a
    supplier is chosen, so the orders arrive without a reload. Only what is
    still to be billed is offered -- an order already invoiced in full has
    nothing left to copy onto a bill.
    """

    page = "inventory.purchase_orders"

    def get(self, request, *args, **kwargs):
        supplier_id = (request.GET.get("supplier") or "").strip()
        if not supplier_id.isdigit():
            return JsonResponse({"orders": []})

        rows = open_order_lines(supplier=Supplier.objects.filter(pk=int(supplier_id)).first())

        orders = {}
        for line in rows:
            order = line.purchase_order
            held = orders.setdefault(order.pk, {
                "id": order.pk,
                "number": order.purchase_num,
                "date": order.purchase_date.isoformat() if order.purchase_date else "",
                "date_text": order.purchase_date.strftime("%d-%m-%Y") if order.purchase_date else "",
                "status": order.get_status_display(),
                "quantity": Decimal("0.0000"),
                "value": Decimal("0.00"),
                "lines": [],
            })
            pending = line.qty_pending
            rate = line.rate or Decimal("0.00")
            amount = (pending * rate).quantize(TWO_DP)
            held["quantity"] += pending
            held["value"] += amount
            held["lines"].append({
                "order_item_id": line.pk,
                "kind": "product" if line.is_product_line else "item",
                "item_id": line.inventory_item_id,
                "product_id": line.product_id,
                "name": line.descr,
                "quantity": float(pending),
                "ordered": float(line.quantity or 0),
                "uom_id": line.uom_id or (line.inventory_item.uom_id if line.inventory_item else "") or "",
                "unit": line.uom.title if line.uom else (
                    line.inventory_item.uom.title
                    if line.inventory_item and line.inventory_item.uom else ""),
                "rate": float(rate),
                "amount": float(amount),
            })

        payload = [
            {**order, "quantity": float(order["quantity"]), "value": float(order["value"]),
             "items": len(order["lines"])}
            for order in sorted(orders.values(), key=lambda o: o["date"], reverse=True)
        ]
        return JsonResponse({"orders": payload})


class PurchaseInvoiceCreateView(InventoryManageMixin, View):
    """Enter a supplier's invoice, with or without an order behind it.

    One form: the party at the top, the goods in the middle, the money at the
    bottom. Which route in it is depends on the supplier -- one with open
    orders must be invoiced against one of them, one without is typed straight
    off the paperwork -- and both post through the same service, so there is
    one set of books either way.
    """

    page = "inventory.purchase_orders"
    action = "add"
    template_name = "inventory/purchase_invoice_form.html"

    def _context(self, **extra):
        items = (
            InventoryItem.objects
            .select_related("uom", "secondary_uom", "stock", "conversion__uom_from", "conversion__uom_to")
            .filter(status=STATUS_ACTIVE)
            .order_by("item_name")
        )
        context = {
            "title": "Purchase Invoice",
            "next_invoice_no": next_purchase_invoice_number(),
            "suppliers": self._suppliers_with_balance(),
            "layout": get_layout(FORM_PURCHASE_INVOICE),
            "extra_field_types": EXTRA_FIELD_TYPES,
            "settings_url": reverse_lazy("inventory:purchase_invoice_form_settings"),
            "can_edit": user_has_permission(self.request.user, f"{self.page}.edit"),
            "units": UOM.objects.order_by("title"),
            "godowns": godown_options(),
            "brokers": broker_options(),
            "wheat_products": wheat_product_options(),
            "bardana_products": bardana_product_options(),
            "bardana_ownership_choices": INV_BARDANA_OWNERSHIP_CHOICES,
            "today": timezone.localdate(),
            "items_json": json.dumps([
                {
                    "id": item.pk,
                    "name": item.item_name,
                    "code": item.code,
                    "uom": item.uom_id or "",
                    "rate": float(item.purchase_price or 0),
                    "stock": float(getattr(item.stock, "current_quantity", 0) or 0),
                    "stocked": item.item_kind == INVENTORY_KIND_PRODUCT,
                    "unit": uom_title(item),
                    "units": item_unit_options(item),
                }
                for item in items
            ]),
        }
        posted = extra.get("posted")
        prefill = extra.pop("prefill_lines", None)
        if prefill is not None:
            rows = prefill
        elif posted and hasattr(posted, "getlist"):
            rows = self._posted_lines(posted)
        else:
            rows = []
        context["posted_lines_json"] = json.dumps(rows)
        context.update(extra)
        return context

    @staticmethod
    def _suppliers_with_balance():
        """Active suppliers, each carrying what is currently owed to it.

        Hung on the object rather than passed as a second map, so the template
        prints it beside the name it belongs to without a lookup filter.
        """
        from apps.finance.services import supplier_payable_balances

        balances = supplier_payable_balances()
        rows = list(Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name"))
        for row in rows:
            row.balance = balances.get(row.pk, Decimal("0.00"))
        return rows

    @staticmethod
    def _posted_lines(posted):
        """The line grid as it was submitted, as plain dicts."""
        item_ids = posted.getlist("item_id")
        quantities = posted.getlist("quantity")
        rates = posted.getlist("rate")
        uom_ids = posted.getlist("line_uom")
        order_items = posted.getlist("row_order_item")

        def at(values, index):
            return values[index] if index < len(values) else ""

        rows = []
        for index, raw_id in enumerate(item_ids):
            row = {
                "item_id": (raw_id or "").strip(),
                "quantity": at(quantities, index),
                "rate": at(rates, index),
                "uom_id": at(uom_ids, index),
                "order_item_id": at(order_items, index),
            }
            if any(row.values()):
                rows.append(row)
        return rows

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(**self._from_order(request)))

    @staticmethod
    def _from_order(request):
        """Supplier and lines for an order named in the query string."""
        raw = (request.GET.get("order") or "").strip()
        if not raw.isdigit():
            return {}

        order = (
            PurchaseOrder.objects.filter(pk=int(raw))
            .select_related("supplier").first()
        )
        if order is None:
            return {}

        lines = open_order_lines(purchase_order=order)
        if not lines:
            messages.info(
                request,
                f"{order.purchase_num} has nothing left to invoice. "
                f"Enter this invoice against another order, or without one.",
            )
            return {"posted": {"supplier": str(order.supplier_id)}}

        return {
            "posted": {"supplier": str(order.supplier_id)},
            "prefill_lines": [
                {
                    "item_id": str(line.inventory_item_id),
                    "quantity": f"{line.qty_pending.normalize():f}",
                    "rate": f"{(line.rate or Decimal('0')):.2f}",
                    "uom_id": str(line.uom_id or line.inventory_item.uom_id or ""),
                    "order_item_id": str(line.pk),
                }
                for line in lines if line.inventory_item_id
            ],
        }

    def post(self, request, *args, **kwargs):
        posted = request.POST
        supplier_id = (posted.get("supplier") or "").strip()
        supplier = Supplier.objects.filter(pk=supplier_id).first() if supplier_id.isdigit() else None

        def decimal_of(raw, default="0"):
            text = (raw or "").strip().replace(",", "") or default
            return Decimal(text)

        def money(name, default="0"):
            try:
                return decimal_of(posted.get(name), default)
            except (InvalidOperation, ValueError):
                raise ValidationError(f"{name.replace('_', ' ').title()} must be a number.")

        lines = []
        item_ids = posted.getlist("item_id")
        quantities = posted.getlist("quantity")
        rates = posted.getlist("rate")
        uom_ids = posted.getlist("line_uom")
        order_item_ids = posted.getlist("row_order_item")
        for index, raw_id in enumerate(item_ids):
            if not (raw_id or "").strip().isdigit():
                continue
            item = InventoryItem.objects.filter(pk=raw_id).first()
            if not item:
                continue
            try:
                quantity = decimal_of(quantities[index] if index < len(quantities) else "")
                rate = decimal_of(rates[index] if index < len(rates) else "")
            except (InvalidOperation, ValueError):
                messages.error(request, f"Check the quantity and price on the {item.item_name} line.")
                return render(request, self.template_name, self._context(posted=posted))
            if quantity > 0:
                raw_uom = (uom_ids[index] if index < len(uom_ids) else "") or ""
                uom = UOM.objects.filter(pk=raw_uom).first() if raw_uom.strip().isdigit() else None
                lines.append({"inventory_item": item, "quantity": quantity, "rate": rate, "uom": uom})

        def weight_at(name, index):
            values = posted.getlist(name)
            raw = (values[index] if index < len(values) else "").strip().replace(",", "")
            return raw or None

        def order_line_at(name, index):
            values = posted.getlist(name)
            raw = (values[index] if index < len(values) else "").strip()
            return int(raw) if raw.isdigit() else None

        product_order_items = {
            row.pk: row for row in open_order_lines(supplier=supplier) if row.product_id
        }

        wheat_products = {
            product.pk: product for product in wheat_product_options()
        }
        for index, raw_id in enumerate(posted.getlist("wheat_product")):
            if not (raw_id or "").strip().isdigit():
                continue
            product = wheat_products.get(int(raw_id))
            if not product:
                continue
            selected = weight_at("wheat_selected_weight", index)
            if selected is None:
                continue
            lines.append({
                "product": product,
                "order_item": product_order_items.get(order_line_at("wheat_order_item", index)),
                "party_weight": weight_at("wheat_party_weight", index),
                "mill_weight": weight_at("wheat_mill_weight", index),
                "selected_weight": selected,
                "katla": weight_at("wheat_katla", index),
                "khoot": weight_at("wheat_khoot", index),
                "moisture": weight_at("wheat_moisture", index),
                "sack_weight_deduction": weight_at("wheat_sack_deduction", index),
                "rate_per_mund": weight_at("wheat_rate_per_mund", index),
            })

        bardana_products = {
            product.pk: product for product in bardana_product_options()
        }
        ownership_codes = dict(INV_BARDANA_OWNERSHIP_CHOICES)
        for index, raw_id in enumerate(posted.getlist("bardana_product")):
            if not (raw_id or "").strip().isdigit():
                continue
            product = bardana_products.get(int(raw_id))
            if not product:
                continue
            quantity = weight_at("bardana_qty", index)
            if quantity is None:
                continue
            ownership = (posted.getlist("bardana_ownership")[index]
                         if index < len(posted.getlist("bardana_ownership")) else "").strip()
            if ownership not in ownership_codes:
                messages.error(request, f"Say whose sacks the {product.name} line is.")
                return render(request, self.template_name, self._context(posted=posted))
            lines.append({
                "product": product,
                "order_item": product_order_items.get(order_line_at("bardana_order_item", index)),
                "quantity": quantity,
                "rate": weight_at("bardana_rate", index) or "0",
                "bardana_ownership": ownership,
                "bag_weight": weight_at("bardana_bag_weight", index),
            })

        invoice_date = posted.get("bill_date") or str(timezone.localdate())

        picked_order_lines = {
            index: int(pk) for index, pk in enumerate(order_item_ids)
            if (pk or "").strip().isdigit()
        }
        only_products = lines and all(line.get("product") for line in lines)
        open_product_ids = {
            row.product_id for row in open_order_lines(supplier=supplier) if row.product_id
        }
        invoice_product_ids = {line["product"].pk for line in lines if line.get("product")}
        if only_products and not (open_product_ids & invoice_product_ids):
            pass
        elif not picked_order_lines and supplier_has_open_orders(supplier=supplier):
            messages.error(
                request,
                f"{supplier.name} has open purchase orders. Pick the order this invoice "
                f"covers, or close the order first if the goods are never coming.",
            )
            return render(request, self.template_name, self._context(posted=posted))

        order_items = {
            item.pk: item
            for item in PurchaseOrderItem.objects.filter(
                pk__in=list(picked_order_lines.values())
            ).select_related("purchase_order", "inventory_item")
        }
        for index, order_item_pk in picked_order_lines.items():
            order_item = order_items.get(order_item_pk)
            if not order_item:
                messages.error(request, "One of the purchase order lines no longer exists.")
                return render(request, self.template_name, self._context(posted=posted))
            if index < len(lines):
                lines[index]["order_item"] = order_item
                if not lines[index].get("rate"):
                    lines[index]["rate"] = order_item.rate

        layout = get_layout(FORM_PURCHASE_INVOICE)
        extra_values, extra_error = read_extra_values(posted, layout)
        if extra_error:
            messages.error(request, extra_error)
            return render(request, self.template_name, self._context(posted=posted))

        try:
            invoice = create_purchase_invoice(
                supplier=supplier,
                supplier_invoice_num=(posted.get("bill_number") or "").strip(),
                supplier_invoice_date=invoice_date,
                invoice_date=invoice_date,
                due_date=(posted.get("due_date") or "").strip() or None,
                godown=picked(posted, "godown", godown_options()),
                vehicle_no=(posted.get("vehicle_no") or "").strip(),
                broker=picked(posted, "broker", broker_options()),
                brokerage_rate_per_100kg=money("brokerage_rate_per_100kg"),
                withholding_rate_per_40kg=money("withholding_rate_per_40kg"),
                extra_data=extra_values,
                lines=lines,
                discount_amount=money("discount_amount"),
                freight_amount=money("freight_amount"),
                tax_amount=money("tax_amount"),
                paid_amount=money("paid_amount"),
                remarks=(posted.get("remarks") or "").strip(),
                user=request.user,
            )
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
            return render(request, self.template_name, self._context(posted=posted))

        messages.success(
            request,
            f"Purchase invoice {invoice.invoice_num} posted for {invoice.total_amount}. "
            f"Stock taken in, payable created.",
        )
        for row in getattr(invoice, "over_invoiced", []):
            messages.warning(
                request,
                f"{row['item']} on {row['order_num']} line {row['seq_num']}: "
                f"{row['excess']} more than the {row['ordered_balance']} still on order. "
                f"Taken in and paid for. Tell the buyer if this was not agreed.",
            )
        if "save_and_new" in posted:
            return redirect("inventory:purchase_invoice_create")
        return redirect("inventory:purchase_invoice_detail", pk=invoice.pk)


class ItemConversionOptionsView(InventoryManageMixin, View):
    """The rates already on file between two units.

    The item form offers these as a pick list rather than asking the operator
    to retype a figure the units screen already holds.
    """

    page = "inventory.items"
    action = "add"

    def get(self, request, *args, **kwargs):
        base = request.GET.get("base") or ""
        secondary = request.GET.get("secondary") or ""
        if not base or not secondary:
            return JsonResponse({"options": []})

        rows = UOMConversion.objects.filter(uom_from_id=base, uom_to_id=secondary).select_related("uom_from", "uom_to")
        return JsonResponse({
            "options": [
                {
                    "id": row.pk,
                    "factor": f"{row.conversion_factor.normalize():f}",
                    "base": row.uom_from.title,
                    "secondary": row.uom_to.title,
                }
                for row in rows
            ]
        })


class ItemCreateView(EmbeddedCreateMixin, InventoryManageMixin, CreateView):
    page = "inventory.items"
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/item_form.html"
    success_url = reverse_lazy("inventory:item_list")
    success_message = "Item saved."
    embed_message_type = "item:saved"
    other_fields = ("item_bar_code", "imported", "inventory", "status")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Inventory Item"
        context["other_fields"] = list(self.other_fields)
        context["product_value"] = INVENTORY_KIND_PRODUCT
        context["service_value"] = INVENTORY_KIND_SERVICE
        return context

    def embed_payload(self, obj):
        stock = getattr(obj, "stock", None)
        return {
            "id": obj.pk,
            "name": obj.item_name,
            "code": obj.code,
            "uom": obj.uom_id or "",
            "rate": float(obj.purchase_price or 0),
            "stock": float(getattr(stock, "current_quantity", 0) or 0),
            "stocked": obj.item_kind == INVENTORY_KIND_PRODUCT,
            "unit": uom_title(obj),
            "units": item_unit_options(obj),
        }

    def form_valid(self, form):
        response = super().form_valid(form)
        quantity = form.cleaned_data.get("opening_quantity")
        if quantity:
            set_opening_stock(
                inventory_item=self.object,
                quantity=quantity,
                price=form.cleaned_data.get("opening_price"),
                opening_date=form.cleaned_data.get("opening_date"),
                user=self.request.user,
            )
        if self.is_embedded():
            return self.embed_saved_response()
        return response

    def get_success_url(self):
        if "save_and_new" in self.request.POST:
            return reverse_lazy("inventory:item_create")
        return reverse_lazy("inventory:item_update", kwargs={"pk": self.object.pk})


class ItemUpdateView(ItemCreateView, UpdateView):
    success_message = "Item updated."


class LedgerListView(InventoryListMixin, ListView):
    page = "inventory.item_ledger"
    template_name = "inventory/ledger_list.html"
    context_object_name = "ledgers"
    queryset = ItemLedger.objects.select_related("inventory_item").order_by("-transaction_date", "-id")
    search_fields = ("transaction_id", "transaction_no", "item_code", "item_name", "ref_no", "transaction_type", "transaction_date", "old_quantity", "quantity", "new_quantity")
    filter_fields = {"item": "inventory_item_id", "type": "transaction_type"}
    date_filters = [{"field": "transaction_date", "label": "Transaction date"}]

    def get_filter_specs(self):
        item_choices = list(InventoryItem.objects.order_by("item_name").values_list("id", "item_name"))
        return [
            {"name": "type", "label": "All types", "choices": INV_TRANSACTION_TYPE_CHOICES, "value": self.request.GET.get("type", "")},
            {"name": "item", "label": "All items", "choices": item_choices, "value": self.request.GET.get("item", "")},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = list(context["ledgers"])

        sale_ids = [r.ref_id for r in rows if r.ref_table == "inv_pos_details"]
        sale_map = dict(POSDetail.objects.filter(pk__in=sale_ids).values_list("pk", "pos_master_id"))
        invoice_ids = {r.ref_id for r in rows if r.ref_table == "inv_purchase_invoices"}
        live_invoices = set(
            PurchaseInvoice.objects.filter(pk__in=invoice_ids).values_list("pk", flat=True)
        )

        for row in rows:
            url = None
            if row.ref_table == "inv_manual_transaction" and row.transaction_id:
                url = reverse_lazy("inventory:manual_transaction_print", kwargs={"tx_id": row.transaction_id})
            elif row.ref_table == "inv_purchase_invoices" and row.ref_id in live_invoices:
                url = reverse_lazy("inventory:purchase_invoice_detail", kwargs={"pk": row.ref_id})
            elif row.ref_table == "inv_pos_details" and row.ref_id in sale_map:
                url = reverse_lazy("inventory:pos_receipt", kwargs={"pk": sale_map[row.ref_id]})
            row.ref_url = url
        return context


class CustomerLedgerListView(InventoryListMixin, ListView):
    page = "inventory.customer_ledger"
    template_name = "inventory/customer_ledger_list.html"
    context_object_name = "ledgers"
    queryset = CustomerLedger.objects.select_related("customer").order_by("-transaction_date", "-id")
    search_fields = ("transaction_no", "customer__customer_name", "customer__customer_code")
    filter_fields = {"customer": "customer_id"}
    date_filters = [{"field": "transaction_date", "label": "Transaction date"}]

    def get_filter_specs(self):
        customer_choices = list(Customer.objects.order_by("customer_name").values_list("id", "customer_name"))
        return [{"name": "customer", "label": "All customers", "choices": customer_choices, "value": self.request.GET.get("customer", "")}]


class LedgerPrintView(PrintContextMixin, InventoryListMixin, ListView):
    page = "inventory.item_ledger"
    action = "view"
    template_name = "inventory/ledger_print.html"
    context_object_name = "ledgers"
    queryset = ItemLedger.objects.select_related("inventory_item").order_by("-transaction_date", "-id")
    search_fields = ("transaction_id", "transaction_no", "item_code", "item_name", "ref_no")
    paginate_by = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["print_back_url"] = reverse_lazy("inventory:ledger_list")
        return context


class PurchaseOrderQuickCreateView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "add"
    def post(self, request):
        item_ids = request.POST.getlist("item_id")
        qtys = request.POST.getlist("qty")
        rates = request.POST.getlist("rate")
        discounts = request.POST.getlist("discount")

        lines = []
        for i, item_id in enumerate(item_ids):
            if not item_id:
                continue
            qty = Decimal(int(float(qtys[i] or "0")))
            if qty <= 0:
                continue
            lines.append((int(item_id), qty, Decimal(rates[i] or "0").quantize(Decimal("0.01")), Decimal(discounts[i] or "0").quantize(Decimal("0.01"))))

        form = PurchaseOrderForm(request.POST)
        if not form.is_valid():
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return redirect("inventory:purchase_order_board")

        if not lines:
            messages.error(request, "Add at least one item before saving.")
            return redirect("inventory:purchase_order_board")

        with transaction.atomic():
            order = form.save(commit=False)
            order.status = STATUS_DRAFT
            order.created_by = request.user
            order.updated_by = request.user
            order.save()
            for item_id, qty, rate, discount in lines:
                inv_item = InventoryItem.objects.get(pk=item_id)
                PurchaseOrderItem.objects.create(
                    purchase_order=order,
                    inventory_item=inv_item,
                    uom=inv_item.uom,
                    quantity=qty,
                    rate=rate,
                    discount_amount=discount,
                    created_by=request.user,
                    updated_by=request.user,
                )

        messages.success(request, f"Purchase order {order.purchase_num} created with {len(lines)} item(s).")
        return redirect(f"{reverse_lazy('inventory:purchase_order_board')}?open={order.pk}")


class PurchaseOrderDraftInitView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "add"
    """AJAX: create draft PO header, return pk."""
    def post(self, request):
        from django.http import JsonResponse
        form = PurchaseOrderForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"error": str(form.errors)}, status=400)
        order = form.save(commit=False)
        order.status = STATUS_DRAFT
        order.created_by = request.user
        order.updated_by = request.user
        order.save()
        return JsonResponse({"pk": order.pk, "purchase_num": order.purchase_num})


class PurchaseOrderDraftFinalizeView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "add"
    """Add items to existing draft PO and raise it."""
    def post(self, request):
        draft_pk = request.POST.get("draft_pk")
        order = get_object_or_404(PurchaseOrder, pk=draft_pk, status=STATUS_DRAFT)

        item_ids = request.POST.getlist("item_id")
        qtys = request.POST.getlist("qty")
        rates = request.POST.getlist("rate")
        discounts = request.POST.getlist("discount")

        lines = []
        for i, item_id in enumerate(item_ids):
            if not item_id:
                continue
            qty = Decimal(int(float(qtys[i] or "0")))
            if qty <= 0:
                continue
            lines.append((int(item_id), qty, Decimal(rates[i] or "0").quantize(Decimal("0.01")), Decimal(discounts[i] or "0").quantize(Decimal("0.01"))))

        if not lines:
            messages.error(request, "Add at least one item before saving.")
            return redirect("inventory:purchase_order_board")

        with transaction.atomic():
            for item_id, qty, rate, discount in lines:
                inv_item = InventoryItem.objects.get(pk=item_id)
                PurchaseOrderItem.objects.create(
                    purchase_order=order,
                    inventory_item=inv_item,
                    uom=inv_item.uom,
                    quantity=qty,
                    rate=rate,
                    discount_amount=discount,
                    created_by=request.user,
                    updated_by=request.user,
                )
            order.status = STATUS_SUBMITTED
            order.updated_by = request.user
            order.save(update_fields=["status", "updated_by", "updated_at"])

        messages.success(request, f"Purchase order {order.purchase_num} raised with {len(lines)} item(s).")
        return redirect("inventory:purchase_order_print", pk=order.pk)


class PurchaseOrderRaiseView(InventoryManageMixin, View):
    """Release a draft order to the supplier.

    Guarded by ``edit`` and not by ``approve``, because most orders are within
    the buyer's own limit and releasing those is ordinary work. The service
    decides whether this particular order needed a second signature, which is
    the only place that can be decided -- it depends on the amount.
    """

    page = "inventory.purchase_orders"
    action = "edit"

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            approve_purchase_order(order=order, user=request.user)
            messages.success(request, f"{order.purchase_num} approved and released to the supplier.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect(f"{reverse_lazy('inventory:purchase_order_board')}?open={order.pk}")


class PurchaseOrderCancelView(InventoryManageMixin, View):
    """Abandon an order nothing has arrived against.

    Not a delete: the number stays in the sequence and the reason stays on the
    record, so a cancelled order can be told apart from one that never existed.
    """

    page = "inventory.purchase_orders"
    action = "approve"

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        form = PurchaseOrderCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Pick a reason for cancelling this order.")
            return redirect("inventory:purchase_order_detail", pk=pk)
        try:
            cancel_purchase_order(order=order, reason=form.cleaned_data["reason"],
                                  remarks=form.cleaned_data["remarks"], user=request.user)
            messages.success(request, f"{order.purchase_num} cancelled. The number stays in the sequence.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("inventory:purchase_order_detail", pk=pk)


class PurchaseOrderCloseShortView(InventoryManageMixin, View):
    """Give up on the balance of a part-delivered order.

    Creates no accounting entry -- an order never had one. What it releases is
    the commitment, so the outstanding quantity stops counting as goods on
    order and stops propping up a reorder decision that will never be met.
    """

    page = "inventory.purchase_orders"
    action = "approve"

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        form = PurchaseOrderCloseShortForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Pick a reason for closing this order short.")
            return redirect("inventory:purchase_order_detail", pk=pk)
        try:
            closed = close_purchase_order_short(order=order, reason=form.cleaned_data["reason"],
                                                remarks=form.cleaned_data["remarks"], user=request.user)
            messages.success(
                request,
                f"{closed.purchase_num} closed — {closed.short_qty} units "
                f"({closed.short_value}) released from what is on order.",
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("inventory:purchase_order_detail", pk=pk)


class PurchaseOrderReopenView(InventoryManageMixin, View):
    """Expect the balance again, because the goods turned up after all."""

    page = "inventory.purchase_orders"
    action = "approve"

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            reopen_purchase_order(order=order, user=request.user)
            messages.success(request, f"{order.purchase_num} re-opened — the balance is expected again.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("inventory:purchase_order_detail", pk=pk)


class PurchaseApprovalLimitView(InventoryManageMixin, View):
    """Set what a buyer may commit without a second signature."""

    page = "inventory.purchase_orders"
    action = "approve"

    def post(self, request):
        form = PurchaseApprovalLimitForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a valid approval limit.")
        else:
            try:
                limit = set_purchase_order_approval_limit(form.cleaned_data["amount"], user=request.user)
                messages.success(request, f"Approval limit set to {limit}. It applies to orders raised from now on.")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        return redirect("inventory:purchase_order_board")


class PurchaseInvoiceListView(SortableListMixin, InventoryListMixin, ListView):
    """Every purchase. The invoice is the only financial document on this side.

    Read the same way as the purchase orders board, because it answers the same
    kind of question about the same trade -- but from the other end. An order is
    a thing still owed; an invoice is one that landed, took the goods in and
    booked what is owed for them, all at once.

    Whether an order was raised first is a column on the row, not a separate
    board: it changes where the lines were copied from and nothing else.
    """

    page = "inventory.purchase_orders"
    template_name = "inventory/purchase_invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 25
    queryset = (
        PurchaseInvoice.objects
        .select_related("supplier", "created_by", "purchase_order", "godown")
        .prefetch_related("items__inventory_item", "items__uom")
        .order_by("-invoice_date", "-id")
    )
    search_fields = ("invoice_num", "supplier__name", "supplier_invoice_num", "remarks",
                     "legacy_bill_no", "vehicle_no")
    filter_fields = {"supplier": "supplier_id", "godown": "godown_id"}
    date_filters = [{"field": "invoice_date", "label": "Invoice date"}]
    sort_fields = {
        "invoice_num": "seq_num",
        "invoice_date": ("invoice_date", "id"),
        "supplier": "supplier__name",
        "total_amount": ("total_amount", "id"),
    }
    default_sort = "invoice_date"
    default_sort_dir = "desc"

    PER_PAGE_OPTIONS = (10, 25, 50, 100)

    def get_paginate_by(self, queryset):
        raw = (self.request.GET.get("per_page") or "").strip()
        if raw.isdigit() and int(raw) in self.PER_PAGE_OPTIONS:
            return int(raw)
        return self.paginate_by

    def get_filter_specs(self):
        supplier_choices = list(
            Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("id", "name")
        )
        return [
            {"name": "supplier", "label": "All suppliers", "short_label": "Supplier",
             "choices": supplier_choices, "value": self.request.GET.get("supplier", "")},
            {"name": "godown", "label": "All godowns", "short_label": "Godown",
             "choices": list(godown_options().values_list("id", "name")),
             "value": self.request.GET.get("godown", "")},
        ]

    def get_queryset(self):
        queryset = super().get_queryset()
        state = (self.request.GET.get("state") or "").strip()
        if state == "reversed":
            queryset = queryset.filter(status=STATUS_REVERSED)
        elif state == "posted":
            queryset = queryset.filter(status=STATUS_POSTED)
        elif state == "against_order":
            queryset = queryset.filter(purchase_order__isnull=False)
        elif state == "direct":
            queryset = queryset.filter(purchase_order__isnull=True)
        return queryset

    def tiles(self):
        """The figures over everything the filters allow, not just this page.

        Counted over the filtered set rather than the page, because "how much
        did we buy" is a question about the whole of it, and the totals are
        read off the invoice header rather than re-added from the lines: the
        header is what posted to the ledger, so it is the figure that is true.
        """
        rows = list(
            super(PurchaseInvoiceListView, self).get_queryset().select_related("supplier")
        )
        today = timezone.localdate()
        value = Decimal("0.00")
        month_value = Decimal("0.00")
        month_count = 0
        unpaid_count = 0
        unpaid_value = Decimal("0.00")
        suppliers = set()
        for row in rows:
            if row.status == STATUS_REVERSED:
                continue
            total = row.total_amount or Decimal("0.00")
            value += total
            suppliers.add(row.supplier_id)
            if row.invoice_date and (row.invoice_date.year, row.invoice_date.month) == (today.year, today.month):
                month_count += 1
                month_value += total
            outstanding = row.balance_amount
            if outstanding > Decimal("0.00"):
                unpaid_count += 1
                unpaid_value += outstanding
        month_start = today.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        return {
            "count": len([r for r in rows if r.status != STATUS_REVERSED]),
            "value": value,
            "month_count": month_count,
            "month_value": month_value,
            "month_from": month_start.isoformat(),
            "month_to": (next_month - timedelta(days=1)).isoformat(),
            "supplier_count": len(suppliers),
            "unpaid_count": unpaid_count,
            "unpaid_value": unpaid_value,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        carried = self.request.GET.copy()
        for key in ("tab", "page"):
            carried.pop(key, None)
        context["base_query"] = carried.urlencode()
        context["per_page"] = self.get_paginate_by(None)
        context["per_page_options"] = list(self.PER_PAGE_OPTIONS)
        context["filters_active"] = any(
            (self.request.GET.get(key) or "").strip()
            for key in ("q", "supplier", "date_from", "date_to", "state")
        )
        context["state"] = (self.request.GET.get("state") or "").strip()
        kept = self.request.GET.copy()
        for key in ("page", "state", "date_from", "date_to"):
            kept.pop(key, None)
        context["tile_query"] = kept.urlencode()
        context["tiles"] = self.tiles()
        context["export_url"] = reverse_lazy("inventory:purchase_invoice_export")
        page_total = Decimal("0.00")
        for invoice in context["invoices"]:
            lines = list(invoice.items.all())
            invoice.line_count = len(lines)
            invoice.qty_total = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
            page_total += invoice.total_amount or Decimal("0.00")
        context["page_total"] = page_total
        context["invoice_count"] = context["paginator"].count if context.get("paginator") else len(context["invoices"])
        return context


class PurchaseInvoiceDetailView(InventoryListMixin, DetailView):
    """One purchase invoice, read as the paper it stands for.

    Who it is from, what was bought, what it came to, and what it did to the
    books. Nothing on it is still owed in goods: the invoice is what took them
    in, so the page states what it created rather than what it is waiting on.
    The one thing that can still be outstanding is the money.
    """

    page = "inventory.purchase_orders"
    model = PurchaseInvoice
    template_name = "inventory/purchase_invoice_detail.html"
    context_object_name = "invoice"
    queryset = (
        PurchaseInvoice.objects
        .select_related("supplier", "created_by", "posted_by", "purchase_order")
        .prefetch_related("items__inventory_item", "items__uom",
                          "items__purchase_order_item__purchase_order")
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = self.object
        lines = list(invoice.items.all())
        context["lines"] = lines
        context["goods_total"] = sum((line.amount or Decimal("0.00") for line in lines), Decimal("0.00"))
        context["qty_total"] = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))

        orders = {}
        for line in lines:
            order_item = line.purchase_order_item
            if order_item is not None:
                orders[order_item.purchase_order_id] = order_item.purchase_order
        context["source_orders"] = sorted(orders.values(), key=lambda o: o.purchase_num)
        context["is_direct"] = not orders

        context["can_reverse"], context["reverse_blocked_reason"] = can_reverse_invoice(invoice)
        context["reversal_reasons"] = INV_REVERSAL_REASONS
        context["invoices_url"] = reverse_lazy("inventory:purchase_invoice_list")
        return context


class PurchaseInvoiceReverseView(InventoryManageMixin, View):
    """Withdraw a posted invoice: stock back out, payable cancelled."""

    page = "inventory.purchase_orders"
    action = "delete"

    def post(self, request, pk, *args, **kwargs):
        invoice = get_object_or_404(PurchaseInvoice, pk=pk)
        try:
            reverse_purchase_invoice(
                invoice=invoice,
                reason=(request.POST.get("reason") or "").strip(),
                user=request.user,
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, f"{invoice.invoice_num} reversed.")
        return redirect("inventory:purchase_invoice_detail", pk=invoice.pk)


class PurchaseInvoiceExportView(InventoryListMixin, TableExportView):
    """The purchase invoice rows on screen, in whichever format was asked for."""

    page = "inventory.purchase_orders"
    columns = PURCHASE_INVOICE_COLUMNS
    filename = "purchase-invoices"
    title = "Purchase Invoices"

    def get_rows(self):
        listing = PurchaseInvoiceListView(request=self.request, kwargs={}, args=())
        rows = list(listing.get_queryset())
        for row in rows:
            lines = list(row.items.all())
            row.line_count = len(lines)
            row.qty_total = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
        return rows


class PurchaseOrderListView(SortableListMixin, InventoryListMixin, ListView):
    """Orders raised on suppliers: what is committed, and what it is waiting on.

    The screen is built around the question an order actually poses -- is it
    approved, has it arrived, has it been billed, is it late -- rather than
    around the row in the table. The tabs sort orders by which of those they are
    stuck on, and the tiles across the top count the same thing the rows below
    show, because both are read from one decorated set.
    """

    page = "inventory.purchase_orders"
    template_name = "inventory/purchase_order_list.html"
    context_object_name = "orders"
    paginate_by = 25
    queryset = (
        PurchaseOrder.objects
        .select_related("supplier", "created_by", "godown")
        .prefetch_related("items__uom", "items__inventory_item", "invoices",
                          "items__invoice_lines__invoice")
        .order_by("-purchase_date", "-id")
    )
    search_fields = ("purchase_num", "supplier__name", "quot_num", "descr")
    filter_fields = {"supplier": "supplier_id", "godown": "godown_id"}
    date_filters = [{"field": "purchase_date", "label": "Order date"}]
    sort_fields = {
        "purchase_num": "seq_num",
        "purchase_date": ("purchase_date", "id"),
        "supplier": "supplier__name",
        "expected": "expected_date",
        "status": "status",
    }
    default_sort = "purchase_date"
    default_sort_dir = "desc"

    PER_PAGE_OPTIONS = (10, 25, 50, 100)

    def current_tab(self):
        tab = self.request.GET.get("tab", TAB_ALL)
        return tab if tab in dict(TABS) else TAB_ALL

    def get_paginate_by(self, queryset):
        raw = (self.request.GET.get("per_page") or "").strip()
        if raw.isdigit() and int(raw) in self.PER_PAGE_OPTIONS:
            return int(raw)
        return self.paginate_by

    def filtered_queryset(self):
        """Everything the filter bar allows, before the tab narrows it.

        The tiles are counted over this: switching to one tab should not make
        the numbers above it change, because they are what the tabs are for.
        """
        return super().get_queryset().distinct()

    def get_queryset(self):
        queryset = self.filtered_queryset()
        tab = self.current_tab()
        statuses = TAB_STATUSES.get(tab)
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        return queryset

    def get_filter_specs(self):
        supplier_choices = list(
            Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("id", "name")
        )
        return [
            {"name": "supplier", "label": "All suppliers", "choices": supplier_choices,
             "value": self.request.GET.get("supplier", "")},
            {"name": "godown", "label": "All godowns", "choices": list(godown_options().values_list("id", "name")),
             "value": self.request.GET.get("godown", "")},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = list(context["orders"])
        decorate(orders)
        context["orders"] = orders
        context["page_total"] = sum((order.total_amount for order in orders), Decimal("0.00"))
        context["order_count"] = context["paginator"].count if context.get("paginator") else len(orders)

        everything = list(self.filtered_queryset())
        context["tiles"] = summarise(everything)
        def tab_count(key):
            statuses = TAB_STATUSES.get(key)
            return sum(1 for order in everything
                       if not statuses or order.status in statuses)

        context["tabs"] = [
            {"key": key, "label": label, "on": key == self.current_tab(), "count": tab_count(key)}
            for key, label in TABS
        ]
        context["approval_lines"] = {
            order.pk: [
                {
                    "name": line.descr,
                    "qty": f"{line.quantity.normalize():f}" if line.quantity else "0",
                    "uom": line.uom.title if line.uom_id else "",
                    "rate": float(line.rate or 0),
                    "amount": float(line.total_amount or 0),
                }
                for line in order.items.all()
            ]
            for order in orders if order.status == STATUS_DRAFT
        }
        context["columns"] = visible_columns(self.request.session)
        context["column_menu"] = column_menu(self.request.session)
        shown = [column.key for column in COLUMNS.columns if column.key in context["columns"]]
        span = len(shown) + 2
        context["column_span"] = span
        if "value" in shown:
            context["foot_lead_span"] = shown.index("value") + 1
            context["foot_tail_span"] = span - shown.index("value") - 2
        else:
            context["foot_lead_span"] = span
            context["foot_tail_span"] = 0
        context["approval_limit"] = purchase_order_approval_limit()
        context["approval_limit"] = purchase_order_approval_limit()
        context["current_tab"] = self.current_tab()
        carried = self.request.GET.copy()
        for key in ("tab", "page"):
            carried.pop(key, None)
        context["base_query"] = carried.urlencode()
        context["per_page"] = self.get_paginate_by(None)
        context["per_page_options"] = list(self.PER_PAGE_OPTIONS)
        context["export_url"] = reverse_lazy("inventory:purchase_order_export")
        context["columns_url"] = reverse_lazy("inventory:purchase_order_columns")
        context["filters_active"] = any(
            (self.request.GET.get(key) or "").strip()
            for key in ("q", "supplier", "date_from", "date_to", "sort", "dir")
        ) or self.current_tab() != TAB_ALL
        return context


class PurchaseOrderExportView(InventoryListMixin, TableExportView):
    """The orders on screen, in whichever format was asked for.

    Same filters and same columns as the list whatever the format, so the file
    needs no explaining and the two can never drift apart.
    """

    page = "inventory.purchase_orders"
    columns = COLUMNS
    filename = "purchase-orders"
    title = "Purchase Orders"

    def get_rows(self):
        listing = PurchaseOrderListView(request=self.request, kwargs={}, args=())
        return decorate(list(listing.get_queryset()))


class PurchaseOrderColumnsView(InventoryListMixin, View):
    """Which columns this person wants on the purchase orders table.

    Kept in the session, not the database: a column choice is how one operator
    likes to look at the screen, and it should not change what anybody else
    sees. Only the index permission is needed, because choosing what to look at
    is not a change to anything.
    """

    page = "inventory.purchase_orders"

    def post(self, request, *args, **kwargs):
        set_visible_columns(request.session, request.POST.getlist("columns"))
        carried = request.POST.get("back", "")
        query = urlencode([
            (key, value) for key, value in parse_qsl(carried, keep_blank_values=False)
            if key in ("q", "tab", "supplier", "date_from", "date_to", "per_page", "page")
        ])
        target = reverse_lazy("inventory:purchase_order_board")
        return redirect(f"{target}?{query}" if query else str(target))


class PurchaseReportView(InventoryListMixin, ListView):
    page = "inventory.purchase_report"
    template_name = "inventory/purchase_report.html"
    context_object_name = "orders"
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items").order_by("-purchase_date", "-id")
    search_fields = ("purchase_num", "supplier__name", "quot_num")
    filter_fields = {"status": "status", "supplier": "supplier_id", "item": "items__inventory_item_id"}
    date_filters = [{"field": "purchase_date", "label": "Purchase date"}]

    def get_queryset(self):
        return super().get_queryset().distinct()

    def get_filter_specs(self):
        supplier_choices = list(Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("id", "name"))
        item_choices = list(InventoryItem.objects.filter(status=STATUS_ACTIVE).order_by("item_name").values_list("id", "item_name"))
        return [
            {"name": "status", "label": "All statuses", "choices": INV_PURCHASE_ORDER_STATUS_CHOICES, "value": self.request.GET.get("status", "")},
            {"name": "supplier", "label": "All suppliers", "choices": supplier_choices, "value": self.request.GET.get("supplier", "")},
            {"name": "item", "label": "All items", "choices": item_choices, "value": self.request.GET.get("item", "")},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for order in context["orders"]:
            items = list(order.items.all())
            order.po_total = sum(i.total_amount for i in items)
        return context


class PendingOrdersReportView(InventoryListMixin, ListView):
    """What is still to come in, by supplier. The owner's morning question.

    Only orders that are live: raised, or part invoiced with a balance still
    owed. A draft has been committed to nobody and a closed or cancelled order
    is not expected, so neither is anything still to come.

    The balance is read off the order lines, which carry ``qty_invoiced``, so
    the figure is the same one the order screen shows rather than a second
    calculation that could disagree with it. A line closed short counts as
    nothing outstanding without pretending it arrived -- that is what closing
    short means, and it is why the report can be trusted as a commitment list.
    """

    page = "inventory.purchase_report"
    template_name = "inventory/pending_orders_report.html"
    context_object_name = "orders"
    paginate_by = 25
    queryset = (
        PurchaseOrder.objects
        .filter(status__in=[STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED])
        .select_related("supplier", "godown")
        .prefetch_related("items__inventory_item", "items__uom")
        .order_by("supplier__name", "purchase_date", "id")
    )
    search_fields = ("purchase_num", "supplier__name", "quot_num")
    filter_fields = {"supplier": "supplier_id", "godown": "godown_id"}
    date_filters = [{"field": "purchase_date", "label": "Order date"}]

    def get_filter_specs(self):
        supplier_choices = list(
            Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("id", "name")
        )
        return [
            {"name": "supplier", "label": "All suppliers", "choices": supplier_choices,
             "value": self.request.GET.get("supplier", "")},
            {"name": "godown", "label": "All godowns", "choices": list(godown_options().values_list("id", "name")),
             "value": self.request.GET.get("godown", "")},
        ]

    @staticmethod
    def _outstanding(order):
        """The lines still owed on one order, and what they come to."""
        zero = Decimal("0.0000")
        rows, value = [], Decimal("0.00")
        for item in order.items.all():
            pending = item.qty_pending
            if pending <= zero:
                continue
            line_value = (pending * (item.rate or Decimal("0"))).quantize(TWO_DP)
            value += line_value
            rows.append({
                "item": item,
                "ordered": item.qty_ordered,
                "invoiced": item.qty_invoiced or zero,
                "pending": pending,
                "value": line_value,
                "uom": uom_title(item),
            })
        return rows, value

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        zero = Decimal("0.00")

        groups, page_value = [], zero
        current = None
        today = timezone.localdate()
        for order in context["orders"]:
            order.pending_rows, order.pending_value = self._outstanding(order)
            if not order.pending_rows:
                continue
            order.days_late = (
                (today - order.expected_date).days
                if order.expected_date and order.expected_date < today else 0
            )
            page_value += order.pending_value
            if current is None or current["supplier"].pk != order.supplier_id:
                current = {"supplier": order.supplier, "orders": [], "value": zero}
                groups.append(current)
            current["orders"].append(order)
            current["value"] += order.pending_value
        context["groups"] = groups
        context["page_value"] = page_value

        everything = list(
            self.filtered_queryset().prefetch_related("items")
            if hasattr(self, "filtered_queryset")
            else self.get_queryset().prefetch_related("items")
        )
        total_value, order_count, supplier_ids = zero, 0, set()
        overdue = 0
        for order in everything:
            _rows, value = self._outstanding(order)
            if value <= zero:
                continue
            total_value += value
            order_count += 1
            supplier_ids.add(order.supplier_id)
            if order.expected_date and order.expected_date < today:
                overdue += 1
        context["pending_value"] = total_value
        context["pending_orders"] = order_count
        context["pending_suppliers"] = len(supplier_ids)
        context["overdue_orders"] = overdue
        return context


class PurchaseOrderCreateView(InventoryManageMixin, View):
    """Raise an order on a supplier.

    Deliberately the same screen as the purchase invoice — party at the top,
    goods in the middle, money at the bottom — because it is the same entry an
    operator makes; the difference is only that nothing is received here, so
    there is no paid box and no stock impact until the goods arrive.
    """

    page = "inventory.purchase_orders"
    action = "add"
    template_name = "inventory/purchase_order_form.html"

    def _context(self, **extra):
        items = (
            InventoryItem.objects
            .select_related("uom", "secondary_uom", "stock", "conversion__uom_from", "conversion__uom_to")
            .filter(status=STATUS_ACTIVE)
            .order_by("item_name")
        )
        context = {
            "title": "Purchase Order",
            "layout": get_layout(),
            "settings_url": reverse_lazy("inventory:purchase_order_form_settings"),
            "extra_field_types": EXTRA_FIELD_TYPES,
            "can_edit": user_has_permission(self.request.user, f"{self.page}.edit"),
            "next_order_no": next_purchase_order_number(),
            "suppliers": Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name"),
            "units": UOM.objects.order_by("title"),
            "godowns": godown_options(),
            "brokers": broker_options(),
            "wheat_products": wheat_product_options(),
            "bardana_products": bardana_product_options(),
            "today": timezone.localdate(),
            "items_json": json.dumps([
                {
                    "id": item.pk,
                    "name": item.item_name,
                    "code": item.code,
                    "uom": item.uom_id or "",
                    "rate": float(item.purchase_price or 0),
                    "stock": float(getattr(item.stock, "current_quantity", 0) or 0),
                    "stocked": item.item_kind == INVENTORY_KIND_PRODUCT,
                    "unit": uom_title(item),
                    "units": item_unit_options(item),
                }
                for item in items
            ]),
        }
        context.update(extra)
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context())

    def post(self, request, *args, **kwargs):
        posted = request.POST
        supplier_id = (posted.get("supplier") or "").strip()
        supplier = Supplier.objects.filter(pk=supplier_id).first() if supplier_id.isdigit() else None

        def decimal_of(raw, default="0"):
            text = (raw or "").strip().replace(",", "") or default
            return Decimal(text)

        def money(name, default="0"):
            try:
                return decimal_of(posted.get(name), default)
            except (InvalidOperation, ValueError):
                raise ValidationError(f"{name.replace('_', ' ').title()} must be a number.")

        lines = []
        item_ids = posted.getlist("item_id")
        quantities = posted.getlist("quantity")
        rates = posted.getlist("rate")
        uom_ids = posted.getlist("line_uom")
        for index, raw_id in enumerate(item_ids):
            if not (raw_id or "").strip().isdigit():
                continue
            item = InventoryItem.objects.filter(pk=raw_id).first()
            if not item:
                continue
            try:
                quantity = decimal_of(quantities[index] if index < len(quantities) else "")
                rate = decimal_of(rates[index] if index < len(rates) else "")
            except (InvalidOperation, ValueError):
                messages.error(request, f"Check the quantity and price on the {item.item_name} line.")
                return render(request, self.template_name, self._context(posted=posted))
            quantity = quantity.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            if quantity > 0:
                raw_uom = (uom_ids[index] if index < len(uom_ids) else "") or ""
                uom = UOM.objects.filter(pk=raw_uom).first() if raw_uom.strip().isdigit() else None
                lines.append({"inventory_item": item, "quantity": quantity, "rate": rate, "uom": uom})

        product_ids = posted.getlist("order_product")
        product_qtys = posted.getlist("order_product_qty")
        product_rates = posted.getlist("order_product_rate")
        orderable = {
            product.pk: product
            for product in list(wheat_product_options()) + list(bardana_product_options())
        }
        for index, raw_id in enumerate(product_ids):
            if not (raw_id or "").strip().isdigit():
                continue
            product = orderable.get(int(raw_id))
            if not product:
                continue
            try:
                quantity = decimal_of(product_qtys[index] if index < len(product_qtys) else "")
                rate = decimal_of(product_rates[index] if index < len(product_rates) else "")
            except (InvalidOperation, ValueError):
                messages.error(request, f"Check the quantity and rate on the {product.name} line.")
                return render(request, self.template_name, self._context(posted=posted))
            if quantity > 0:
                lines.append({"product": product, "quantity": quantity, "rate": rate})

        extra_values, extra_error = read_extra_values(posted)
        if extra_error:
            messages.error(request, extra_error)
            return render(request, self.template_name, self._context(posted=posted))

        try:
            order, net = create_purchase_order(
                supplier=supplier,
                quot_num=(posted.get("quot_num") or "").strip(),
                quot_date=(posted.get("quot_date") or "") or None,
                order_date=posted.get("order_date") or str(timezone.localdate()),
                expected_date=(posted.get("expected_date") or "") or None,
                godown=picked(posted, "godown", godown_options()),
                broker=picked(posted, "broker", broker_options()),
                lines=lines,
                discount_amount=money("discount_amount"),
                tax_amount=money("tax_amount"),
                remarks=(posted.get("remarks") or "").strip(),
                extra_data=extra_values,
                status=STATUS_DRAFT,
                user=request.user,
            )
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
            return render(request, self.template_name, self._context(posted=posted))

        messages.success(request, f"Purchase order {order.purchase_num} saved for {net}.")
        if "save_and_print" in posted:
            return redirect("inventory:purchase_order_print", pk=order.pk)
        if "save_and_new" in posted:
            return redirect("inventory:purchase_order_create")
        return redirect("inventory:purchase_order_board")


class PurchaseOrderFormSettingsView(InventoryManageMixin, View):
    """The settings menu on a purchase form: what it shows, and what it adds.

    Everything arrives as a plain POST and sends the operator back to the form,
    so the menu never has to keep a half-applied state of its own. Configuring
    the screen is an edit to how the site works, so it wants the manage
    permission and not merely the right to raise an order.

    Serves both purchase forms. Which one is a class attribute rather than a
    posted field: the form being configured decides where the operator is sent
    back to, and that is not something a request should be able to choose.
    """

    page = "inventory.purchase_orders"
    action = "edit"
    form_key = FORM_PURCHASE_ORDER
    redirect_to = "inventory:purchase_order_create"

    def post(self, request, *args, **kwargs):
        step = request.POST.get("step")

        if step == "fields":
            shown = set(request.POST.getlist("shown"))
            set_hidden([field["code"] for field in get_layout(self.form_key)["optional_fields"]
                        if field["code"] not in shown], self.form_key)
            messages.success(request, "Form fields updated.")

        elif step == "add":
            error = add_extra_field(
                label=request.POST.get("label"),
                kind=request.POST.get("type"),
                required=request.POST.get("required") == "1",
                options=(request.POST.get("options") or "").splitlines(),
                form=self.form_key,
            )
            if error:
                messages.error(request, error)
            else:
                messages.success(request, "Field added to the form.")

        elif step == "remove":
            remove_extra_field((request.POST.get("code") or "").strip(), self.form_key)
            messages.success(request, "Field removed from the form. What earlier records held under it is kept.")

        return redirect(self.redirect_to)


class PurchaseInvoiceFormSettingsView(PurchaseOrderFormSettingsView):
    """The same menu, configuring the invoice form instead."""

    form_key = FORM_PURCHASE_INVOICE
    redirect_to = "inventory:purchase_invoice_create"


class PurchaseOrderUpdateView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "edit"
    def get(self, request, pk):
        return self._blocked(request, pk)

    def post(self, request, pk):
        return self._blocked(request, pk)

    def _blocked(self, request, pk):
        messages.error(request, "A purchase order cannot be edited once it is created.")
        return redirect("inventory:purchase_order_detail", pk=pk)


class PurchaseOrderDetailView(InventoryListMixin, DetailView):
    page = "inventory.purchase_orders"
    model = PurchaseOrder
    template_name = "inventory/purchase_order_detail.html"
    context_object_name = "order"
    queryset = (
        PurchaseOrder.objects
        .select_related("supplier", "created_by", "approved_by", "closed_by")
        .prefetch_related("items__uom", "items__inventory_item", "invoices",
                          "items__invoice_lines__invoice")
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        item_form = PurchaseOrderItemForm()
        used_item_ids = self.object.items.values_list("inventory_item_id", flat=True)
        available_items = item_form.fields["inventory_item"].queryset.exclude(pk__in=used_item_ids).select_related("uom")
        item_form.fields["inventory_item"].queryset = available_items
        context["item_form"] = item_form
        context["item_uom_map"] = {str(i.pk): {"name": i.item_name, "uom": uom_title(i)} for i in available_items}
        lines = list(self.object.items.all())
        anything_invoiced = any((line.qty_invoiced or Decimal("0")) > 0 for line in lines)
        outstanding = sum((line.qty_pending for line in lines), Decimal("0"))
        context["can_cancel"] = self.object.status in (STATUS_DRAFT, STATUS_SUBMITTED) and not anything_invoiced
        context["can_close_short"] = anything_invoiced and outstanding > Decimal("0.0005")
        context["is_closed_early"] = self.object.status in (STATUS_CANCELLED, STATUS_CLOSED)
        context["outstanding_qty"] = outstanding
        context["cancel_form"] = PurchaseOrderCancelForm()
        context["close_short_form"] = PurchaseOrderCloseShortForm()
        context["reversal_form"] = ReversalReasonForm()
        context["linked_documents"] = linked_documents(self.object)
        invoice_rows = []
        for invoice in self.object.invoices.select_related("supplier").prefetch_related("items").order_by("invoice_date", "id"):
            taken = sum(
                (line.quantity or Decimal("0") for line in invoice.items.all()
                 if line.purchase_order_item_id and line.purchase_order_item.purchase_order_id == self.object.pk),
                Decimal("0"),
            )
            invoice_rows.append({
                "invoice": invoice,
                "quantity": taken,
                "reversed": invoice.status == STATUS_REVERSED,
            })
        context["order_invoices"] = invoice_rows
        context["order_total"] = sum((line.total_amount for line in lines), Decimal("0.00"))
        decorate([self.object])
        context["can_edit_lines"] = (
            context.get("can_edit")
            and self.object.status in (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED)
        )
        return context


def redirect_after_item(request, pk):
    """Redirect back to the originating page with the PO collapsible auto-opened."""
    ref = request.META.get("HTTP_REFERER") or str(reverse_lazy("inventory:purchase_order_board"))
    parts = urlsplit(ref)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "open"]
    query.append(("open", str(pk)))
    return redirect(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), "")))


class PurchaseOrderItemCreateView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "add"
    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        if order.status == STATUS_FULLY_INVOICED:
            messages.error(request, "Fully received purchase order cannot be updated.")
            return redirect("inventory:purchase_order_detail", pk=pk)
        form = PurchaseOrderItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.purchase_order = order
            item.uom = item.inventory_item.uom
            item.created_by = request.user
            item.updated_by = request.user
            if item.is_duplicate_in_order():
                messages.error(request, "This item is already added to this purchase order.")
            else:
                item.save()
                messages.success(request, "Purchase order item saved.")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return redirect_after_item(request, pk)


class PurchaseOrderItemUpdateView(InventoryManageMixin, UpdateView):
    page = "inventory.purchase_orders"
    model = PurchaseOrderItem
    form_class = PurchaseOrderItemForm
    template_name = "inventory/simple_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.purchase_order.status != STATUS_SUBMITTED:
            messages.error(request, "Only items of a created purchase order can be edited.")
            return redirect("inventory:purchase_order_detail", pk=self.object.purchase_order_id)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"uom_title": uom_title(self.object)}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit Item - {self.object.purchase_num}"
        return context

    def form_valid(self, form):
        item = form.save(commit=False)
        item.uom = item.inventory_item.uom
        item.updated_by = self.request.user
        if item.is_duplicate_in_order():
            form.add_error("inventory_item", "This item is already added to this purchase order.")
            return self.form_invalid(form)
        item.save()
        messages.success(self.request, "Purchase order item updated.")
        list_url = str(reverse_lazy("inventory:purchase_order_board"))
        return redirect(f"{list_url}?open={item.purchase_order_id}")


class PurchaseOrderLinesUpdateView(InventoryManageMixin, View):
    """The order's lines, corrected together on the order itself.

    The document is the natural place to fix a line: the figure that is wrong
    is being read there. Only what a line actually says is editable --
    quantity, rate, discount -- and never the item, because changing what was
    ordered is a different order, not an edit.

    Every line is checked before any is written, so a page of corrections
    cannot half-save and leave the operator guessing which half took.
    """

    page = "inventory.purchase_orders"
    action = "edit"

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        back = redirect("inventory:purchase_order_detail", pk=order.pk)

        if order.status not in (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED):
            messages.error(request, f"{order.purchase_num} is closed, so its lines can no longer be edited.")
            return back

        changes = []
        for item in order.items.all():
            try:
                quantity = decimal_of(request.POST.get(f"quantity_{item.pk}"))
                rate = decimal_of(request.POST.get(f"rate_{item.pk}"))
                discount = decimal_of(request.POST.get(f"discount_{item.pk}") or "0")
            except (InvalidOperation, ValueError):
                messages.error(request, f"{item.descr}: quantity, rate and discount must be numbers.")
                return back

            if quantity <= 0:
                messages.error(request, f"{item.descr}: the quantity must be greater than zero.")
                return back
            if quantity < (item.qty_invoiced or Decimal("0")):
                messages.error(
                    request,
                    f"{item.descr}: {item.qty_invoiced} has already been invoiced, "
                    f"so the order cannot be cut to {quantity}.",
                )
                return back
            if discount > quantity * rate:
                messages.error(request, f"{item.descr}: the discount is more than the line comes to.")
                return back

            quantity = quantity.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            rate = rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if (quantity, rate, discount) == (item.quantity, item.rate, item.discount_amount):
                continue
            changes.append((item, quantity, rate, discount))

        if not changes:
            messages.info(request, "Nothing on the lines was changed.")
            return back

        with transaction.atomic():
            for item, quantity, rate, discount in changes:
                item.quantity = quantity
                item.rate = rate
                item.unit_rate = rate
                item.discount_amount = discount
                item.updated_by = request.user
                item.save()
            _refresh_order_receipt_status(order, user=request.user)

        plural = "" if len(changes) == 1 else "s"
        messages.success(request, f"{len(changes)} line{plural} updated on {order.purchase_num}.")
        return back


class PurchaseOrderPrintView(PrintContextMixin, InventoryListMixin, DetailView):
    page = "inventory.purchase_orders"
    model = PurchaseOrder
    template_name = "inventory/purchase_order_print.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(self.object.items.filter(status=YES))
        context["items"] = items
        context["total_qty"] = sum((i.quantity or Decimal("0")) for i in items)
        context["total_discount"] = sum((i.discount_amount or Decimal("0")) for i in items)
        grand_total = sum((i.total_amount for i in items), Decimal("0"))
        context["grand_total"] = grand_total
        context["amount_in_words"] = amount_in_words(grand_total)
        supplier = self.object.supplier
        approver = self.object.approved_by
        shown = get_layout()["shown"]
        pairs = [
            ("PO No", self.object.purchase_num),
            ("Date", self.object.purchase_date),
            ("Status", self.object.get_status_display()),
            ("Expected", self.object.expected_date if shown.get("expected_date", True) else ""),
            ("Quot Num", self.object.quot_num if shown.get("quot_num", True) else ""),
            ("Quot Date", self.object.quot_date if shown.get("quot_date", True) else ""),
            ("Godown", str(self.object.godown) if self.object.godown_id and shown.get("godown", True) else ""),
            ("Broker", self.object.broker.title if self.object.broker_id and shown.get("broker", True) else ""),
            ("Approved By", approver.get_full_name() or approver.username if approver else ""),
            ("Supplier Name", supplier.name if supplier else ""),
            ("Phone", (supplier.tel1 or supplier.tel2) if supplier else ""),
            ("Email", supplier.email if supplier else ""),
            ("NTN", supplier.ntn_number if supplier else ""),
            ("Sales Tax", supplier.sale_tax_num if supplier else ""),
        ]
        context["meta_pairs"] = [(label, value) for label, value in pairs if value]
        context["supplier_address"] = " ".join(
            part for part in ((supplier.addr1 or ""), (supplier.addr2 or "")) if part
        ).strip() if supplier else ""
        context["print_back_url"] = (
            f"{reverse_lazy('inventory:purchase_order_board')}?open={self.object.pk}"
        )
        return context


class PurchaseOrderItemToggleStatusView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "edit"
    def post(self, request, pk):
        item = get_object_or_404(PurchaseOrderItem, pk=pk)
        item.status = NO if item.status == YES else YES
        item.updated_by = request.user
        item.save()
        return redirect_after_item(request, item.purchase_order_id)


def _current_draft_tx_id():
    return ManualTransaction.objects.filter(status=STATUS_DRAFT).order_by("-id").values_list("transaction_id", flat=True).first()


class ManualTransactionView(InventoryManageMixin, View):
    page = "inventory.manual_transaction"
    action = "index"
    template_name = "inventory/manual_transaction.html"

    def get(self, request):
        from django.shortcuts import render

        draft_tx_id = _current_draft_tx_id()
        rows = ManualTransaction.objects.select_related("inventory_item").filter(transaction_id=draft_tx_id, status=STATUS_DRAFT) if draft_tx_id else ManualTransaction.objects.none()
        used_item_ids = list(rows.values_list("inventory_item_id", flat=True))
        items = InventoryItem.objects.select_related("uom", "stock").exclude(pk__in=used_item_ids).order_by("item_name")
        batch_descr = rows.values_list("descr", flat=True).first() or ""
        batch_supplier = rows.values_list("supplier_id", flat=True).first()
        form = ManualTransactionForm(initial={"descr": batch_descr, "qty": 1, "supplier": batch_supplier})
        form.fields["inventory_item"].queryset = items
        form.fields["supplier"].queryset = Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name")
        from itertools import groupby as _groupby
        posted_qs = ManualTransaction.objects.filter(status=STATUS_POSTED).order_by("transaction_id", "id")
        history = {}
        for tx_id, grp in _groupby(posted_qs, key=lambda r: r.transaction_id):
            rows_list = list(grp)
            history[tx_id] = {
                "rows": rows_list,
                "date": rows_list[0].created_at,
                "descr": rows_list[0].descr,
                "total_qty": sum(r.qty for r in rows_list),
                "total_amount": sum(r.qty * r.price for r in rows_list),
            }
        context = {
            "title": "Manual Stock Transaction",
            "form": form,
            "rows": rows,
            "transaction_id": draft_tx_id,
            "item_price_map": {str(i.pk): {"price": str(getattr(i, "stock", None) and i.stock.current_price or i.price), "qty": str(getattr(i, "stock", None) and i.stock.current_quantity or 0), "uom": uom_title(i)} for i in items},
            "history": history,
        }
        return render(request, self.template_name, context)


class ManualTransactionAddView(InventoryManageMixin, View):
    page = "inventory.manual_transaction"
    action = "add"
    def post(self, request):
        form = ManualTransactionForm(request.POST)
        if form.is_valid():
            draft_tx_id = _current_draft_tx_id() or generate_transaction_id("ADJ", ManualTransaction)
            if draft_tx_id and ManualTransaction.objects.filter(transaction_id=draft_tx_id, status=STATUS_DRAFT, inventory_item=form.cleaned_data["inventory_item"]).exists():
                messages.error(request, "This item is already added to the current batch.")
                return redirect("inventory:manual_transaction")
            row = form.save(commit=False)
            row.transaction_id = draft_tx_id
            row.status = STATUS_DRAFT
            row.created_by = request.user
            row.updated_by = request.user
            row.save()
            batch = ManualTransaction.objects.filter(transaction_id=draft_tx_id, status=STATUS_DRAFT)
            batch.update(supplier=row.supplier)
            if row.descr:
                batch.update(descr=row.descr)
            messages.success(request, "Entry added to draft.")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return redirect("inventory:manual_transaction")


class ManualTransactionToggleView(InventoryManageMixin, View):
    page = "inventory.manual_transaction"
    action = "edit"
    def post(self, request, pk):
        row = get_object_or_404(ManualTransaction, pk=pk, status=STATUS_DRAFT)
        row.selected = NO if row.selected == YES else YES
        row.updated_by = request.user
        row.save(update_fields=["selected", "updated_by", "updated_at"])
        return redirect("inventory:manual_transaction")


class ManualTransactionDeleteView(InventoryManageMixin, View):
    page = "inventory.manual_transaction"
    action = "delete"
    def post(self, request, pk):
        row = get_object_or_404(ManualTransaction, pk=pk, status=STATUS_DRAFT)
        row.delete()
        messages.success(request, "Entry removed.")
        return redirect("inventory:manual_transaction")


class ManualTransactionSubmitView(InventoryManageMixin, View):
    page = "inventory.manual_transaction"
    action = "add"
    def post(self, request):
        draft_tx_id = _current_draft_tx_id()
        if not draft_tx_id:
            messages.error(request, "No draft entries to submit.")
            return redirect("inventory:manual_transaction")
        try:
            count = finalize_manual_transaction(transaction_id=draft_tx_id, user=request.user)
            messages.success(request, f"{count} entries posted to ledger and stock updated.")
            return redirect("inventory:manual_transaction_print", tx_id=draft_tx_id)
        except ValidationError as exc:
            messages.error(request, exc)
        return redirect("inventory:manual_transaction")


class ManualTransactionPrintView(InventoryManageMixin, PrintContextMixin, View):
    page = "inventory.manual_transaction"
    action = "view"
    template_name = "inventory/manual_transaction_print.html"

    def get(self, request, tx_id):
        from django.shortcuts import render
        rows = ManualTransaction.objects.filter(transaction_id=tx_id, status=STATUS_POSTED).select_related("inventory_item__uom", "supplier").order_by("id")
        if not rows.exists():
            messages.error(request, "Transaction not found.")
            return redirect("inventory:manual_transaction")
        grand_total = sum(r.qty * r.price for r in rows)
        context = self.get_print_context(request)
        context.update({
            "tx_id": tx_id,
            "rows": rows,
            "grand_total": grand_total,
            "amount_in_words": amount_in_words(grand_total),
            "tx_date": rows[0].created_at,
            "descr": rows[0].descr,
            "supplier": rows[0].supplier,
            "prepared_by": rows[0].created_by,
        })
        return render(request, self.template_name, context)


class CustomerListView(BaseSimpleListView):
    page = "inventory.customers"
    model = Customer
    queryset = Customer.objects.select_related("city").order_by("customer_name")
    search_fields = ("customer_name", "customer_code", "customer_cell_no")
    filter_fields = {"status": "status"}
    extra_context = {"title": "Customers", "create_url": reverse_lazy("inventory:customer_create"), "edit_url_name": "inventory:customer_update", "status_toggle_url_name": "inventory:customer_toggle_status", "default_toggle_url_name": "inventory:customer_toggle_default", "columns": [("Name", "customer_name"), ("Code", "customer_code"), ("Cell", "customer_cell_no"), ("Status", "status_toggle"), ("Default Customer", "default_toggle")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class CustomerToggleStatusView(InventoryManageMixin, View):
    page = "inventory.customers"
    action = "edit"
    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        customer.status = STATUS_INACTIVE if customer.status == STATUS_ACTIVE else STATUS_ACTIVE
        customer.updated_by = request.user
        if customer.status == STATUS_INACTIVE and customer.is_default:
            customer.is_default = False
            customer.save(update_fields=["status", "is_default", "updated_by", "updated_at"])
        else:
            customer.save(update_fields=["status", "updated_by", "updated_at"])
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("inventory:customer_list"))


class CustomerToggleDefaultView(InventoryManageMixin, View):
    page = "inventory.customers"
    action = "edit"
    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        if not customer.is_default and customer.status != STATUS_ACTIVE:
            messages.error(request, "An inactive customer cannot be set as default.")
            return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("inventory:customer_list"))
        customer.is_default = not customer.is_default
        customer.updated_by = request.user
        customer.save()
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("inventory:customer_list"))


class CustomerCreateView(EmbeddedCreateMixin, InventoryManageMixin, CreateView):
    page = "inventory.customers"
    model = Customer
    form_class = CustomerForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:customer_list")
    success_message = "Customer saved."
    embed_message_type = "customer:saved"
    extra_context = {"title": "Customer"}

    def embed_payload(self, obj):
        return {"id": obj.pk, "name": obj.customer_name}

    def form_valid(self, form):
        creating = self.object is None  # None on create, set on update
        response = super().form_valid(form)
        if creating:
            node = create_customer_receivable_account(customer=self.object, user=self.request.user)
            opening_balance = form.cleaned_data.get("opening_balance")
            if node and opening_balance:
                node.opening_balance = opening_balance
                node.save(update_fields=["opening_balance", "updated_at"])
        if self.is_embedded():
            return self.embed_saved_response()
        return response


class CustomerUpdateView(CustomerCreateView, UpdateView):
    success_message = "Customer updated."


class SaleInvoiceListView(SortableListMixin, InventoryListMixin, ListView):
    """Sales entered as invoices, the counterpart of the purchase invoice list.

    Read the same way as the purchase boards, because it answers the same kind
    of question about the other direction: what went out, what it came to, and
    what the customer still owes for it.
    """

    page = "inventory.pos_sales"
    template_name = "inventory/sale_invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 25
    queryset = (
        POSMaster.objects
        .select_related("customer", "created_by")
        .prefetch_related("items__inventory_item__uom")
        .order_by("-sale_date", "-id")
    )
    search_fields = ("sale_num", "customer__customer_name", "invoice_num", "remarks")
    filter_fields = {"customer": "customer_id"}
    date_filters = [{"field": "sale_date", "label": "Sale date"}]
    sort_fields = {
        "sale_num": "sale_seq_num",
        "sale_date": ("sale_date", "id"),
        "customer": "customer__customer_name",
        "net_amount": "net_amount",
        "balance": "balance",
    }
    default_sort = "sale_date"
    default_sort_dir = "desc"

    PER_PAGE_OPTIONS = (10, 25, 50, 100)

    TAB_ALL = "all"
    TAB_DRAFT = "draft"
    TAB_OWING = "owing"
    TAB_SETTLED = "settled"
    TABS = (
        (TAB_ALL, "All"),
        (TAB_DRAFT, "Not posted"),
        (TAB_OWING, "Owing"),
        (TAB_SETTLED, "Settled"),
    )

    def current_tab(self):
        tab = self.request.GET.get("tab", self.TAB_ALL)
        return tab if tab in dict(self.TABS) else self.TAB_ALL

    def get_paginate_by(self, queryset):
        raw = (self.request.GET.get("per_page") or "").strip()
        if raw.isdigit() and int(raw) in self.PER_PAGE_OPTIONS:
            return int(raw)
        return self.paginate_by

    def filtered_queryset(self):
        """Everything the filter bar allows, before the tab narrows it.

        The tiles are counted over this: clicking a tab must not change the
        numbers above it, because they are what the tabs are for.
        """
        return super().get_queryset()

    def get_queryset(self):
        queryset = self.filtered_queryset()
        tab = self.current_tab()
        if tab == self.TAB_DRAFT:
            return queryset.exclude(posted=YES)
        if tab == self.TAB_OWING:
            return queryset.filter(posted=YES, balance__gt=Decimal("0.00"))
        if tab == self.TAB_SETTLED:
            return queryset.filter(posted=YES, balance__lte=Decimal("0.00"))
        return queryset

    def get_filter_specs(self):
        customer_choices = list(
            Customer.objects.filter(status=STATUS_ACTIVE).order_by("customer_name").values_list("id", "customer_name")
        )
        return [
            {"name": "customer", "label": "All customers", "short_label": "Customer",
             "choices": customer_choices, "value": self.request.GET.get("customer", "")},
        ]

    def tiles(self):
        """The figures over everything the filters allow, not just this page."""
        base = self.filtered_queryset()
        posted = base.filter(posted=YES)
        sold = posted.aggregate(count=Count("id"), value=Sum("net_amount"), taken=Sum("total_paid"))
        owing = posted.filter(balance__gt=Decimal("0.00")).aggregate(count=Count("id"), value=Sum("balance"))
        drafts = base.exclude(posted=YES).aggregate(count=Count("id"), value=Sum("net_amount"))
        month = timezone.localdate().replace(day=1)
        this_month = posted.filter(sale_date__gte=month).aggregate(count=Count("id"), value=Sum("net_amount"))
        return {
            "sold_count": sold["count"] or 0,
            "sold_value": sold["value"] or Decimal("0.00"),
            "taken": sold["taken"] or Decimal("0.00"),
            "month_count": this_month["count"] or 0,
            "month_value": this_month["value"] or Decimal("0.00"),
            "owing_count": owing["count"] or 0,
            "owing_value": owing["value"] or Decimal("0.00"),
            "draft_count": drafts["count"] or 0,
            "draft_value": drafts["value"] or Decimal("0.00"),
            "month_from": month.isoformat(),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        carried = self.request.GET.copy()
        for key in ("tab", "page"):
            carried.pop(key, None)
        context["base_query"] = carried.urlencode()
        context["per_page"] = self.get_paginate_by(None)
        context["per_page_options"] = list(self.PER_PAGE_OPTIONS)
        context["tabs"] = self.TABS
        context["current_tab"] = self.current_tab()
        context["filters_active"] = any(
            (self.request.GET.get(key) or "").strip()
            for key in ("q", "customer", "date_from", "date_to", "tab")
        )
        context["tiles"] = self.tiles()
        context["export_url"] = reverse_lazy("inventory:sale_invoice_export")

        page_total = Decimal("0.00")
        for invoice in context["invoices"]:
            lines = list(invoice.items.all())
            invoice.line_count = len(lines)
            invoice.qty_total = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
            if invoice.posted != YES:
                invoice.state, invoice.state_label = "draft", "Not posted"
            elif (invoice.balance or Decimal("0.00")) > 0:
                invoice.state, invoice.state_label = "owing", "Owing"
            else:
                invoice.state, invoice.state_label = "settled", "Settled"
            page_total += invoice.net_amount or Decimal("0.00")
        context["page_total"] = page_total
        context["invoice_count"] = context["paginator"].count if context.get("paginator") else len(context["invoices"])
        return context


class SaleInvoiceExportView(InventoryListMixin, TableExportView):
    """The sale rows on screen, in whichever format was asked for."""

    page = "inventory.pos_sales"
    columns = SALE_COLUMNS
    filename = "sale-invoices"
    title = "Sale Invoices"

    def get_rows(self):
        listing = SaleInvoiceListView(request=self.request, kwargs={}, args=())
        rows = list(listing.get_queryset())
        for row in rows:
            lines = list(row.items.all())
            row.line_count = len(lines)
            row.qty_total = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
            if row.posted != YES:
                row.state_label = "Not posted"
            elif (row.balance or Decimal("0.00")) > 0:
                row.state_label = "Owing"
            else:
                row.state_label = "Settled"
        return rows


class SaleInvoiceCreateView(InventoryManageMixin, View):
    """A sale written up as an invoice, rather than rung through the POS screen.

    Same entry as the purchase invoice, the other way round: the customer at the
    top, the goods in the middle, the money at the bottom. It posts through the
    same service the POS screen uses, so there is one set of books either way.
    """

    page = "inventory.pos_sales"
    action = "add"
    template_name = "inventory/sale_invoice_form.html"

    def _context(self, **extra):
        items = (
            InventoryItem.objects
            .select_related("uom", "secondary_uom", "stock", "conversion__uom_from", "conversion__uom_to")
            .filter(status=STATUS_ACTIVE)
            .order_by("item_name")
        )
        context = {
            "title": "Sale Invoice",
            "next_invoice_no": next_sale_invoice_number(),
            "customers": Customer.objects.filter(status=STATUS_ACTIVE).order_by("customer_name"),
            "units": UOM.objects.order_by("title"),
            "today": timezone.localdate(),
            "items_json": json.dumps([
                {
                    "id": item.pk,
                    "name": item.item_name,
                    "code": item.code,
                    "uom": item.uom_id or "",
                    "rate": float(item.price or 0),
                    "stock": float(getattr(item.stock, "current_quantity", 0) or 0),
                    "stocked": item.item_kind == INVENTORY_KIND_PRODUCT,
                    "unit": uom_title(item),
                    "units": item_unit_options(item),
                }
                for item in items
            ]),
        }
        context.update(extra)
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context())

    def post(self, request, *args, **kwargs):
        posted = request.POST
        customer_id = (posted.get("customer") or "").strip()
        customer = Customer.objects.filter(pk=customer_id).first() if customer_id.isdigit() else None

        def decimal_of(raw, default="0"):
            text = (raw or "").strip().replace(",", "") or default
            return Decimal(text)

        def money(name, default="0"):
            try:
                return decimal_of(posted.get(name), default)
            except (InvalidOperation, ValueError):
                raise ValidationError(f"{name.replace('_', ' ').title()} must be a number.")

        lines = []
        item_ids = posted.getlist("item_id")
        quantities = posted.getlist("quantity")
        prices = posted.getlist("rate")
        uom_ids = posted.getlist("line_uom")
        for index, raw_id in enumerate(item_ids):
            if not (raw_id or "").strip().isdigit():
                continue
            item = InventoryItem.objects.filter(pk=raw_id).first()
            if not item:
                continue
            try:
                quantity = decimal_of(quantities[index] if index < len(quantities) else "")
                price = decimal_of(prices[index] if index < len(prices) else "")
            except (InvalidOperation, ValueError):
                messages.error(request, f"Check the quantity and price on the {item.item_name} line.")
                return render(request, self.template_name, self._context(posted=posted))
            if quantity > 0:
                raw_uom = (uom_ids[index] if index < len(uom_ids) else "") or ""
                uom = UOM.objects.filter(pk=raw_uom).first() if raw_uom.strip().isdigit() else None
                lines.append({"inventory_item": item, "quantity": quantity, "price": price, "uom": uom})

        order_item_ids = posted.getlist("row_order_item")
        picked = {
            item.pk: item
            for item in SalesOrderItem.objects.filter(
                pk__in=[int(pk) for pk in order_item_ids if (pk or "").strip().isdigit()]
            ).select_related("sales_order")
        }
        for index, raw_pk in enumerate(order_item_ids):
            if not (raw_pk or "").strip().isdigit() or index >= len(lines):
                continue
            order_item = picked.get(int(raw_pk))
            if not order_item:
                messages.error(request, "One of the sales order lines no longer exists.")
                return render(request, self.template_name, self._context(posted=posted))
            lines[index]["order_item"] = order_item

        try:
            sale_date = posted.get("sale_date") or str(timezone.localdate())
            sale, net = create_direct_sale(
                customer=customer,
                sale_date=sale_date,
                lines=lines,
                discount_amount=money("discount_amount"),
                tax_amount=money("tax_amount"),
                paid_amount=money("paid_amount"),
                remarks=(posted.get("remarks") or "").strip(),
                user=request.user,
            )
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
            return render(request, self.template_name, self._context(posted=posted))

        messages.success(request, f"Sale {sale.sale_num} saved for {net}.")
        if "save_and_print" in posted:
            return redirect("inventory:pos_receipt", pk=sale.pk)
        return redirect("inventory:pos_detail", pk=sale.pk)


class CustomerSalesOrderOptionsView(InventoryListMixin, View):
    """This customer's open orders, as the sale invoice screen needs them.

    Answers the picker rather than a page: the screen asks the moment a
    customer is chosen, so the orders arrive without a reload. Only what is
    still to be invoiced is offered.
    """

    page = "inventory.pos_sales"

    def get(self, request, *args, **kwargs):
        customer_id = (request.GET.get("customer") or "").strip()
        if not customer_id.isdigit():
            return JsonResponse({"orders": []})

        rows = open_sales_order_lines(
            customer=Customer.objects.filter(pk=int(customer_id)).first()
        )

        orders = {}
        for line in rows:
            order = line.sales_order
            held = orders.setdefault(order.pk, {
                "id": order.pk,
                "number": order.order_num,
                "date": order.order_date.isoformat() if order.order_date else "",
                "date_text": order.order_date.strftime("%d-%m-%Y") if order.order_date else "",
                "status": order.get_status_display(),
                "quantity": Decimal("0.0000"),
                "value": Decimal("0.00"),
                "lines": [],
            })
            pending = line.qty_pending
            rate = line.rate or Decimal("0.00")
            amount = (pending * rate).quantize(TWO_DP)
            held["quantity"] += pending
            held["value"] += amount
            held["lines"].append({
                "order_item_id": line.pk,
                "item_id": line.inventory_item_id,
                "name": line.descr,
                "quantity": float(pending),
                "ordered": float(line.quantity or 0),
                "uom_id": line.uom_id or line.inventory_item.uom_id or "",
                "unit": line.uom.title if line.uom else (
                    line.inventory_item.uom.title if line.inventory_item.uom else ""),
                "rate": float(rate),
                "amount": float(amount),
            })

        payload = [
            {**order, "quantity": float(order["quantity"]), "value": float(order["value"]),
             "items": len(order["lines"])}
            for order in sorted(orders.values(), key=lambda o: o["date"], reverse=True)
        ]
        return JsonResponse({"orders": payload})


class SalesOrderListView(SortableListMixin, InventoryListMixin, ListView):
    """Orders raised by customers: what is promised, and what is still to go.

    Read the same way as the purchase orders board, because it is the same
    question from the other side.
    """

    page = "inventory.pos_sales"
    template_name = "inventory/sales_order_list.html"
    context_object_name = "orders"
    paginate_by = 25
    queryset = (
        SalesOrder.objects
        .select_related("customer", "created_by")
        .prefetch_related("items__inventory_item", "items__uom")
        .order_by("-order_date", "-id")
    )
    search_fields = ("order_num", "customer__customer_name", "customer_ref", "remarks")
    filter_fields = {"customer": "customer_id", "status": "status"}
    date_filters = [{"field": "order_date", "label": "Order date"}]
    sort_fields = {
        "order_num": "seq_num",
        "order_date": ("order_date", "id"),
        "customer": "customer__customer_name",
    }
    default_sort = "order_date"
    default_sort_dir = "desc"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = list(context["orders"])
        for order in rows:
            lines = list(order.items.all())
            order.line_count = len(lines)
            order.qty_total = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
            order.qty_still_due = sum((line.qty_pending for line in lines), Decimal("0"))
            order.value_total = sum((line.total_amount for line in lines), Decimal("0.00"))
        context["statuses"] = INV_SALES_ORDER_STATUS_CHOICES
        context["create_url"] = reverse_lazy("inventory:sales_order_create")
        return context


class SalesOrderCreateView(InventoryManageMixin, View):
    """Raise an order on a customer. Nothing is committed to the books by it."""

    page = "inventory.pos_sales"
    action = "add"
    template_name = "inventory/sales_order_form.html"

    def _context(self, **extra):
        items = (
            InventoryItem.objects
            .select_related("uom", "secondary_uom", "stock")
            .filter(status=STATUS_ACTIVE)
            .order_by("item_name")
        )
        context = {
            "title": "Sales Order",
            "next_order_no": next_sales_order_number(),
            "customers": Customer.objects.filter(status=STATUS_ACTIVE).order_by("customer_name"),
            "units": UOM.objects.order_by("title"),
            "today": timezone.localdate(),
            "items_json": json.dumps([
                {
                    "id": item.pk,
                    "name": item.item_name,
                    "code": item.code,
                    "uom": item.uom_id or "",
                    "rate": float(item.price or 0),
                    "stock": float(getattr(item.stock, "current_quantity", 0) or 0),
                    "stocked": item.item_kind == INVENTORY_KIND_PRODUCT,
                    "unit": uom_title(item),
                    "units": item_unit_options(item),
                }
                for item in items
            ]),
        }
        context.update(extra)
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context())

    def post(self, request, *args, **kwargs):
        posted = request.POST
        customer_id = (posted.get("customer") or "").strip()
        customer = Customer.objects.filter(pk=customer_id).first() if customer_id.isdigit() else None

        lines = []
        item_ids = posted.getlist("item_id")
        quantities = posted.getlist("quantity")
        rates = posted.getlist("rate")
        uom_ids = posted.getlist("line_uom")
        for index, raw_id in enumerate(item_ids):
            if not (raw_id or "").strip().isdigit():
                continue
            item = InventoryItem.objects.filter(pk=raw_id).first()
            if not item:
                continue
            try:
                quantity = decimal_of(quantities[index] if index < len(quantities) else "")
                rate = decimal_of(rates[index] if index < len(rates) else "")
            except (InvalidOperation, ValueError):
                messages.error(request, f"Check the quantity and price on the {item.item_name} line.")
                return render(request, self.template_name, self._context(posted=posted))
            if quantity > 0:
                raw_uom = (uom_ids[index] if index < len(uom_ids) else "") or ""
                uom = UOM.objects.filter(pk=raw_uom).first() if raw_uom.strip().isdigit() else None
                lines.append({"inventory_item": item, "quantity": quantity, "rate": rate, "uom": uom})

        try:
            order, total = create_sales_order(
                customer=customer,
                order_date=posted.get("order_date") or str(timezone.localdate()),
                expected_date=posted.get("expected_date") or None,
                customer_ref=(posted.get("customer_ref") or "").strip(),
                lines=lines,
                remarks=(posted.get("remarks") or "").strip(),
                user=request.user,
            )
            if "save_draft" not in posted:
                submit_sales_order(order=order, user=request.user)
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
            return render(request, self.template_name, self._context(posted=posted))

        messages.success(request, f"Sales order {order.order_num} raised for {total}.")
        return redirect("inventory:sales_order_list")


class SalesOrderCloseView(InventoryManageMixin, View):
    """Stop an order early: the balance is given up on, not shipped."""

    page = "inventory.pos_sales"
    action = "edit"

    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(SalesOrder, pk=pk)
        try:
            close_sales_order(
                order=order,
                reason=(request.POST.get("reason") or "").strip(),
                remarks=(request.POST.get("remarks") or "").strip(),
                user=request.user,
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, f"{order.order_num} closed.")
        return redirect("inventory:sales_order_list")


class POSListView(InventoryManageMixin, View):
    page = "inventory.pos_sales"
    action = "index"
    template_name = "inventory/pos_list.html"

    def get(self, request):
        from django.shortcuts import render

        items = [
            {"id": s.inventory_item_id, "name": s.item_name, "price": float(s.current_price or 0), "stock": float(s.current_quantity or 0)}
            for s in Stock.objects.filter(status=STATUS_ACTIVE, current_quantity__gt=0).order_by("item_name")
        ]
        context = {
            "master_form": POSMasterForm(),
            "items_json": items,
            "recent_sales": POSMaster.objects.select_related("customer").filter(posted=YES).order_by("-id")[:10],
        }
        return render(request, self.template_name, context)


class POSCheckoutView(InventoryManageMixin, View):
    page = "inventory.pos_sales"
    action = "add"
    def post(self, request):
        item_ids = request.POST.getlist("item_id")
        qtys = request.POST.getlist("qty")
        prices = request.POST.getlist("price")
        discounts = request.POST.getlist("discount")

        lines = []
        for idx, item_id in enumerate(item_ids):
            if not item_id:
                continue
            qty = Decimal(qtys[idx] or "0").quantize(Decimal("0.01"))
            if qty <= 0:
                continue
            price = Decimal(prices[idx] or "0").quantize(Decimal("0.01"))
            discount = Decimal(discounts[idx] or "0").quantize(Decimal("0.01"))
            lines.append((int(item_id), qty, price, discount))

        if not lines:
            messages.error(request, "Add at least one item with quantity before posting.")
            return redirect("inventory:pos_list")

        needed = {}
        for item_id, qty, _price, _disc in lines:
            needed[item_id] = needed.get(item_id, Decimal("0")) + qty
        for stock in Stock.objects.filter(inventory_item_id__in=needed):
            if needed[stock.inventory_item_id] > (stock.current_quantity or Decimal("0")):
                messages.error(request, f"Insufficient stock for {stock.item_name} (available {stock.current_quantity}).")
                return redirect("inventory:pos_list")

        return self._checkout(request, lines)

    @transaction.atomic
    def _checkout(self, request, lines):
        sale = POSMaster.objects.create(
            transaction_id=generate_transaction_id("SAL", POSMaster),
            sale_date=request.POST.get("sale_date") or timezone.localdate(),
            pay_mode=request.POST.get("pay_mode") or "cash",
            customer_id=request.POST.get("customer") or None,
            remarks=f"Walking customer {timezone.now():%Y-%m-%d %H:%M:%S}",
            created_by=request.user,
            updated_by=request.user,
        )
        for item_id, qty, price, discount in lines:
            POSDetail.objects.create(
                pos_master=sale,
                inventory_item_id=item_id,
                quantity=qty,
                price=price,
                discount_amount=discount,
                created_by=request.user,
                updated_by=request.user,
            )
        post_sale(sale=sale, user=request.user)
        messages.success(request, f"Sale {sale.sale_num} posted — {len(lines)} item(s), stock updated.")
        return redirect("inventory:pos_receipt", pk=sale.pk)


class POSReceiptView(PrintContextMixin, InventoryListMixin, DetailView):
    page = "inventory.pos_sales"
    model = POSMaster
    template_name = "inventory/pos_receipt.html"
    context_object_name = "sale"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = self.object.items.all()
        context["items"] = items
        context["total_qty"] = sum((i.quantity or Decimal("0") for i in items), Decimal("0"))
        context["total_discount"] = sum((i.discount_amount or Decimal("0") for i in items), Decimal("0"))
        return context


class POSCreateView(InventoryManageMixin, CreateView):
    page = "inventory.pos_sales"
    model = POSMaster
    form_class = POSMasterForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:pos_list")
    success_message = "Sale saved."
    extra_context = {"title": "POS Sale"}

    def form_valid(self, form):
        if not form.instance.transaction_id:
            form.instance.transaction_id = generate_transaction_id("SAL", POSMaster)
        if not form.instance.remarks:
            form.instance.remarks = f"Walking customer {timezone.now():%Y-%m-%d %H:%M:%S}"
        return super().form_valid(form)


class POSUpdateView(POSCreateView, UpdateView):
    success_message = "Sale updated."

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.posted == YES:
            messages.error(request, "Posted sale cannot be updated.")
            return redirect("inventory:pos_detail", pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)


class POSDetailView(InventoryListMixin, DetailView):
    page = "inventory.pos_sales"
    model = POSMaster
    template_name = "inventory/pos_detail.html"
    context_object_name = "sale"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_form"] = POSDetailForm()
        items = self.object.items.all()
        bill_amount = sum((i.total_price or Decimal("0") for i in items), Decimal("0"))
        discount_total = sum((i.discount_amount or Decimal("0") for i in items), Decimal("0"))
        tax_total = sum((i.tax_amount or Decimal("0") for i in items), Decimal("0"))
        net_amount = bill_amount - discount_total + tax_total
        context["bill_amount"] = bill_amount
        context["discount_total"] = discount_total
        context["tax_total"] = tax_total
        context["net_amount"] = net_amount
        context["payable_amount"] = net_amount
        return context


class POSReturnQuickCreateView(InventoryManageMixin, View):
    page = "inventory.pos_returns"
    action = "add"
    def post(self, request):
        sale_id = request.POST.get("pos_master")
        if not sale_id:
            messages.error(request, "Select a sale first.")
            return redirect("inventory:pos_return_list")

        sale = get_object_or_404(POSMaster, pk=sale_id, posted=YES)
        detail_ids = request.POST.getlist("detail_id")
        return_qtys = request.POST.getlist("return_qty")

        lines = []
        for i, detail_id in enumerate(detail_ids):
            if not detail_id:
                continue
            qty = Decimal(return_qtys[i] or "0").quantize(Decimal("0.0001"))
            if qty <= 0:
                continue
            lines.append((int(detail_id), qty))

        if not lines:
            messages.error(request, "Select at least one item with return quantity.")
            return redirect("inventory:pos_return_list")

        pay_mode = request.POST.get("pay_mode") or "cash"
        adjusted_amount = Decimal(request.POST.get("adjusted_amount") or "0").quantize(Decimal("0.01"))
        return_date = request.POST.get("return_date") or timezone.localdate()

        with transaction.atomic():
            sale_return = POSReturnMaster.objects.create(
                transaction_id=generate_transaction_id("SRT", POSReturnMaster),
                pos_master=sale,
                return_date=return_date,
                pay_mode=pay_mode,
                adjusted_amount=adjusted_amount,
                created_by=request.user,
                updated_by=request.user,
            )
            for detail_id, qty in lines:
                pos_detail = get_object_or_404(POSDetail, pk=detail_id, pos_master=sale)
                if qty > pos_detail.quantity:
                    messages.error(request, f"{pos_detail.item_name}: return qty ({qty}) cannot exceed sale qty ({pos_detail.quantity}).")
                    return redirect("inventory:pos_return_list")
                POSReturnDetail.objects.create(
                    pos_return_master=sale_return,
                    pos_detail=pos_detail,
                    quantity=qty,
                    created_by=request.user,
                    updated_by=request.user,
                )

        try:
            post_sale_return(sale_return=sale_return, user=request.user)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("inventory:pos_return_list")

        messages.success(request, f"Sale return {sale_return.return_num} posted — stock updated.")
        return redirect("inventory:pos_return_receipt", pk=sale_return.pk)


class POSReturnReceiptView(PrintContextMixin, InventoryListMixin, DetailView):
    page = "inventory.pos_returns"
    model = POSReturnMaster
    template_name = "inventory/pos_return_receipt.html"
    context_object_name = "sale_return"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = self.object.items.all()
        context["items"] = items
        context["total_qty"] = sum((i.quantity or Decimal("0") for i in items), Decimal("0"))
        context["total_return"] = sum((i.net_total or Decimal("0") for i in items), Decimal("0"))
        return context


class POSReturnListView(InventoryListMixin, ListView):
    page = "inventory.pos_returns"
    template_name = "inventory/pos_return_list.html"
    context_object_name = "returns"
    queryset = POSReturnMaster.objects.select_related("pos_master", "customer").filter(posted=YES).order_by("-return_date", "-id")
    search_fields = ("return_num", "transaction_id", "sale_num")
    date_filters = [{"field": "return_date", "label": "Return date"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        returned_sale_ids = POSReturnMaster.objects.filter(posted=YES).values_list("pos_master_id", flat=True)
        sales = POSMaster.objects.filter(posted=YES).exclude(pk__in=returned_sale_ids).prefetch_related("items__inventory_item").order_by("-sale_date", "-id")
        sales_json = []
        sale_items_json = {}
        for sale in sales:
            sales_json.append({
                "id": sale.pk,
                "sale_num": sale.sale_num,
                "customer": sale.customer.customer_name if sale.customer_id else "",
                "date": str(sale.sale_date),
                "net_amount": float(sale.net_amount),
            })
            sale_items_json[sale.pk] = [
                {
                    "id": item.pk,
                    "item_name": item.item_name,
                    "item_code": item.item_code,
                    "qty": float(item.quantity),
                    "price": float(item.price),
                    "net_total": float(item.net_total),
                }
                for item in sale.items.all()
            ]
        context["sales_json"] = sales_json
        context["sale_items_json"] = sale_items_json
        context["today"] = timezone.localdate()
        return context


class POSReturnCreateView(InventoryManageMixin, CreateView):
    page = "inventory.pos_returns"
    model = POSReturnMaster
    form_class = POSReturnMasterForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:pos_return_list")
    success_message = "Sale return saved."
    extra_context = {"title": "POS Return"}

    def form_valid(self, form):
        if not form.instance.transaction_id:
            form.instance.transaction_id = generate_transaction_id("SRT", POSReturnMaster)
        return super().form_valid(form)


class POSReturnDetailView(InventoryListMixin, DetailView):
    page = "inventory.pos_returns"
    model = POSReturnMaster
    template_name = "inventory/pos_return_detail.html"
    context_object_name = "sale_return"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = POSReturnDetailForm()
        form.fields["pos_detail"].queryset = self.object.pos_master.items.all()
        context["item_form"] = form
        return context


class POSReturnItemCreateView(InventoryManageMixin, View):
    page = "inventory.pos_returns"
    action = "add"
    def post(self, request, pk):
        sale_return = get_object_or_404(POSReturnMaster, pk=pk)
        if sale_return.posted == YES:
            messages.error(request, "Posted sale return cannot be updated.")
            return redirect("inventory:pos_return_detail", pk=pk)
        form = POSReturnDetailForm(request.POST)
        form.fields["pos_detail"].queryset = sale_return.pos_master.items.all()
        if form.is_valid():
            item = form.save(commit=False)
            item.pos_return_master = sale_return
            item.created_by = request.user
            item.updated_by = request.user
            item.save()
            messages.success(request, "Return item saved.")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return redirect("inventory:pos_return_detail", pk=pk)


class POSReturnPostView(InventoryManageMixin, View):
    page = "inventory.pos_returns"
    action = "edit"
    def post(self, request, pk):
        record = get_object_or_404(POSReturnMaster, pk=pk)
        try:
            post_sale_return(sale_return=record, user=request.user)
            messages.success(request, "Sale return posted and stock updated.")
        except ValidationError as exc:
            messages.error(request, exc)
        return redirect("inventory:pos_return_detail", pk=pk)


class PurchaseReturnListView(SortableListMixin, InventoryListMixin, ListView):
    page = "inventory.purchase_returns"
    template_name = "inventory/purchase_return_list.html"
    context_object_name = "returns"
    paginate_by = 25
    queryset = (
        PurchaseReturnMaster.objects
        .select_related("purchase_invoice", "purchase_order", "supplier")
        .order_by("-return_date", "-id")
    )
    search_fields = ("return_num", "supplier__name", "purchase_invoice__invoice_num",
                     "purchase_invoice__supplier_invoice_num", "purchase_order__purchase_num", "remarks")
    filter_fields = {"supplier": "supplier_id", "godown": "purchase_invoice__godown_id"}
    date_filters = [{"field": "return_date", "label": "Return date"}]
    sort_fields = {
        "return_num": "return_seq_num",
        "return_date": ("return_date", "id"),
        "supplier": "supplier__name",
        "invoice": "purchase_invoice__seq_num",
        "order": "purchase_order__seq_num",
        "status": "status",
        "value": ("returned_amount", "id"),
    }
    default_sort = "return_date"
    default_sort_dir = "desc"

    PER_PAGE_OPTIONS = (10, 25, 50, 100)
    TAB_FILTERS = {
        RETURN_TAB_DRAFT: {"status__in": INV_RETURN_DRAFT_STATUSES},
        RETURN_TAB_POSTED: {"status": STATUS_POSTED},
        RETURN_TAB_REVERSED: {"status": STATUS_REVERSED},
    }

    def current_tab(self):
        tab = self.request.GET.get("tab", RETURN_TAB_ALL)
        return tab if tab in dict(RETURN_TABS) else RETURN_TAB_ALL

    def get_paginate_by(self, queryset):
        raw = (self.request.GET.get("per_page") or "").strip()
        if raw.isdigit() and int(raw) in self.PER_PAGE_OPTIONS:
            return int(raw)
        return self.paginate_by

    def filtered_queryset(self):
        return super().get_queryset()

    def get_queryset(self):
        queryset = self.filtered_queryset()
        rule = self.TAB_FILTERS.get(self.current_tab())
        if rule:
            queryset = queryset.filter(**rule)
        return queryset.prefetch_related("items__inventory_item", "items__uom")

    def get_filter_specs(self):
        supplier_choices = list(
            Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("id", "name")
        )
        return [
            {"name": "supplier", "label": "All suppliers", "short_label": "Supplier",
             "choices": supplier_choices, "value": self.request.GET.get("supplier", "")},
            {"name": "godown", "label": "All godowns", "short_label": "Godown",
             "choices": list(godown_options().values_list("id", "name")),
             "value": self.request.GET.get("godown", "")},
        ]

    def tiles(self):
        base = self.filtered_queryset().order_by()
        zero = Decimal("0.00")

        def figures(queryset):
            row = queryset.aggregate(count=Count("id"), value=Sum("returned_amount"))
            return row["count"] or 0, row["value"] or zero

        today = timezone.localdate()
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        all_count, all_value = figures(base)
        draft_count, draft_value = figures(base.filter(status__in=INV_RETURN_DRAFT_STATUSES))
        posted_count, posted_value = figures(base.filter(status=STATUS_POSTED))
        reversed_count, reversed_value = figures(base.filter(status=STATUS_REVERSED))
        month_count, month_value = figures(base.filter(status=STATUS_POSTED, return_date__range=(month_start, month_end)))
        return {
            "all_count": all_count, "all_value": all_value,
            "draft_count": draft_count, "draft_value": draft_value,
            "posted_count": posted_count, "posted_value": posted_value,
            "reversed_count": reversed_count, "reversed_value": reversed_value,
            "month_count": month_count, "month_value": month_value,
            "month_from": month_start.isoformat(), "month_to": month_end.isoformat(),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        carried = self.request.GET.copy()
        for key in ("tab", "page"):
            carried.pop(key, None)
        context["base_query"] = carried.urlencode()
        current = self.current_tab()
        tiles = self.tiles()
        counts = {
            RETURN_TAB_ALL: tiles["all_count"], RETURN_TAB_DRAFT: tiles["draft_count"],
            RETURN_TAB_POSTED: tiles["posted_count"], RETURN_TAB_REVERSED: tiles["reversed_count"],
        }
        context["tabs"] = [
            {"key": key, "label": label, "on": key == current, "count": counts[key]}
            for key, label in RETURN_TABS
        ]
        context["current_tab"] = current
        context["tiles"] = tiles
        context["per_page"] = self.get_paginate_by(None)
        context["per_page_options"] = list(self.PER_PAGE_OPTIONS)
        context["filters_active"] = any(
            (self.request.GET.get(key) or "").strip()
            for key in ("q", "supplier", "godown", "date_from", "date_to", "tab")
        )
        columns = RETURN_COLUMNS.visible(self.request.session)
        context["columns"] = columns
        context["row_span"] = len(columns) + 2
        context["foot_span"] = len(columns) - sum(1 for key in ("lines", "quantity", "status") if key in columns)
        context["column_menu"] = RETURN_COLUMNS.menu(self.request.session)
        context["columns_url"] = reverse_lazy("inventory:purchase_return_columns")
        context["export_url"] = reverse_lazy("inventory:purchase_return_export")
        context["reversal_reasons"] = INV_REVERSAL_REASONS
        context["draft_statuses"] = INV_RETURN_DRAFT_STATUSES
        page_qty = Decimal("0")
        page_total = Decimal("0.00")
        for row in context["returns"]:
            lines = list(row.items.all())
            row.line_count = len(lines)
            row.qty_total = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
            page_qty += row.qty_total
            page_total += row.returned_amount or Decimal("0.00")
        context["page_qty"] = page_qty
        context["page_total"] = page_total
        return context


class PurchaseReturnExportView(InventoryListMixin, TableExportView):
    page = "inventory.purchase_returns"
    columns = RETURN_COLUMNS
    filename = "purchase-returns"
    title = "Purchase Returns"

    def get_rows(self):
        listing = PurchaseReturnListView(request=self.request, kwargs={}, args=())
        rows = list(listing.get_queryset())
        for row in rows:
            lines = list(row.items.all())
            row.line_count = len(lines)
            row.qty_total = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
        return rows


class PurchaseReturnColumnsView(InventoryListMixin, View):
    page = "inventory.purchase_returns"

    def post(self, request, *args, **kwargs):
        RETURN_COLUMNS.choose(request.session, request.POST.getlist("columns"))
        carried = request.POST.get("back", "")
        query = urlencode([
            (key, value) for key, value in parse_qsl(carried, keep_blank_values=False)
            if key in ("q", "tab", "supplier", "godown", "date_from", "date_to", "per_page", "page")
        ])
        target = reverse_lazy("inventory:purchase_return_list")
        return redirect(f"{target}?{query}" if query else str(target))


class PurchaseReturnOptionsView(InventoryListMixin, View):
    page = "inventory.purchase_returns"

    def get(self, request, *args, **kwargs):
        invoice_id = (request.GET.get("invoice") or "").strip()
        if invoice_id.isdigit():
            invoice = get_object_or_404(
                PurchaseInvoice.objects.select_related("supplier", "purchase_order"), pk=invoice_id, status=STATUS_POSTED
            )
            lines = purchase_return_lines(invoice)
            return JsonResponse({
                "invoice": {
                    "id": invoice.pk, "number": invoice.invoice_num, "date": invoice.invoice_date.strftime("%d-%m-%Y"),
                    "supplier": invoice.supplier_id,
                    "order": invoice.purchase_order.purchase_num if invoice.purchase_order_id else "",
                },
                "lines": [
                    {
                        "id": line.pk, "item": line.descr or line.inventory_item.item_name,
                        "code": line.inventory_item.code, "unit": uom_title(line),
                        "invoiced": str(line.quantity), "returned": str(line.qty_returned),
                        "returnable": str(line.qty_returnable), "rate": str(line.rate),
                    }
                    for line in lines
                ],
            })

        supplier_id = (request.GET.get("supplier") or "").strip()
        if not supplier_id.isdigit():
            return JsonResponse({"invoices": []})
        invoices = list(
            PurchaseInvoice.objects.filter(supplier_id=supplier_id, status=STATUS_POSTED)
            .select_related("purchase_order").order_by("-invoice_date", "-id")[:100]
        )
        rows = []
        for invoice in invoices:
            lines = purchase_return_lines(invoice)
            returnable = sum((line.qty_returnable for line in lines), Decimal("0"))
            rows.append({
                "id": invoice.pk, "number": invoice.invoice_num,
                "supplier_ref": invoice.supplier_invoice_num,
                "date": invoice.invoice_date.strftime("%d-%m-%Y"),
                "order": invoice.purchase_order.purchase_num if invoice.purchase_order_id else "",
                "total": str(invoice.total_amount),
                "lines": len([line for line in lines if line.qty_returnable > 0]),
                "mill_only": not lines,
                "disabled": returnable <= 0,
            })
        return JsonResponse({"invoices": rows})


class PurchaseReturnCreateView(InventoryManageMixin, View):
    page = "inventory.purchase_returns"
    action = "add"
    template_name = "inventory/purchase_return_form.html"

    def _render(self, request, posted, posted_lines=None, status=200):
        return render(request, self.template_name, {
            "suppliers": Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name"),
            "next_number": next_purchase_return_number(),
            "today": timezone.localdate(),
            "posted": posted,
            "posted_lines": posted_lines or {},
            "options_url": reverse("inventory:purchase_return_options"),
            "list_url": reverse("inventory:purchase_return_list"),
            "can_post": user_has_permission(request.user, f"{self.page}.edit"),
        }, status=status)

    def get(self, request, *args, **kwargs):
        posted = {}
        invoice_id = (request.GET.get("invoice") or "").strip()
        if invoice_id.isdigit():
            invoice = PurchaseInvoice.objects.filter(pk=invoice_id, status=STATUS_POSTED).first()
            if invoice:
                posted = {"supplier": str(invoice.supplier_id), "purchase_invoice": str(invoice.pk)}
        return self._render(request, posted)

    def post(self, request, *args, **kwargs):
        posted = request.POST
        posted_lines = {}
        lines = []
        for line_id, raw in zip(posted.getlist("line_id"), posted.getlist("return_qty")):
            if not line_id.isdigit() or not (raw or "").strip():
                continue
            posted_lines[line_id] = raw
            try:
                lines.append((int(line_id), decimal_of(raw)))
            except InvalidOperation:
                messages.error(request, "A return quantity is not a number.")
                return self._render(request, posted, posted_lines, status=400)

        invoice = PurchaseInvoice.objects.filter(pk=(posted.get("purchase_invoice") or "0").strip() or 0).first()
        if invoice is None:
            messages.error(request, "Pick the purchase invoice the goods came in on.")
            return self._render(request, posted, posted_lines, status=400)
        if str(invoice.supplier_id) != (posted.get("supplier") or "").strip():
            messages.error(request, "That invoice is not from the supplier picked.")
            return self._render(request, posted, posted_lines, status=400)

        post_now = posted.get("action") == "post"
        if post_now and not user_has_permission(request.user, f"{self.page}.edit"):
            messages.error(request, "You can save this return as a draft, but not post it.")
            return self._render(request, posted, posted_lines, status=403)

        try:
            purchase_return = create_purchase_return(
                invoice=invoice,
                lines=lines,
                return_date=parse_date(posted.get("return_date") or "") or timezone.localdate(),
                remarks=(posted.get("remarks") or "").strip(),
                post=post_now,
                user=request.user,
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
            return self._render(request, posted, posted_lines, status=400)

        state = "posted" if post_now else "saved as draft"
        messages.success(request, f"{purchase_return.return_num} {state}.")
        return redirect("inventory:purchase_return_detail", pk=purchase_return.pk)


class PurchaseReturnReceiptView(PrintContextMixin, InventoryListMixin, DetailView):
    page = "inventory.purchase_returns"
    model = PurchaseReturnMaster
    template_name = "inventory/purchase_return_receipt.html"
    context_object_name = "pr"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(self.object.items.select_related("inventory_item").all())
        context["items"] = items
        context["total_qty"] = sum(i.quantity for i in items)
        context["total_return"] = self.object.returned_amount
        context["amount_in_words"] = amount_in_words(self.object.returned_amount)
        context["print_back_url"] = reverse_lazy("inventory:purchase_return_detail", kwargs={"pk": self.object.pk})
        return context


class PurchaseReturnDetailView(InventoryListMixin, DetailView):
    page = "inventory.purchase_returns"
    model = PurchaseReturnMaster
    template_name = "inventory/purchase_return_detail.html"
    context_object_name = "purchase_return"
    queryset = (
        PurchaseReturnMaster.objects
        .select_related("purchase_invoice", "purchase_invoice__godown", "purchase_order", "supplier", "created_by")
        .prefetch_related("items__inventory_item", "items__uom")
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        record = self.object
        lines = list(record.items.all())
        context["lines"] = lines
        context["qty_total"] = sum((line.quantity or Decimal("0") for line in lines), Decimal("0"))
        context["goods_total"] = sum((line.total_price or Decimal("0.00") for line in lines), Decimal("0.00"))
        context["is_draft"] = record.status in INV_RETURN_DRAFT_STATUSES and record.posted != YES
        context["is_posted"] = record.status == STATUS_POSTED
        context["reversal_reasons"] = INV_REVERSAL_REASONS
        context["reverse_reason_label"] = dict(INV_REVERSAL_REASONS).get(record.reverse_reason, "")
        context["list_url"] = reverse_lazy("inventory:purchase_return_list")
        links = [{
            "kind": "Purchase Invoice",
            "label": record.purchase_invoice.invoice_num,
            "url": reverse("inventory:purchase_invoice_detail", args=[record.purchase_invoice_id]),
            "dead": record.purchase_invoice.status == STATUS_REVERSED,
        }]
        if record.purchase_order_id:
            links.append({
                "kind": "Purchase Order",
                "label": record.purchase_order.purchase_num,
                "url": reverse("inventory:purchase_order_detail", args=[record.purchase_order_id]),
                "dead": False,
            })
        context["linked_documents"] = links
        return context


class PurchaseReturnPostView(InventoryManageMixin, View):
    page = "inventory.purchase_returns"
    action = "edit"

    def post(self, request, pk):
        record = get_object_or_404(PurchaseReturnMaster, pk=pk)
        try:
            record = post_purchase_return(purchase_return=record, user=request.user)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, f"{record.return_num} posted.")
        return redirect(request.POST.get("next") or reverse("inventory:purchase_return_detail", args=[pk]))


class PurchaseReturnReverseView(InventoryManageMixin, View):
    page = "inventory.purchase_returns"
    action = "edit"

    def post(self, request, pk):
        record = get_object_or_404(PurchaseReturnMaster, pk=pk)
        try:
            reverse_purchase_return(
                purchase_return=record, reason=(request.POST.get("reason") or "").strip(), user=request.user,
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, f"{record.return_num} reversed.")
        return redirect(request.POST.get("next") or reverse("inventory:purchase_return_detail", args=[pk]))


def balance_of_grn_clearing():
    """What the GRN clearing account is holding right now.

    Read straight off the posted voucher lines rather than from a stored total,
    so the figure on the screen cannot drift from the ledger it claims to show.
    """
    from apps.core.constants import GL_GRN_CLEARING_PATH
    from apps.finance.services import gl_account

    account = gl_account(GL_GRN_CLEARING_PATH)
    rows = AccountVoucherLine.objects.filter(account_no=account.code).aggregate(
        debit=Sum("debit_amount"), credit=Sum("credit_amount")
    )
    return (rows["debit"] or Decimal("0")) - (rows["credit"] or Decimal("0"))


class WheatPurchaseEntryView(InventoryManageMixin, View):
    """The gate's own wheat purchase slip, laid out the way the mill writes it.

    A separate screen from the general purchase invoice on purpose. A stores
    purchase is a list of lines; a wheat purchase is one item, weighed twice,
    argued over at the gate, with the sacks it arrived in priced beside it. The
    two do not fit one grid without making both worse.

    Read-only for now: it renders, calculates and previews what it would post,
    and the save endpoint is deliberately not wired yet.
    """

    page = "inventory.purchase_orders"
    action = "add"
    template_name = "inventory/wheat_purchase_form.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context())

    def post(self, request, *args, **kwargs):
        """Save the slip, answering in JSON so the screen never reloads.

        The gate types this at night on a connection that drops; a reload would
        empty a filled form. Everything the clerk entered stays in the page, and
        a failure comes back as something he can read and act on.
        """
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return JsonResponse({"errors": ["The entry could not be read. Try saving again."]}, status=400)

        def weight(name):
            """A weight box, or None where the clerk left it blank.

            Blank is not zero here: a tare that was never taken and a tare of
            zero are different facts, and only one of them belongs on the slip.
            """
            raw = str(payload.get(name) or "").replace(",", "").strip()
            if not raw:
                return None
            try:
                return Decimal(raw)
            except InvalidOperation:
                return None

        def money(name):
            return weight(name) or Decimal("0.00")

        supplier = Supplier.objects.filter(pk=payload.get("supplier") or 0, status=STATUS_ACTIVE).first()
        wheat = wheat_product_options().filter(pk=payload.get("wheat_product") or 0).first()
        if not supplier:
            return JsonResponse({"errors": ["Choose the sender before saving."]}, status=400)
        if not wheat:
            return JsonResponse({"errors": ["Choose the wheat item before saving."]}, status=400)

        bag_ids = {row.pk: row for row in bardana_product_options()}
        bardana_lines, sack_deduction = [], Decimal("0.000")
        for row in payload.get("bardana") or []:
            product = bag_ids.get(int(row.get("product") or 0))
            if product is None:
                continue
            qty = Decimal(str(row.get("qty") or "0").replace(",", "") or "0")
            if qty <= 0:
                continue
            per_bag = Decimal(str(row.get("ded_per_bag") or "0").replace(",", "") or "0")
            sack_deduction += qty * per_bag
            bardana_lines.append({
                "product": product,
                "quantity": qty,
                "rate": Decimal(str(row.get("rate") or "0").replace(",", "") or "0"),
                "bardana_ownership": (row.get("ownership") or "").strip(),
            })

        party_net, mill_net = None, None
        if weight("party_load") is not None:
            party_net = (weight("party_load") or Decimal("0")) - (weight("party_tare") or Decimal("0"))
        if weight("mill_load") is not None:
            mill_net = (weight("mill_load") or Decimal("0")) - (weight("mill_tare") or Decimal("0"))

        wheat_line = {
            "product": wheat,
            "party_load_weight": weight("party_load"),
            "party_tare_weight": weight("party_tare"),
            "mill_load_weight": weight("mill_load"),
            "mill_tare_weight": weight("mill_tare"),
            "party_weight": party_net,
            "mill_weight": mill_net,
            "selected_weight": weight("selected_weight"),
            "katla": weight("katla"),
            "khoot": weight("impurities"),
            "moisture": weight("moisture"),
            "sack_weight_deduction": sack_deduction or None,
            "rate_per_mund": weight("rate_per_mund"),
        }

        text_payload = {key: ("" if value is None else str(value)) for key, value in payload.items()
                        if not isinstance(value, (list, dict))}

        try:
            from apps.godowns.models import Godown

            invoice = create_purchase_invoice(
                supplier=supplier,
                supplier_invoice_num="",
                invoice_date=parse_date(payload.get("voucher_date") or "") or timezone.localdate(),
                lines=[wheat_line] + bardana_lines,
                freight_amount=money("freight"),
                freight_paid_by_mill=True,
                brokerage_borne_by_supplier=True,
                remarks=(payload.get("remark") or "").strip(),
                godown=picked(text_payload, "godown", Godown.objects.filter(status=STATUS_ACTIVE)),
                vehicle_no=(payload.get("vehicle_no") or "").strip()[:30],
                broker=picked(text_payload, "broker", broker_options()),
                brokerage_rate_per_100kg=money("brokerage_rate"),
                withholding_rate_per_40kg=money("withholding_rate"),
                extra_data={
                    key: (payload.get(key) or "").strip()
                    for key in ("transporter", "driver_phone", "builty_no")
                    if (payload.get(key) or "").strip()
                },
                user=request.user,
            )
        except ValidationError as exc:
            return JsonResponse({"errors": list(exc.messages)}, status=400)

        return JsonResponse({
            "invoice_num": invoice.invoice_num,
            "detail_url": reverse("inventory:purchase_invoice_detail", args=[invoice.pk]),
            "over_invoiced": invoice.extra_data.get("over_invoiced") or [],
        })

    def _context(self):
        setting = SystemSetting.get_solo()
        wheat = wheat_product_options()
        bardana = list(bardana_product_options())
        suppliers = PurchaseInvoiceCreateView._suppliers_with_balance()
        return {
            "title": "Wheat Purchase",
            "list_url": reverse_lazy("inventory:purchase_invoice_list"),
            "next_voucher_no": next_purchase_invoice_number(),
            "today": timezone.localdate(),
            "suppliers": suppliers,
            "wheat_products": wheat,
            "bardana_products": bardana,
            "brokers": broker_options(),
            "godowns": godown_options(),
            "bardana_ownership_choices": INV_BARDANA_OWNERSHIP_CHOICES,
            "default_withholding_rate": setting.wheat_withholding_rate_per_40kg,
            "default_brokerage_rate": setting.wheat_brokerage_rate_per_100kg,
            "wheat_json": json.dumps([
                {
                    "id": row.pk,
                    "code": row.complete_code,
                    "name": row.name,
                    "spec": row.specification or "",
                }
                for row in wheat
            ]),
            "bardana_json": json.dumps([
                {
                    "id": row.pk,
                    "code": row.complete_code,
                    "name": row.name,
                    "spec": row.specification or "",
                }
                for row in bardana
            ]),
            "supplier_json": json.dumps([
                {"id": row.pk, "name": row.name, "balance": float(row.balance or 0)}
                for row in suppliers
            ]),
        }
