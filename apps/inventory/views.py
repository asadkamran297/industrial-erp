from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.core.constants import INV_POS_STATUS_CHOICES, INV_RETURN_STATUS_CHOICES, RECORD_STATUS_CHOICES, YES
from apps.core.mixins import PortalPermissionRequiredMixin, SearchFilterPaginationMixin
from apps.finance.views import AuditSaveMixin

from .forms import CustomerForm, InventoryClassForm, InventoryItemForm, POSDetailForm, POSMasterForm, POSReturnDetailForm, POSReturnMasterForm, PurchaseOrderForm, PurchaseOrderItemForm, PurchaseReturnDetailForm, PurchaseReturnMasterForm, ReceivePOForm, UOMConversionForm, UOMForm, VendorForm
from .models import Customer, InventoryClass, InventoryItem, ItemLedger, POSMaster, POSReturnMaster, PurchaseMaster, PurchaseOrder, PurchaseReturnMaster, Stock, UOM, UOMConversion, Vendor
from .services import generate_transaction_id, post_purchase_return, post_sale, post_sale_return, receive_purchase_order_item


class InventoryListMixin(SearchFilterPaginationMixin, PortalPermissionRequiredMixin):
    permission_required = "inventory.view"


class InventoryManageMixin(AuditSaveMixin, PortalPermissionRequiredMixin):
    permission_required = "inventory.manage"


class BaseSimpleListView(InventoryListMixin, ListView):
    template_name = "inventory/simple_list.html"
    context_object_name = "records"
    extra_context = {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.extra_context)
        return context


