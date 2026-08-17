import csv
import io
import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View

from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apps.core.constants import INVENTORY_KIND_PRODUCT, INVENTORY_KIND_SERVICE, INV_POS_STATUS_CHOICES, INV_PURCHASE_ORDER_STATUS_CHOICES, INV_TRANSACTION_TYPE_CHOICES, NO, RECORD_STATUS_CHOICES, STATUS_ACTIVE, STATUS_CREATED, STATUS_DRAFT, STATUS_FULLY_RECEIVED, STATUS_INACTIVE, STATUS_PARTIAL_RECEIVED, STATUS_POSTED, STATUS_RAISED, YES
from apps.access_control.selectors import user_has_permission
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, PrintContextMixin, SearchFilterPaginationMixin, SortableListMixin
from apps.finance.models import AccountVoucherLine, ChartOfAccount
from apps.finance.services import account_balances, account_ledger, create_customer_receivable_account, sync_supplier_opening_balance
from apps.finance.views import AuditSaveMixin

from .forms import CustomerForm, InventoryClassForm, InventoryItemForm, InventoryItemImportForm, ManualTransactionForm, POSDetailForm, POSMasterForm, POSReturnDetailForm, POSReturnMasterForm, PurchaseOrderForm, PurchaseOrderItemForm, PurchaseReturnDetailForm, PurchaseReturnMasterForm, ReceivePOForm, UOMConversionForm, UOMForm, SupplierForm
from .models import Customer, CustomerLedger, InventoryClass, InventoryItem, ItemLedger, ManualTransaction, POSDetail, POSMaster, POSReturnDetail, POSReturnMaster, PurchaseMaster, PurchaseOrder, PurchaseOrderItem, PurchaseOrderItemReceived, PurchaseReturnDetail, PurchaseReturnMaster, Stock, UOM, UOMConversion, Supplier
from .services import amount_in_words, create_direct_purchase, finalize_manual_transaction, set_opening_stock, generate_transaction_id, post_purchase_return, post_sale, post_sale_return, receive_purchase_order_item


