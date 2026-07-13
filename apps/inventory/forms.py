from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.forms import AutoSelectSingleChoiceMixin

from .models import (
    Customer,
    InventoryClass,
    InventoryItem,
    POSDetail,
    POSMaster,
    POSReturnDetail,
    POSReturnMaster,
    PurchaseOrder,
    PurchaseOrderItem,
    ManualTransaction,
    PurchaseReturnDetail,
    PurchaseReturnMaster,
    UOM,
    UOMConversion,
    Vendor,
)


class InventoryItemChoiceField(forms.ModelChoiceField):
    """Item dropdown showing only item name (no code). Reuse everywhere."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("queryset", InventoryItem.objects.all())
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        return obj.item_name


class StyledModelForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "form-input")
                field.widget.attrs.setdefault("rows", 3)
            else:
                field.widget.attrs.setdefault("class", "form-input")


class InventoryClassForm(StyledModelForm):
    class Meta:
        model = InventoryClass
        fields = ("title", "class_code", "status")


class UOMForm(StyledModelForm):
    class Meta:
        model = UOM
        fields = ("title", "code", "status")


class UOMConversionForm(StyledModelForm):
    class Meta:
        model = UOMConversion
        fields = ("uom_from", "uom_to", "conversion_factor", "status")


class VendorForm(StyledModelForm):
    class Meta:
        model = Vendor
        fields = ("name", "code", "web_url", "email", "fax", "ntn_number", "sale_tax_num", "addr1", "addr2", "city", "tel1", "tel2", "status", "remarks", "vendor_current_status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["city"].required = True
        self.fields["city"].empty_label = "-- Select city --"


class InventoryItemForm(StyledModelForm):
    class Meta:
        model = InventoryItem
        fields = ("item_name", "code", "uom", "item_class", "conversion", "item_bar_code", "status", "imported", "inventory", "price")

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()


class PurchaseOrderForm(StyledModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ("vendor", "descr", "purchase_date", "quot_num", "quot_date")
        labels = {"descr": "Comments"}
        widgets = {"descr": forms.TextInput(), "purchase_date": forms.DateInput(attrs={"type": "date"}), "quot_date": forms.DateInput(attrs={"type": "date"})}


class PurchaseOrderItemForm(StyledModelForm):
    inventory_item = InventoryItemChoiceField(label="Inventory Name")
    uom_title = forms.CharField(required=False, disabled=True, label="UOM", widget=forms.TextInput(attrs={"class": "form-input", "readonly": "readonly"}))

    class Meta:
        model = PurchaseOrderItem
        fields = ("inventory_item", "uom_title", "quantity", "rate", "discount_amount", "status")
        labels = {"inventory_item": "Inventory Name"}


class ReceivePOForm(forms.Form):
    purchase_order_item = forms.ModelChoiceField(queryset=PurchaseOrderItem.objects.all(), widget=forms.Select(attrs={"class": "form-select"}))
    quantity = forms.DecimalField(decimal_places=4, max_digits=18, widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.0001", "min": "0.0001"}))
    extra_qty = forms.DecimalField(decimal_places=4, max_digits=18, required=False, initial=Decimal("0.0000"), widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.0001", "min": "0"}))
    retail_price = forms.DecimalField(decimal_places=2, max_digits=18, widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "min": "0"}))
    receive_date = forms.DateField(widget=forms.DateInput(attrs={"class": "form-input", "type": "date"}))
    invoice_num = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-input"}))
    invoice_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-input", "type": "date"}))
    rv_number = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-input"}))
    remarks = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-input", "rows": 2}))


class ManualTransactionForm(StyledModelForm):
    inventory_item = InventoryItemChoiceField(label="Item")

    class Meta:
        model = ManualTransaction
        fields = ("vendor", "inventory_item", "qty", "price", "descr")
        labels = {"vendor": "Vendor", "inventory_item": "Item", "qty": "Qty", "price": "Price", "descr": "Description"}
        widgets = {"descr": forms.TextInput()}


class CustomerForm(StyledModelForm):
    class Meta:
        model = Customer
        fields = ("customer_code", "customer_name", "customer_address", "customer_cell_no", "customer_email", "ntn_number", "sale_tax_num", "city", "is_default", "status", "remarks")
        labels = {"is_default": "Set as default customer"}


class POSMasterForm(StyledModelForm):
    class Meta:
        model = POSMaster
        fields = ("sale_date", "pay_mode", "customer")
        widgets = {"sale_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        labels = {"sale_date": "Sale Date"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pay_mode"].initial = "cash"
        self.fields["sale_date"].initial = timezone.localdate()
        if not self.instance.pk and not self.initial.get("customer"):
            default_customer = Customer.get_default()
            if default_customer:
                self.fields["customer"].initial = default_customer.pk


class POSDetailForm(StyledModelForm):
    inventory_item = InventoryItemChoiceField(label="Item")

    class Meta:
        model = POSDetail
        fields = ("inventory_item", "quantity", "price", "discount_amount")
        labels = {"inventory_item": "Item", "discount_amount": "Discount"}


class POSReturnMasterForm(StyledModelForm):
    class Meta:
        model = POSReturnMaster
        fields = ("pos_master", "return_date", "adjusted_amount", "pay_mode", "status", "remarks")
        widgets = {"return_date": forms.DateInput(attrs={"type": "date"})}


class POSReturnDetailForm(StyledModelForm):
    class Meta:
        model = POSReturnDetail
        fields = ("pos_detail", "quantity", "status")


class PurchaseReturnMasterForm(StyledModelForm):
    class Meta:
        model = PurchaseReturnMaster
        fields = ("purchase_master", "return_date", "adjusted_amount", "status", "remarks")
        widgets = {"return_date": forms.DateInput(attrs={"type": "date"})}


class PurchaseReturnDetailForm(StyledModelForm):
    inventory_item = InventoryItemChoiceField(label="Item")

    class Meta:
        model = PurchaseReturnDetail
        fields = ("inventory_item", "quantity", "rate", "status")
