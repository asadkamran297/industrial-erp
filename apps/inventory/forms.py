from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.constants import INVENTORY_KIND_PRODUCT, INVENTORY_KIND_SERVICE
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
    Supplier,
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


class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = (
            "name", "code", "web_url", "email", "fax", "ntn_number", "sale_tax_num",
            "addr1", "addr2", "city", "tel1", "tel2", "status", "remarks", "supplier_current_status",
            "opening_balance", "opening_balance_date", "credit_limit", "credit_period_days",
        )
        widgets = {
            "remarks": forms.TextInput(),
            "opening_balance_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "opening_balance": "Opening Balance",
            "opening_balance_date": "As Of Date",
            "credit_limit": "Credit Limit",
            "credit_period_days": "Credit Period (days)",
        }
        help_texts = {
            "opening_balance": "What was already owed to this supplier when they were put on the system.",
            "credit_limit": "Leave blank for no limit.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional: a supplier is often on the books before their address is.
        self.fields["city"].required = False
        self.fields["city"].empty_label = "-- Select city --"
        # System-assigned: shown so it can be read, never typed.
        self.fields["code"].required = False
        self.fields["code"].disabled = True
        self.fields["code"].help_text = "Assigned automatically."
        if not self.instance.pk:
            self.initial["code"] = Supplier.next_code()
        self.fields["opening_balance"].required = False
        # The date only matters once there is a figure to date; clean() ties them.
        self.fields["opening_balance_date"].required = False
        # A new supplier's balance is almost always "as of today", so today is
        # offered; an existing record keeps whatever date it was given.
        if not self.instance.pk and not self.initial.get("opening_balance_date"):
            self.initial["opening_balance_date"] = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        opening = cleaned.get("opening_balance")
        as_of = cleaned.get("opening_balance_date")
        if opening and not as_of:
            # An opening balance with no date cannot be placed in a period.
            self.add_error("opening_balance_date", "Give the date this balance was true.")
        limit = cleaned.get("credit_limit")
        if limit is not None and limit < 0:
            self.add_error("credit_limit", "Credit limit cannot be negative.")
        return cleaned


class InventoryItemForm(StyledModelForm):
    """Add/edit an item, with the opening stock a brand-new item starts from.

    Opening quantity is not a model field: it is a one-off movement recorded
    through the item ledger on save, so it can never be silently re-applied by
    editing the item later.
    """

    opening_quantity = forms.DecimalField(
        label="Opening Quantity",
        required=False,
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.0001", "min": "0", "placeholder": "0"}),
    )
    opening_date = forms.DateField(
        label="As of Date",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-input", "type": "date"}),
    )
    opening_price = forms.DecimalField(
        label="Opening Rate",
        required=False,
        max_digits=18,
        decimal_places=2,
        min_value=Decimal("0"),
        help_text="Left blank, the purchase price is used.",
        widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "min": "0", "placeholder": "0.00"}),
    )

    class Meta:
        model = InventoryItem
        fields = (
            "item_name", "code", "item_kind", "uom", "item_class", "conversion",
            "item_bar_code", "status", "imported", "inventory", "price", "purchase_price",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = False  # the model assigns one from the class
        self.fields["price"].label = "Sale Price"
        self.fields["purchase_price"].label = "Purchase Price"
        self.fields["item_class"].label = "Category"
        self.fields["uom"].label = "Unit"
        self.fields["opening_date"].initial = timezone.localdate()

    @property
    def opening_stock_allowed(self):
        """Only a brand-new product can be given an opening quantity."""
        if self.instance.pk:
            return False
        return (self.data.get("item_kind") or self.initial.get("item_kind") or INVENTORY_KIND_PRODUCT) == INVENTORY_KIND_PRODUCT

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get("opening_quantity")
        if not quantity:
            return cleaned_data

        # Reported against the form rather than the field: in both cases the
        # opening boxes are hidden on the re-rendered page, so a field-level
        # error would be raised into a panel the operator cannot see.
        if self.instance.pk:
            # Editing must not re-open a stock balance; that is what the Stock
            # Adjustment screen is for.
            self.add_error(None, "Opening stock can only be set when the item is first created. Use Stock Adjustment instead.")
        elif cleaned_data.get("item_kind") == INVENTORY_KIND_SERVICE:
            self.add_error(None, "A service is not stocked, so it cannot carry an opening quantity.")
        if not cleaned_data.get("opening_date"):
            cleaned_data["opening_date"] = timezone.localdate()
        if cleaned_data.get("opening_price") in (None, ""):
            cleaned_data["opening_price"] = cleaned_data.get("purchase_price") or Decimal("0.00")
        return cleaned_data


class InventoryItemImportForm(forms.Form):
    """CSV upload for creating items in bulk.

    Deliberately master-data only: an imported item starts at zero stock, which
    is then moved by a Stock Adjustment or a goods receipt, so an import can
    never post quantities behind the ledger's back.
    """

    COLUMNS = ("item_name", "item_class", "uom", "price", "item_bar_code")
    # .xls is the old binary format openpyxl cannot read; Excel saves either of
    # these from "Save As" without any add-in.
    EXTENSIONS = (".csv", ".xlsx")

    file = forms.FileField(
        label="Excel or CSV file",
        help_text="Columns: item_name, item_class, uom, price, item_bar_code. The first row must be the header.",
        widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": ".csv,.xlsx,text/csv"}),
    )
    update_existing = forms.BooleanField(
        label="Update items that already exist",
        required=False,
        help_text="Matched on item name. Left off, an existing name is reported and skipped.",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-slate-300"}),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(self.EXTENSIONS):
            raise ValidationError("Upload a .xlsx or .csv file. The older .xls format is not supported — re-save it as .xlsx.")
        # 5 MB is far beyond any hand-kept item list, and stops a stray upload
        # from being read into memory.
        if upload.size > 5 * 1024 * 1024:
            raise ValidationError("File is larger than 5 MB.")
        return upload


class PurchaseOrderForm(StyledModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ("supplier", "descr", "purchase_date", "quot_num", "quot_date")
        labels = {"descr": "Comments"}
        widgets = {"descr": forms.TextInput(), "purchase_date": forms.DateInput(attrs={"type": "date"}), "quot_date": forms.DateInput(attrs={"type": "date"})}


class PurchaseOrderItemForm(StyledModelForm):
    inventory_item = InventoryItemChoiceField(label="Inventory Name")
    uom_title = forms.CharField(required=False, disabled=True, label="UOM", widget=forms.TextInput(attrs={"class": "form-input", "readonly": "readonly"}))

    class Meta:
        model = PurchaseOrderItem
        fields = ("inventory_item", "uom_title", "quantity", "rate", "discount_amount", "remarks", "status")
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
        fields = ("supplier", "inventory_item", "qty", "price", "descr")
        labels = {"supplier": "Supplier", "inventory_item": "Item", "qty": "Qty", "price": "Price", "descr": "Description"}
        widgets = {"descr": forms.TextInput()}


class CustomerForm(StyledModelForm):
    opening_balance = forms.DecimalField(max_digits=14, decimal_places=2, required=False, initial=0, label="Opening Balance")

    class Meta:
        model = Customer
        fields = ("customer_code", "customer_name", "customer_address", "customer_cell_no", "customer_email", "ntn_number", "sale_tax_num", "city", "is_default", "status", "remarks")
        labels = {"is_default": "Set as default customer"}
        widgets = {"remarks": forms.TextInput()}


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