def uom_title(record):
    """The unit shown against a record, blank where it carries none.

    An item is allowed to have no unit, so every screen that prints one has to
    survive the empty case rather than reaching through a null relation.
    """
    return record.uom.title if record and record.uom_id else ""


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
    # A picker in a scrolling panel, not a page of results.
    paginate_by = 100
    search_fields = ("title", "class_code")
    extra_context = {"title": "Item Categories", "active_tab": "category"}

    # The left row that stands for "no category at all".
    UNFILED = "none"

    def _is_ajax(self):
        return self.request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def get_queryset(self):
        # The count beside each category is what the left column shows.
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

    # ---- AJAX -----------------------------------------------------------
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
        # The dialog asks for a name only; the code is derived the same way the
        # item form derives it, so two screens never invent different codes.
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

        # An item is moved out of a category, never deleted with it, so a
        # category still holding items is refused until it is emptied.
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
    # The list is a picker in a scrolling panel, not a page of results, so it
    # holds a full alphabet rather than ten rows.
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
        # The base is the unit already open on the left; only the other side is
        # a choice, and it can never be the same unit.
        form.fields["uom_from"].queryset = UOM.objects.filter(pk=selected_uom.pk) if selected_uom else UOM.objects.none()
        form.fields["uom_to"].queryset = UOM.objects.exclude(pk=selected_uom.pk) if selected_uom else UOM.objects.none()
        if selected_uom and not form.is_bound:
            form.initial.setdefault("uom_from", selected_uom.pk)
        return form

    # ---- AJAX plumbing ---------------------------------------------------
    # The screen never navigates: it asks for the two panes and swaps them in.
    # Every handler answers JSON to an AJAX caller; a plain request still gets
    # the whole page, which is what the first load and a reload go through.

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
        # Only the modal that was submitted needs to know, and it is on screen
        # already, so the errors go back on their own.
        if self._is_ajax():
            return JsonResponse({"ok": False, "errors": self._errors(form)}, status=400)
        for errors in form.errors.values():
            for error in errors:
                messages.error(self.request, error)
        return self._redirect_to_unit(self.get_selected_uom())

    def post(self, request, *args, **kwargs):
        # The list itself only needs index rights; writing needs add.
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
        # A posted id edits that unit; without one this is a new one.
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
            # A unit saved from here becomes the one on show.
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

        # Its own conversions are not a reason to stop -- they go with it --
        # but a conversion that something else uses is, so they are checked in
        # their own right below.
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

        # A posted id edits that row; without one this is a new conversion, so
        # a unit can carry as many as it needs.
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
        # The secondary-unit picker is built once and reused for every unit, so
        # it carries the whole list and hides the base unit in script.
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
            # The units screen refreshes its own panes, so it only needs the word.
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
    # Newest first: a supplier just added is the one being looked for.
    queryset = Supplier.objects.select_related("city").order_by("-id")
    search_fields = ("name", "code", "email", "tel1")
    sort_fields = {"name": "name", "code": "code", "city": "city__title", "status": ("status", "name"), "added": "-id"}
    # Rolled up per row after the query, so the database cannot order by it.
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
        # One query per kind for the whole page rather than per expanded row:
        # the panels are open by default, so every row's figures are needed.
        purchases = {
            row["supplier_id"]: row
            for row in PurchaseMaster.objects.filter(supplier__in=suppliers)
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
        # A supplier's payable account is named after them, so the ledger the
        # panel links to is found the same way the posting created it.
        payable_codes = dict(
            ChartOfAccount.objects.filter(title__in=[supplier.name for supplier in suppliers])
            .values_list("title", "code")
        )
        balances = account_balances()

        # Every supplier's ledger in one pass: the panels are ledgers, and one
        # query per open panel would be a query per row.
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

        # The payable column is computed above, so its sort happens here.
        context["records"] = self.sort_rows(suppliers)
        # The tiles report the whole filtered set, not just the page in front of
        # you: "10 suppliers" on page 1 of 4 would be a lie.
        all_suppliers = self.get_queryset()
        context["supplier_count"] = all_suppliers.count()
        context["purchased_total"] = (
            PurchaseMaster.objects.filter(supplier__in=all_suppliers).aggregate(total=Sum("total_amount"))["total"] or zero
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

        bought = PurchaseMaster.objects.filter(supplier=supplier).aggregate(total=Sum("total_amount"), count=Count("id"))
        sent_back = PurchaseReturnMaster.objects.filter(supplier=supplier).aggregate(total=Sum("returned_amount"), count=Count("id"))
        context["purchase_total"] = bought["total"] or zero
        context["purchase_count"] = bought["count"] or 0
        context["return_total"] = sent_back["total"] or zero
        context["return_count"] = sent_back["count"] or 0
        context["order_count"] = PurchaseOrder.objects.filter(supplier=supplier).count()
        context["recent_receipts"] = PurchaseMaster.objects.filter(supplier=supplier).order_by("-id")[:10]

        # The supplier's payable account is named after them, the same way the
        # posting created it, so the ledger here is the ledger the books hold.
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


class SupplierCreateView(InventoryManageMixin, CreateView):
    page = "inventory.suppliers"
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/supplier_form.html"
    success_url = reverse_lazy("inventory:supplier_list")
    success_message = "Supplier saved."
    extra_context = {
        "title": "Supplier",
        # Name, phone, address and the credit block are placed by hand; the rest
        # are grouped behind their own tabs so the first screen stays short.
        "registration_fields": ("code", "ntn_number", "sale_tax_num", "web_url"),
        "extra_fields": ("fax", "tel2", "status", "supplier_current_status", "remarks"),
    }

    def form_valid(self, form):
        response = super().form_valid(form)
        # The opening balance belongs in the ledger, not only on the master.
        sync_supplier_opening_balance(supplier=self.object, user=self.request.user)
        return response

    def get_success_url(self):
        # "Save & New" is for entering suppliers in a run: it comes straight back
        # to an empty form instead of the list.
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
    # The stock row carries its own copy of the code and name, and is what a
    # search for a stocked item is likely typed against.
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
            # Valued at the current price, the same figure the Inventory control
            # account is reconciled against.
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
        # Items are the subsidiary ledger behind the balance sheet's Inventory
        # account, so the page states whether the two currently agree.
        from apps.finance.services import inventory_control_summary  # lazy: finance imports inventory

        context = super().get_context_data(**kwargs)
        context["title"] = "Services" if context["is_service_tab"] else "Inventory Items"
        context["create_url"] = reverse_lazy("inventory:item_create")
        # A service holds no stock, so the Inventory control banner belongs only
        # on the products tab, where the figures it reconciles are shown.
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
        # Excel reads a UTF-8 CSV correctly only when it starts with the BOM.
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
        # utf-8-sig: a CSV saved by Excel carries a BOM, which would otherwise
        # become part of the first header name.
        text = upload.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = [(name or "").strip().lower() for name in (reader.fieldnames or [])]
        rows = [{(k or "").strip().lower(): str(v or "").strip() for k, v in raw.items() if k} for raw in reader]
        return headers, rows

    @staticmethod
    def _read_xlsx(upload):
        """(header names, row dicts) from the first sheet of an .xlsx upload."""
        from openpyxl import load_workbook

        # data_only: a sheet built with formulas hands over the cached results
        # rather than "=A1*2". read_only keeps a long sheet off the heap.
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
                    # A price typed as a number arrives as 100.0; str() of that
                    # is still what the item form parses, so no rounding here.
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
            # Anything openpyxl throws on a corrupt or mislabelled workbook.
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
                    # A blank unit column is allowed, an unreadable one is not:
                    # silently dropping a typo would file the item unmeasured.
                    if not uom and (row.get("uom") or "").strip():
                        errors.append(f"Row {line_no}: unknown UOM '{row.get('uom', '')}'.")
                        continue

                    existing = InventoryItem.objects.filter(item_name__iexact=row.get("item_name", "")).first()
                    if existing and not update_existing:
                        errors.append(f"Row {line_no}: '{existing.item_name}' already exists.")
                        continue

                    data = {
                        "item_name": row.get("item_name", ""),
                        # Left blank on purpose: the model derives the code from
                        # the class prefix, so imports match hand-added items.
                        "code": existing.code if existing else "",
                        "category": item_class.title,
                        "uom": uom.pk,
                        "item_bar_code": row.get("item_bar_code", ""),
                        "price": row.get("price") or "0",
                        "purchase_price": row.get("purchase_price") or "0",
                        # Bulk-loaded rows are stocked goods; a service is added
                        # one at a time from the Add Item screen.
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
                    # Nothing is kept when any row failed, so the file can be
                    # corrected and re-uploaded without hunting for duplicates.
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
            # Excel reads a UTF-8 CSV correctly only when it starts with the BOM.
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


class DirectPurchaseCreateView(InventoryManageMixin, View):
    """Enter a supplier bill without raising an order first.

    The screen is one form: the party at the top, the goods in the middle, the
    money at the bottom. Everything it posts goes through the same service the
    ordered route uses, so there is one set of books either way.
    """

    page = "inventory.purchase_orders"
    action = "add"
    template_name = "inventory/direct_purchase_form.html"

    def _context(self, **extra):
        items = InventoryItem.objects.select_related("uom", "stock").filter(status=STATUS_ACTIVE).order_by("item_name")
        context = {
            "title": "Purchase",
            "suppliers": Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name"),
            "units": UOM.objects.order_by("title"),
            "today": timezone.localdate(),
            "items_json": json.dumps([
                {
                    "id": item.pk,
                    "name": item.item_name,
                    "code": item.code,
                    "uom": item.uom_id or "",
                    "rate": float(item.purchase_price or 0),
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

        def money(name, default="0"):
            raw = (posted.get(name) or "").strip() or default
            try:
                return Decimal(raw)
            except (InvalidOperation, ValueError):
                raise ValidationError(f"{name.replace('_', ' ').title()} must be a number.")

        # The rows arrive as parallel lists, so a blank row simply drops out.
        lines = []
        item_ids = posted.getlist("item_id")
        quantities = posted.getlist("quantity")
        rates = posted.getlist("rate")
        for index, raw_id in enumerate(item_ids):
            if not (raw_id or "").strip().isdigit():
                continue
            item = InventoryItem.objects.filter(pk=raw_id).first()
            if not item:
                continue
            try:
                quantity = Decimal((quantities[index] or "0").strip() or "0")
                rate = Decimal((rates[index] or "0").strip() or "0")
            except (IndexError, InvalidOperation, ValueError):
                continue
            if quantity > 0:
                lines.append({"inventory_item": item, "quantity": quantity, "rate": rate})

        try:
            bill_date = posted.get("bill_date") or str(timezone.localdate())
            order, net = create_direct_purchase(
                supplier=supplier,
                bill_number=(posted.get("bill_number") or "").strip(),
                bill_date=bill_date,
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

        messages.success(request, f"Purchase {order.purchase_num} saved for {net}.")
        if "save_and_new" in posted:
            return redirect("inventory:direct_purchase_create")
        return redirect("inventory:purchase_order_detail", pk=order.pk)


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


class ItemCreateView(InventoryManageMixin, CreateView):
    page = "inventory.items"
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/item_form.html"
    success_url = reverse_lazy("inventory:item_list")
    success_message = "Item saved."
    # Everything the first screen does not ask for; the Other tab renders these
    # by name so the layout never silently drops a field the form still posts.
    # `conversion` is not here: the unit dialog owns it now.
    other_fields = ("item_bar_code", "imported", "inventory", "status")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Inventory Item"
        context["other_fields"] = list(self.other_fields)
        context["product_value"] = INVENTORY_KIND_PRODUCT
        context["service_value"] = INVENTORY_KIND_SERVICE
        return context

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
        return response

    def get_success_url(self):
        # "Save & New" keeps the operator on a blank form for the next item.
        if "save_and_new" in self.request.POST:
            return reverse_lazy("inventory:item_create")
        # Otherwise stay on the record just saved, so it can be checked or
        # corrected without hunting for it in the list.
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

        receive_ids = [r.ref_id for r in rows if r.ref_table == "inv_purchase_order_item_received"]
        sale_ids = [r.ref_id for r in rows if r.ref_table == "inv_pos_details"]
        receive_map = {
            rec.pk: rec.purchase_order_item.purchase_order_id
            for rec in PurchaseOrderItemReceived.objects.filter(pk__in=receive_ids).select_related("purchase_order_item")
        }
        sale_map = dict(POSDetail.objects.filter(pk__in=sale_ids).values_list("pk", "pos_master_id"))

        for row in rows:
            url = None
            if row.ref_table == "inv_manual_transaction" and row.transaction_id:
                url = reverse_lazy("inventory:manual_transaction_print", kwargs={"tx_id": row.transaction_id})
            elif row.ref_table == "inv_purchase_order_item_received" and row.ref_id in receive_map:
                url = f"{reverse_lazy('inventory:grn_print', kwargs={'pk': receive_map[row.ref_id]})}?receipts={row.ref_id}&reprint=1"
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
            return redirect("inventory:purchase_order_list")

        if not lines:
            messages.error(request, "Add at least one item before saving.")
            return redirect("inventory:purchase_order_list")

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
        return redirect(f"{reverse_lazy('inventory:purchase_order_list')}?open={order.pk}")


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
            return redirect("inventory:purchase_order_list")

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
            order.status = STATUS_RAISED
            order.updated_by = request.user
            order.save(update_fields=["status", "updated_by", "updated_at"])

        messages.success(request, f"Purchase order {order.purchase_num} raised with {len(lines)} item(s).")
        return redirect("inventory:purchase_order_print", pk=order.pk)


class PurchaseOrderRaiseView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "edit"
    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk, status=STATUS_DRAFT)
        order.status = STATUS_RAISED
        order.updated_by = request.user
        order.save(update_fields=["status", "updated_by", "updated_at"])
        messages.success(request, f"{order.purchase_num} raised.")
        return redirect(f"{reverse_lazy('inventory:purchase_order_list')}?open={order.pk}")


class PurchaseOrderListView(InventoryListMixin, ListView):
    page = "inventory.purchase_orders"
    template_name = "inventory/purchase_order_list.html"
    context_object_name = "orders"
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items__inventory_item", "items__uom").exclude(status=STATUS_FULLY_RECEIVED).order_by("-purchase_date", "-id")
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
        context["create_form"] = PurchaseOrderForm()
        po_summaries = {}
        for order in context["orders"]:
            items = list(order.items.all())
            po_summaries[order.pk] = {
                "items": len(items),
                "amount": float(sum(i.total_amount for i in items)),
                "discount": float(sum(i.discount_amount or 0 for i in items)),
            }
        context["po_summaries"] = po_summaries
        context["items_json"] = [
            {"id": i.pk, "name": i.item_name, "price": float(getattr(i, "stock", None) and i.stock.current_price or i.price), "uom": uom_title(i)}
            for i in InventoryItem.objects.select_related("uom", "stock").filter(status=STATUS_ACTIVE).order_by("item_name")
        ]
        for order in context["orders"]:
            form = PurchaseOrderItemForm()
            used_item_ids = order.items.values_list("inventory_item_id", flat=True)
            available_items = form.fields["inventory_item"].queryset.exclude(pk__in=used_item_ids).select_related("uom", "stock")
            form.fields["inventory_item"].queryset = available_items
            order.uom_map_id = f"uom-map-{order.pk}"
            form.fields["inventory_item"].widget.attrs["data-uom-source"] = order.uom_map_id
            order.add_form = form
            order.uom_map = {str(i.pk): {"uom": uom_title(i)} for i in available_items}
            order.avail_items_json = [
                {"id": i.pk, "name": i.item_name, "uom": uom_title(i), "price": float(getattr(i, "stock", None) and i.stock.current_price or i.price)}
                for i in available_items
            ]
            order.avail_items_json_id = f"avail-items-{order.pk}"
        return context


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


class PurchaseOrderCreateView(InventoryManageMixin, CreateView):
    page = "inventory.purchase_orders"
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:purchase_order_list")
    success_message = "Purchase order saved."
    extra_context = {"title": "Purchase Order"}


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        item_form = PurchaseOrderItemForm()
        used_item_ids = self.object.items.values_list("inventory_item_id", flat=True)
        available_items = item_form.fields["inventory_item"].queryset.exclude(pk__in=used_item_ids).select_related("uom")
        item_form.fields["inventory_item"].queryset = available_items
        context["item_form"] = item_form
        context["item_uom_map"] = {str(i.pk): {"name": i.item_name, "uom": uom_title(i)} for i in available_items}
        receive_form = ReceivePOForm(initial={"purchase_order_item": self.object.items.first()})
        receive_form.fields["purchase_order_item"].queryset = self.object.items.all()
        context["receive_form"] = receive_form
        return context


def redirect_after_item(request, pk):
    """Redirect back to the originating page with the PO collapsible auto-opened."""
    ref = request.META.get("HTTP_REFERER") or str(reverse_lazy("inventory:purchase_order_list"))
    parts = urlsplit(ref)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "open"]
    query.append(("open", str(pk)))
    return redirect(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), "")))


class PurchaseOrderItemCreateView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "add"
    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        if order.status == STATUS_FULLY_RECEIVED:
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
        if self.object.purchase_order.status != STATUS_RAISED:
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
        list_url = str(reverse_lazy("inventory:purchase_order_list"))
        return redirect(f"{list_url}?open={item.purchase_order_id}")


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
        context["print_back_url"] = f"{reverse_lazy('inventory:purchase_order_list')}?open={self.object.pk}"
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


class PurchaseReceiveView(InventoryManageMixin, View):
    page = "inventory.purchase_orders"
    action = "edit"
    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        form = ReceivePOForm(request.POST)
        form.fields["purchase_order_item"].queryset = order.items.all()
        if form.is_valid():
            try:
                receive_purchase_order_item(user=request.user, **form.cleaned_data)
                messages.success(request, "GRN posted and stock updated.")
            except ValidationError as exc:
                messages.error(request, exc)
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return redirect("inventory:purchase_order_detail", pk=pk)


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
        # group posted transactions by transaction_id for history table
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


class CustomerCreateView(InventoryManageMixin, CreateView):
    page = "inventory.customers"
    model = Customer
    form_class = CustomerForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:customer_list")
    success_message = "Customer saved."
    extra_context = {"title": "Customer"}

    def form_valid(self, form):
        creating = self.object is None  # None on create, set on update
        response = super().form_valid(form)
        if creating:
            node = create_customer_receivable_account(customer=self.object, user=self.request.user)
            opening_balance = form.cleaned_data.get("opening_balance")
            if node and opening_balance:
                node.opening_balance = opening_balance
                node.save(update_fields=["opening_balance", "updated_at"])
        return response


class CustomerUpdateView(CustomerCreateView, UpdateView):
    success_message = "Customer updated."


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


class GRNListView(InventoryListMixin, ListView):
    page = "inventory.grn"
    template_name = "inventory/grn_list.html"
    context_object_name = "orders"
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items__receipts").exclude(status=STATUS_FULLY_RECEIVED).order_by("-purchase_date", "-id")
    search_fields = ("purchase_num", "supplier__name", "quot_num")
    filter_fields = {"supplier": "supplier_id"}
    date_filters = [{"field": "purchase_date", "label": "Purchase date"}]

    def get_filter_specs(self):
        supplier_choices = list(Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("id", "name"))
        return [{"name": "supplier", "label": "All suppliers", "choices": supplier_choices, "value": self.request.GET.get("supplier", "")}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["grns"] = PurchaseOrderItemReceived.objects.select_related("purchase_order_item__purchase_order", "inventory_item").order_by("-receive_date", "-id")
        for order in context["orders"]:
            items = list(order.items.all())
            order.po_total = sum(i.total_amount for i in items)
            for item in items:
                remaining = (item.quantity or Decimal("0")) - (item.total_receive_qty or Decimal("0"))
                item.remaining_qty = remaining if remaining > 0 else Decimal("0")
        return context


class GRNPrintView(PrintContextMixin, InventoryListMixin, DetailView):
    page = "inventory.grn"
    model = PurchaseOrder
    template_name = "inventory/grn_print.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        receipt_pks_raw = self.request.GET.get("receipts", "")
        if receipt_pks_raw:
            pks = [p for p in receipt_pks_raw.split(",") if p.isdigit()]
            receipts = list(PurchaseOrderItemReceived.objects.filter(pk__in=pks).select_related("purchase_order_item"))
        else:
            receipts = []
            for item in self.object.items.prefetch_related("receipts").filter(status=YES):
                last = item.receipts.order_by("-id").first()
                if last:
                    receipts.append(last)
        for r in receipts:
            r.line_total = r.quantity * r.retail_price
        context["receipts"] = receipts
        context["total_qty"] = sum(r.quantity for r in receipts)
        context["grand_total"] = sum(r.line_total for r in receipts)
        context["po_total_qty"] = sum(r.purchase_order_item.quantity for r in receipts)
        context["receive_date"] = receipts[0].receive_date if receipts else timezone.localdate()
        context["prepared_by"] = self.request.user.get_full_name() or self.request.user.username
        context["is_reprint"] = self.request.GET.get("reprint") == "1"
        context["amount_in_words"] = amount_in_words(context["grand_total"])
        context["print_back_url"] = reverse_lazy("inventory:grn_list")
        return context


class GRNBulkReceiveView(InventoryManageMixin, View):
    page = "inventory.grn"
    action = "edit"
    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        today = timezone.localdate()
        errors = []
        receipt_pks = []

        try:
            freight_total = Decimal(request.POST.get("freight_charges", "").strip() or "0")
        except Exception:
            freight_total = Decimal("0")
        if freight_total < 0:
            freight_total = Decimal("0")

        # First pass: collect valid receive lines and their cost value for freight allocation.
        recv_lines = []
        for item in order.items.filter(status=YES):
            raw = request.POST.get(f"recv_qty_{item.pk}", "").strip()
            if not raw:
                continue
            try:
                qty = Decimal(raw)
            except Exception:
                continue
            if qty <= 0:
                continue
            unit_cost = item.retail_price or item.rate or Decimal("0")
            recv_lines.append((item, qty, unit_cost, qty * unit_cost))

        total_value = sum((line[3] for line in recv_lines), Decimal("0"))

        try:
            with transaction.atomic():
                allocated = Decimal("0")
                for idx, (item, qty, unit_cost, line_value) in enumerate(recv_lines):
                    if freight_total <= 0 or total_value <= 0:
                        freight_amount = Decimal("0")
                    elif idx == len(recv_lines) - 1:
                        freight_amount = (freight_total - allocated).quantize(Decimal("0.01"))
                    else:
                        freight_amount = (freight_total * line_value / total_value).quantize(Decimal("0.01"))
                        allocated += freight_amount
                    try:
                        receipt = receive_purchase_order_item(
                            purchase_order_item=item,
                            quantity=qty,
                            extra_qty=Decimal("0"),
                            retail_price=unit_cost,
                            receive_date=today,
                            invoice_num="",
                            invoice_date=None,
                            rv_number="",
                            remarks="",
                            user=request.user,
                            freight_amount=freight_amount,
                        )
                        receipt_pks.append(str(receipt.pk))
                    except ValidationError as exc:
                        errors.append(str(exc))
                if errors:
                    raise ValidationError(errors)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("inventory:grn_list")
        if receipt_pks:
            messages.success(request, f"{len(receipt_pks)} item(s) received for {order.purchase_num}.")
        return redirect(f"{reverse_lazy('inventory:grn_print', kwargs={'pk': pk})}?receipts={','.join(receipt_pks)}")


class PurchaseReturnListView(InventoryListMixin, ListView):
    page = "inventory.purchase_returns"
    template_name = "inventory/purchase_return_list.html"
    context_object_name = "returns"
    queryset = PurchaseReturnMaster.objects.filter(posted=YES).select_related("purchase_order", "supplier").order_by("-return_date", "-id")
    search_fields = ("return_num", "transaction_id", "purchase_order__purchase_num")
    filter_fields = {"supplier": "supplier_id"}
    date_filters = [{"field": "return_date", "label": "Return date"}]

    def get_filter_specs(self):
        supplier_choices = list(Supplier.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("id", "name"))
        return [{"name": "supplier", "label": "All suppliers", "choices": supplier_choices, "value": self.request.GET.get("supplier", "")}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_orders = PurchaseOrder.objects.select_related("supplier").prefetch_related("items__inventory_item", "items__uom").filter(
            status__in=[STATUS_PARTIAL_RECEIVED, STATUS_FULLY_RECEIVED]
        ).order_by("-purchase_date", "-id")
        returnable_pks = []
        for o in all_orders:
            for item in o.items.all():
                if (item.total_receive_qty or Decimal("0")) <= 0:
                    continue
                already = PurchaseReturnDetail.objects.filter(
                    purchase_return_master__purchase_order=o,
                    purchase_return_master__posted=YES,
                    inventory_item=item.inventory_item,
                ).aggregate(t=Sum("quantity"))["t"] or Decimal("0")
                if item.total_receive_qty > already:
                    returnable_pks.append(o.pk)
                    break
        orders = all_orders.filter(pk__in=returnable_pks)
        pos_json = [
            {"id": o.pk, "purchase_num": o.purchase_num, "supplier": o.supplier.name, "date": str(o.purchase_date)}
            for o in orders
        ]
        items_json = {}
        for o in orders:
            rows = []
            for i in o.items.all():
                if (i.total_receive_qty or Decimal("0")) <= 0:
                    continue
                already = PurchaseReturnDetail.objects.filter(
                    purchase_return_master__purchase_order=o,
                    purchase_return_master__posted=YES,
                    inventory_item=i.inventory_item,
                ).aggregate(t=Sum("quantity"))["t"] or Decimal("0")
                returnable = i.total_receive_qty - already
                if returnable <= 0:
                    continue
                rows.append({
                    "poi_pk": i.pk,
                    "inventory_item_pk": i.inventory_item_id,
                    "item_name": i.descr,
                    "item_code": i.inventory_item.code,
                    "recv_qty": float(returnable),
                    "rate": float(i.rate),
                    "total": float(returnable * i.rate),
                    "uom": uom_title(i),
                })
            items_json[str(o.pk)] = rows
        context["po_json"] = pos_json
        context["po_items_json"] = items_json
        context["today"] = timezone.localdate()
        return context


class PurchaseReturnQuickCreateView(InventoryManageMixin, View):
    page = "inventory.purchase_returns"
    action = "add"
    def post(self, request):
        po_pk = request.POST.get("purchase_order")
        order = get_object_or_404(PurchaseOrder, pk=po_pk)
        purchase_master = order.purchase_masters.first()
        if not purchase_master:
            messages.error(request, "No purchase master found for this PO.")
            return redirect("inventory:purchase_return_list")
        poi_pks = request.POST.getlist("poi_pk")
        return_qtys = request.POST.getlist("return_qty")
        if not poi_pks:
            messages.error(request, "No items selected.")
            return redirect("inventory:purchase_return_list")
        try:
            with transaction.atomic():
                pr = PurchaseReturnMaster(
                    transaction_id=generate_transaction_id("PRT", PurchaseReturnMaster),
                    purchase_master=purchase_master,
                    return_date=timezone.localdate(),
                    created_by=request.user,
                    updated_by=request.user,
                )
                pr.save()
                for poi_pk, qty_raw in zip(poi_pks, return_qtys):
                    try:
                        qty = Decimal(qty_raw)
                    except Exception:
                        continue
                    if qty <= 0:
                        continue
                    poi = get_object_or_404(PurchaseOrderItem, pk=poi_pk)
                    PurchaseReturnDetail.objects.create(
                        purchase_return_master=pr,
                        inventory_item=poi.inventory_item,
                        quantity=qty,
                        rate=poi.rate,
                        created_by=request.user,
                        updated_by=request.user,
                    )
                post_purchase_return(purchase_return=pr, user=request.user)
        except ValidationError as exc:
            messages.error(request, exc)
            return redirect("inventory:purchase_return_list")
        return redirect(f"{reverse_lazy('inventory:purchase_return_receipt', kwargs={'pk': pr.pk})}?po={po_pk}")


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
        context["print_back_url"] = f"{reverse_lazy('inventory:purchase_return_list')}?po={self.request.GET.get('po', '')}"
        return context


class PurchaseReturnCreateView(InventoryManageMixin, CreateView):
    page = "inventory.purchase_returns"
    model = PurchaseReturnMaster
    form_class = PurchaseReturnMasterForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:purchase_return_list")
    success_message = "Purchase return saved."
    extra_context = {"title": "Purchase Return"}

    def form_valid(self, form):
        if not form.instance.transaction_id:
            form.instance.transaction_id = generate_transaction_id("PRT", PurchaseReturnMaster)
        return super().form_valid(form)


class PurchaseReturnDetailView(InventoryListMixin, DetailView):
    page = "inventory.purchase_returns"
    model = PurchaseReturnMaster
    template_name = "inventory/purchase_return_detail.html"
    context_object_name = "purchase_return"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_form"] = PurchaseReturnDetailForm()
        return context


class PurchaseReturnItemCreateView(InventoryManageMixin, View):
    page = "inventory.purchase_returns"
    action = "add"
    def post(self, request, pk):
        record = get_object_or_404(PurchaseReturnMaster, pk=pk)
        if record.posted == YES:
            messages.error(request, "Posted purchase return cannot be updated.")
            return redirect("inventory:purchase_return_detail", pk=pk)
        form = PurchaseReturnDetailForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.purchase_return_master = record
            item.created_by = request.user
            item.updated_by = request.user
            item.save()
            messages.success(request, "Purchase return item saved.")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return redirect("inventory:purchase_return_detail", pk=pk)


class PurchaseReturnPostView(InventoryManageMixin, View):
    page = "inventory.purchase_returns"
    action = "edit"
    def post(self, request, pk):
        record = get_object_or_404(PurchaseReturnMaster, pk=pk)
        try:
            post_purchase_return(purchase_return=record, user=request.user)
            messages.success(request, "Purchase return posted and stock updated.")
        except ValidationError as exc:
            messages.error(request, exc)
        return redirect("inventory:purchase_return_detail", pk=pk)