class InventoryClassListView(BaseSimpleListView):
    model = InventoryClass
    queryset = InventoryClass.objects.order_by("title")
    search_fields = ("title", "class_code")
    filter_fields = {"status": "status"}
    extra_context = {"title": "Inventory Classes", "create_url": reverse_lazy("inventory:class_create"), "edit_url_name": "inventory:class_update", "columns": [("Title", "title"), ("Code", "class_code"), ("Status", "get_status_display")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class InventoryClassCreateView(InventoryManageMixin, CreateView):
    model = InventoryClass
    form_class = InventoryClassForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:class_list")
    success_message = "Inventory class saved."
    extra_context = {"title": "Inventory Class"}


class InventoryClassUpdateView(InventoryClassCreateView, UpdateView):
    success_message = "Inventory class updated."


class UOMListView(BaseSimpleListView):
    model = UOM
    queryset = UOM.objects.order_by("title")
    search_fields = ("title", "code")
    filter_fields = {"status": "status"}
    extra_context = {"title": "Units of Measure", "create_url": reverse_lazy("inventory:uom_create"), "edit_url_name": "inventory:uom_update", "columns": [("Title", "title"), ("Code", "code"), ("Status", "get_status_display")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class UOMCreateView(InventoryManageMixin, CreateView):
    model = UOM
    form_class = UOMForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:uom_list")
    success_message = "UOM saved."
    extra_context = {"title": "UOM"}


class UOMUpdateView(UOMCreateView, UpdateView):
    success_message = "UOM updated."


class UOMConversionListView(BaseSimpleListView):
    model = UOMConversion
    queryset = UOMConversion.objects.select_related("uom_from", "uom_to").order_by("uom_from__title")
    search_fields = ("uom_from__title", "uom_to__title")
    filter_fields = {"status": "status"}
    extra_context = {"title": "UOM Conversions", "create_url": reverse_lazy("inventory:conversion_create"), "edit_url_name": "inventory:conversion_update", "columns": [("From", "uom_from"), ("To", "uom_to"), ("Factor", "conversion_factor"), ("Status", "get_status_display")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class UOMConversionCreateView(InventoryManageMixin, CreateView):
    model = UOMConversion
    form_class = UOMConversionForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:conversion_list")
    success_message = "UOM conversion saved."
    extra_context = {"title": "UOM Conversion"}


class UOMConversionUpdateView(UOMConversionCreateView, UpdateView):
    success_message = "UOM conversion updated."


class VendorListView(BaseSimpleListView):
    model = Vendor
    queryset = Vendor.objects.select_related("city").order_by("name")
    search_fields = ("name", "code", "email", "tel1")
    filter_fields = {"status": "status"}
    extra_context = {"title": "Vendors", "create_url": reverse_lazy("inventory:vendor_create"), "edit_url_name": "inventory:vendor_update", "columns": [("Name", "name"), ("Code", "code"), ("City", "city"), ("Status", "get_status_display")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class VendorCreateView(InventoryManageMixin, CreateView):
    model = Vendor
    form_class = VendorForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:vendor_list")
    success_message = "Vendor saved."
    extra_context = {"title": "Vendor"}


class VendorUpdateView(VendorCreateView, UpdateView):
    success_message = "Vendor updated."


class ItemListView(BaseSimpleListView):
    model = InventoryItem
    queryset = InventoryItem.objects.select_related("uom", "item_class").order_by("item_name")
    search_fields = ("item_name", "code", "item_bar_code")
    filter_fields = {"status": "status"}
    extra_context = {"title": "Inventory Items", "create_url": reverse_lazy("inventory:item_create"), "edit_url_name": "inventory:item_update", "columns": [("Name", "item_name"), ("Code", "code"), ("UOM", "uom"), ("Price", "price"), ("Status", "get_status_display")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class ItemCreateView(InventoryManageMixin, CreateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:item_list")
    success_message = "Item saved."
    extra_context = {"title": "Inventory Item"}


class ItemUpdateView(ItemCreateView, UpdateView):
    success_message = "Item updated."


class StockListView(InventoryListMixin, ListView):
    template_name = "inventory/stock_list.html"
    context_object_name = "stocks"
    queryset = Stock.objects.select_related("inventory_item").order_by("item_name")
    search_fields = ("item_code", "item_name", "inventory_item__code")


class LedgerListView(InventoryListMixin, ListView):
    template_name = "inventory/ledger_list.html"
    context_object_name = "ledgers"
    queryset = ItemLedger.objects.select_related("inventory_item").order_by("-transaction_date", "-id")
    search_fields = ("transaction_id", "transaction_no", "item_code", "item_name", "ref_no")


class PurchaseOrderListView(InventoryListMixin, ListView):
    template_name = "inventory/purchase_order_list.html"
    context_object_name = "orders"
    queryset = PurchaseOrder.objects.select_related("vendor").order_by("-purchase_date", "-id")
    search_fields = ("purchase_num", "vendor__name", "quot_num")
    filter_fields = {"status": "status"}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": INV_RETURN_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class PurchaseOrderCreateView(InventoryManageMixin, CreateView):
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:purchase_order_list")
    success_message = "Purchase order saved."
    extra_context = {"title": "Purchase Order"}


class PurchaseOrderUpdateView(PurchaseOrderCreateView, UpdateView):
    success_message = "Purchase order updated."

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status == "posted":
            messages.error(request, "Posted purchase order cannot be updated.")
            return redirect("inventory:purchase_order_detail", pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)


class PurchaseOrderDetailView(InventoryListMixin, DetailView):
    model = PurchaseOrder
    template_name = "inventory/purchase_order_detail.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_form"] = PurchaseOrderItemForm()
        receive_form = ReceivePOForm(initial={"purchase_order_item": self.object.items.first()})
        receive_form.fields["purchase_order_item"].queryset = self.object.items.all()
        context["receive_form"] = receive_form
        return context


class PurchaseOrderItemCreateView(InventoryManageMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        if order.status == "posted":
            messages.error(request, "Posted purchase order cannot be updated.")
            return redirect("inventory:purchase_order_detail", pk=pk)
        form = PurchaseOrderItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.purchase_order = order
            item.created_by = request.user
            item.updated_by = request.user
            item.save()
            messages.success(request, "Purchase order item saved.")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return redirect("inventory:purchase_order_detail", pk=pk)


class PurchaseReceiveView(InventoryManageMixin, View):
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


class CustomerListView(BaseSimpleListView):
    model = Customer
    queryset = Customer.objects.select_related("city").order_by("customer_name")
    search_fields = ("customer_name", "customer_code", "customer_cell_no")
    filter_fields = {"status": "status"}
    extra_context = {"title": "Customers", "create_url": reverse_lazy("inventory:customer_create"), "edit_url_name": "inventory:customer_update", "columns": [("Name", "customer_name"), ("Code", "customer_code"), ("Cell", "customer_cell_no"), ("Status", "get_status_display")]}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class CustomerCreateView(InventoryManageMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:customer_list")
    success_message = "Customer saved."
    extra_context = {"title": "Customer"}


class CustomerUpdateView(CustomerCreateView, UpdateView):
    success_message = "Customer updated."


class POSListView(InventoryListMixin, ListView):
    template_name = "inventory/pos_list.html"
    context_object_name = "sales"
    queryset = POSMaster.objects.select_related("customer").order_by("-sale_date", "-id")
    search_fields = ("sale_num", "transaction_id", "invoice_num", "customer__customer_name")
    filter_fields = {"status": "status", "posted": "posted"}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": INV_POS_STATUS_CHOICES, "value": self.request.GET.get("status", "")}] 


class POSCreateView(InventoryManageMixin, CreateView):
    model = POSMaster
    form_class = POSMasterForm
    template_name = "inventory/simple_form.html"
    success_url = reverse_lazy("inventory:pos_list")
    success_message = "Sale saved."
    extra_context = {"title": "POS Sale"}

    def form_valid(self, form):
        if not form.instance.transaction_id:
            form.instance.transaction_id = generate_transaction_id("SAL", POSMaster)
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
    model = POSMaster
    template_name = "inventory/pos_detail.html"
    context_object_name = "sale"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_form"] = POSDetailForm()
        return context


class POSItemCreateView(InventoryManageMixin, View):
    def post(self, request, pk):
        sale = get_object_or_404(POSMaster, pk=pk)
        if sale.posted == YES:
            messages.error(request, "Posted sale cannot be updated.")
            return redirect("inventory:pos_detail", pk=pk)
        form = POSDetailForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.pos_master = sale
            item.created_by = request.user
            item.updated_by = request.user
            item.save()
            messages.success(request, "Sale item saved.")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return redirect("inventory:pos_detail", pk=pk)


class POSPostView(InventoryManageMixin, View):
    def post(self, request, pk):
        sale = get_object_or_404(POSMaster, pk=pk)
        try:
            post_sale(sale=sale, user=request.user)
            messages.success(request, "Sale posted and stock updated.")
        except ValidationError as exc:
            messages.error(request, exc)
        return redirect("inventory:pos_detail", pk=pk)


class POSReturnListView(InventoryListMixin, ListView):
    template_name = "inventory/pos_return_list.html"
    context_object_name = "returns"
    queryset = POSReturnMaster.objects.select_related("pos_master", "customer").order_by("-return_date", "-id")
    search_fields = ("return_num", "transaction_id", "sale_num")


class POSReturnCreateView(InventoryManageMixin, CreateView):
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
    def post(self, request, pk):
        record = get_object_or_404(POSReturnMaster, pk=pk)
        try:
            post_sale_return(sale_return=record, user=request.user)
            messages.success(request, "Sale return posted and stock updated.")
        except ValidationError as exc:
            messages.error(request, exc)
        return redirect("inventory:pos_return_detail", pk=pk)


class PurchaseReturnListView(InventoryListMixin, ListView):
    template_name = "inventory/purchase_return_list.html"
    context_object_name = "returns"
    queryset = PurchaseReturnMaster.objects.select_related("purchase_order", "vendor").order_by("-return_date", "-id")
    search_fields = ("return_num", "transaction_id", "purchase_order__purchase_num")


class PurchaseReturnCreateView(InventoryManageMixin, CreateView):
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
    model = PurchaseReturnMaster
    template_name = "inventory/purchase_return_detail.html"
    context_object_name = "purchase_return"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_form"] = PurchaseReturnDetailForm()
        return context


class PurchaseReturnItemCreateView(InventoryManageMixin, View):
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
    def post(self, request, pk):
        record = get_object_or_404(PurchaseReturnMaster, pk=pk)
        try:
            post_purchase_return(purchase_return=record, user=request.user)
            messages.success(request, "Purchase return posted and stock updated.")
        except ValidationError as exc:
            messages.error(request, exc)
        return redirect("inventory:purchase_return_detail", pk=pk)
