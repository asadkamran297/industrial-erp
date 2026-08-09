from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.constants import (
    INV_CUSTOMER_LEDGER_TRANSACTION_TYPE_CHOICES,
    INV_IMPORTED_CHOICES,
    INV_ITEM_TYPE_CHOICES,
    INV_POS_STATUS_CHOICES,
    INV_PURCHASE_ORDER_STATUS_CHOICES,
    INV_RETURN_STATUS_CHOICES,
    INV_TRANSACTION_TYPE_CHOICES,
    NO,
    PAY_MODE_CHOICES,
    RECORD_STATUS_CHOICES,
    STATUS_ACTIVE,
    STATUS_CREATED,
    STATUS_DRAFT,
    STATUS_RAISED,
    STATUS_SUBMITTED,
    YES,
    YES_NO_CHOICES,
)
from apps.core.models import BaseModel


TWO_DP = Decimal("0.01")


class InventoryClass(BaseModel):
    title = models.CharField("Class Name", max_length=160)
    class_code = models.CharField("Class Code", max_length=20, unique=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "inv_config_classess"
        ordering = ["title"]

    def __str__(self):
        return self.title


class UOM(BaseModel):
    title = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "inv_config_uoms"
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.code})"


class UOMConversion(BaseModel):
    uom_from = models.ForeignKey(UOM, on_delete=models.PROTECT, related_name="conversion_from_set", db_column="inv_config_uom_from_id")
    uom_to = models.ForeignKey(UOM, on_delete=models.PROTECT, related_name="conversion_to_set", db_column="inv_config_uom_to_id")
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=4)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "inv_config_uom_conversions"
        ordering = ["uom_from__title", "uom_to__title"]
        constraints = [models.CheckConstraint(check=~Q(uom_from=models.F("uom_to")), name="inv_uom_conversion_different")]

    def clean(self):
        if self.uom_from_id and self.uom_from_id == self.uom_to_id:
            raise ValidationError({"uom_to": "From UOM and To UOM cannot be same."})

    def __str__(self):
        return f"{self.uom_from} -> {self.uom_to}"


class Vendor(BaseModel):
    name = models.CharField(max_length=180)
    # Assigned by save(); nobody types a supplier code.
    code = models.CharField(max_length=40, unique=True, blank=True)
    web_url = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    fax = models.CharField(max_length=40, blank=True)
    ntn_number = models.CharField(max_length=50, blank=True)
    sale_tax_num = models.CharField(max_length=50, blank=True)
    addr1 = models.CharField(max_length=255, blank=True)
    addr2 = models.CharField(max_length=255, blank=True)
    city = models.ForeignKey("configurations.City", null=True, blank=True, on_delete=models.SET_NULL, db_column="conf_city_id")
    tel1 = models.CharField(max_length=40, blank=True)
    tel2 = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)
    remarks = models.TextField(blank=True)
    vendor_current_status = models.CharField(max_length=60, blank=True)

    # ── Credit & balance ────────────────────────────────────────────────
    # What was already owed when the supplier was put on the system, and the
    # date that figure was true. It is mirrored onto the supplier's payable
    # account, so the ledger opens from the same number the master carries.
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    opening_balance_date = models.DateField(null=True, blank=True)
    # Blank means no limit: a supplier who extends credit without a ceiling.
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    # Days allowed before a bill falls due, counted from the invoice date.
    credit_period_days = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "inv_config_vendors"
        ordering = ["name"]

    CODE_PREFIX = "VEN"

    def clean(self):
        code = (self.code or "").strip().upper()
        if not code:
            return  # save() assigns it
        if len(code) < 4:
            raise ValidationError({"code": "Code must be at least 4 characters."})
        if not code.replace("-", "").isalnum():
            raise ValidationError({"code": "Code may contain alphabets and numbers only."})

    @classmethod
    def next_code(cls):
        """Next code in the supplier sequence: VEN-0001, VEN-0002, …

        Read off the highest number already issued rather than the row count, so
        a deleted supplier never lets its code be handed out twice.
        """
        prefix = cls.CODE_PREFIX
        issued = cls.all_objects.filter(code__startswith=f"{prefix}-").values_list("code", flat=True)
        highest = 0
        for code in issued:
            tail = code.rsplit("-", 1)[-1]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return f"{prefix}-{highest + 1:04d}"

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        if not self.code:
            self.code = self.next_code()
            # A second save racing this one would take the same number, so the
            # collision is walked past rather than raised at the user.
            while Vendor.all_objects.filter(code=self.code).exclude(pk=self.pk).exists():
                self.code = self.next_code()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"


class InventoryItem(BaseModel):
    item_name = models.CharField(max_length=180)
    code = models.CharField(max_length=60, unique=True, blank=True)
    uom = models.ForeignKey(UOM, on_delete=models.PROTECT, db_column="inv_config_uom_id")
    item_class = models.ForeignKey(InventoryClass, on_delete=models.PROTECT, db_column="inv_config_class_id")
    conversion = models.ForeignKey(UOMConversion, null=True, blank=True, on_delete=models.SET_NULL, db_column="conversion_id")
    item_bar_code = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)
    imported = models.CharField(max_length=1, choices=INV_IMPORTED_CHOICES, default="L")
    inventory = models.CharField(max_length=1, choices=INV_ITEM_TYPE_CHOICES, default="I")
    price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "inv_inventory_codes"
        ordering = ["item_name"]
        indexes = [models.Index(fields=["code"]), models.Index(fields=["item_name"])]

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if not self.code:
            prefix = (self.item_class.class_code or "ITM").upper()
            last = InventoryItem.all_objects.filter(code__startswith=prefix).order_by("-id").values_list("id", flat=True).first() or 0
            self.code = f"{prefix}-{last + 1:04d}"
        self.full_clean()
        super().save(*args, **kwargs)
        if creating:
            Stock.objects.get_or_create(
                inventory_item=self,
                defaults={
                    "item_code": self.code,
                    "item_name": self.item_name,
                    "current_quantity": Decimal("0.0000"),
                    "current_price": self.price,
                    "last_price": self.price,
                    "status": self.status,
                    "created_by": self.created_by,
                    "updated_by": self.updated_by,
                },
            )

    def __str__(self):
        return f"{self.code} - {self.item_name}"


class PurchaseOrder(BaseModel):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, db_column="inv_config_vendor_id")
    seq_num = models.PositiveIntegerField(unique=True, blank=True, null=True)
    purchase_num = models.CharField(max_length=40, unique=True, blank=True)
    descr = models.TextField(blank=True)
    purchase_date = models.DateField(default=timezone.localdate)
    quot_num = models.CharField(max_length=80, blank=True)
    quot_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=INV_PURCHASE_ORDER_STATUS_CHOICES, default=STATUS_RAISED)

    class Meta:
        db_table = "inv_purchase_orders"
        ordering = ["-purchase_date", "-id"]
        indexes = [models.Index(fields=["purchase_num"]), models.Index(fields=["purchase_date"])]

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = PurchaseOrder.all_objects.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
            self.seq_num = last + 1
        self.purchase_num = f"PO-{self.seq_num}"
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.purchase_num


class PurchaseOrderItem(BaseModel):
    purchase_order = models.ForeignKey(PurchaseOrder, related_name="items", on_delete=models.CASCADE, db_column="inv_purchase_order_id")
    seq_num = models.PositiveIntegerField()
    purchase_num = models.CharField(max_length=40)
    purchase_date = models.DateField()
    status = models.CharField(max_length=20, choices=YES_NO_CHOICES, default=YES)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    rate = models.DecimalField(max_digits=18, decimal_places=2)
    unit_rate = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    uom = models.ForeignKey(UOM, on_delete=models.PROTECT, db_column="inv_config_uom_id")
    last_receive_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    curr_receive_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    tax_perc = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    discount_perc = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    extra_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    retail_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_receive_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    descr = models.CharField(max_length=255)
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "inv_purchase_order_items"
        ordering = ["purchase_order", "seq_num"]
        unique_together = (("purchase_order", "seq_num"),)

    @property
    def pending_receive_qty(self):
        pending_qty = (self.quantity or Decimal("0.0000")) - (self.total_receive_qty or Decimal("0.0000"))
        return pending_qty if pending_qty > Decimal("0.0000") else Decimal("0.0000")

    @property
    def total_amount(self):
        return (self.quantity or Decimal("0")) * (self.rate or Decimal("0")) - (self.discount_amount or Decimal("0"))

    def is_duplicate_in_order(self):
        if not (self.purchase_order_id and self.inventory_item_id):
            return False
        return PurchaseOrderItem.objects.filter(purchase_order_id=self.purchase_order_id, inventory_item_id=self.inventory_item_id).exclude(pk=self.pk).exists()

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = self.purchase_order.items.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
            self.seq_num = last + 1
        self.purchase_num = self.purchase_order.purchase_num
        self.purchase_date = self.purchase_order.purchase_date
        self.descr = self.inventory_item.item_name
        if not self.unit_rate:
            self.unit_rate = self.rate
        self.full_clean()
        super().save(*args, **kwargs)


class PurchaseOrderItemReceived(BaseModel):
    purchase_order_item = models.ForeignKey(PurchaseOrderItem, related_name="receipts", on_delete=models.PROTECT, db_column="inv_purchase_order_item_id")
    seq_num = models.PositiveIntegerField()
    purchase_num = models.CharField(max_length=40)
    purchase_date = models.DateField()
    descr = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=INV_RETURN_STATUS_CHOICES, default=STATUS_CREATED)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    receive_date = models.DateField(default=timezone.localdate)
    invoice_num = models.CharField(max_length=80, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    grn_number = models.CharField(max_length=80, blank=True)
    rv_number = models.CharField(max_length=80, blank=True)
    extra_qty_tag = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=NO)
    extra_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    retail_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "inv_purchase_order_item_received"
        ordering = ["-receive_date", "-id"]


class PurchaseMaster(BaseModel):
    transaction_id = models.CharField(max_length=60, unique=True)
    inv_purchase_order_inv_num = models.CharField(max_length=80, blank=True)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    adjusted_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    return_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    purchase_order = models.ForeignKey(PurchaseOrder, related_name="purchase_masters", on_delete=models.PROTECT, db_column="inv_purchase_order_id")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, db_column="inv_config_vendor_id")

    class Meta:
        db_table = "inv_purchase_master"
        ordering = ["-id"]
        indexes = [models.Index(fields=["transaction_id"])]


class PurchaseMasterReturn(BaseModel):
    purchase_master = models.ForeignKey(PurchaseMaster, related_name="return_rows", on_delete=models.CASCADE, db_column="inv_purchase_master_id")
    inv_purchase_master_transaction_id = models.CharField(max_length=60)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    inv_inventory_item_name = models.CharField(max_length=180)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    rate = models.DecimalField(max_digits=18, decimal_places=2)
    total_price = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        db_table = "inv_purchase_master_returns"


class Stock(BaseModel):
    inventory_item = models.OneToOneField(InventoryItem, related_name="stock", on_delete=models.CASCADE, db_column="inv_inventory_code_id")
    item_code = models.CharField(max_length=60)
    item_name = models.CharField(max_length=180)
    current_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    current_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    last_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "inv_stocks"
        ordering = ["item_name"]


class ItemLedger(BaseModel):
    transaction_id = models.CharField(max_length=60)
    transaction_no = models.CharField(max_length=60, blank=True)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    item_code = models.CharField(max_length=60)
    item_name = models.CharField(max_length=180)
    transaction_type = models.CharField(max_length=20, choices=INV_TRANSACTION_TYPE_CHOICES)
    transaction_date = models.DateField(default=timezone.localdate)
    ref_table = models.CharField(max_length=100)
    ref_id = models.PositiveBigIntegerField()
    ref_no = models.CharField(max_length=80, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    old_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    new_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    old_price = models.DecimalField(max_digits=18, decimal_places=2)
    current_price = models.DecimalField(max_digits=18, decimal_places=2)
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "inv_item_ledgers"
        ordering = ["-transaction_date", "-id"]
        indexes = [models.Index(fields=["transaction_id"]), models.Index(fields=["transaction_no"]), models.Index(fields=["transaction_date"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Ledger is insert-only. Use reversal entries instead of editing.")
        super().save(*args, **kwargs)


class Customer(BaseModel):
    customer_code = models.CharField(max_length=40, blank=True, null=True, unique=True)
    customer_name = models.CharField(max_length=180)
    customer_address = models.CharField(max_length=255, blank=True)
    customer_cell_no = models.CharField(max_length=40, blank=True)
    customer_email = models.EmailField(blank=True)
    ntn_number = models.CharField(max_length=50, blank=True)
    sale_tax_num = models.CharField(max_length=50, blank=True)
    city = models.ForeignKey("configurations.City", null=True, blank=True, on_delete=models.SET_NULL, db_column="conf_city_id")
    is_default = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = "inv_customers"
        ordering = ["customer_name"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Customer.all_objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)

    @classmethod
    def get_default(cls):
        return cls.objects.filter(is_default=True, status=STATUS_ACTIVE).first()

    def __str__(self):
        return self.customer_name


class CustomerLedger(BaseModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, db_column="inv_customer_id")
    transaction_no = models.CharField(max_length=50)
    transaction_type = models.CharField(max_length=50, choices=INV_CUSTOMER_LEDGER_TRANSACTION_TYPE_CHOICES)
    transaction_date = models.DateField(default=timezone.localdate)
    running_amount = models.DecimalField(max_digits=18, decimal_places=2)
    opening_amount = models.DecimalField(max_digits=18, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=18, decimal_places=2)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "inv_customer_ledgers"
        ordering = ["-transaction_date", "-id"]
        indexes = [models.Index(fields=["transaction_no"]), models.Index(fields=["customer"]), models.Index(fields=["transaction_date"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Ledger is insert-only. Use reversal entries instead of editing.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer_id} - {self.transaction_no}"


class POSMaster(BaseModel):
    transaction_id = models.CharField(max_length=60, unique=True)
    sale_seq_num = models.PositiveIntegerField(unique=True, blank=True, null=True)
    sale_num = models.CharField(max_length=40, unique=True, blank=True)
    invoice_type = models.CharField(max_length=40, blank=True)
    invoice_num = models.CharField(max_length=80, blank=True)
    sale_date = models.DateField(default=timezone.localdate)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    net_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_paid = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, db_column="inv_customer_id")
    pay_mode = models.CharField(max_length=20, choices=PAY_MODE_CHOICES, default="cash")
    credit_card_type = models.CharField(max_length=40, blank=True)
    credit_card_number = models.CharField(max_length=40, blank=True)
    expiry_date = models.CharField(max_length=10, blank=True)
    cc_last_4_digit = models.CharField(max_length=4, blank=True)
    online_transaction_id = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=INV_POS_STATUS_CHOICES, default=STATUS_CREATED)
    posted = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=NO)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = "inv_pos_masters"
        ordering = ["-sale_date", "-id"]
        indexes = [models.Index(fields=["transaction_id"]), models.Index(fields=["sale_num"]), models.Index(fields=["sale_date"])]

    def save(self, *args, **kwargs):
        if not self.sale_seq_num:
            last = POSMaster.all_objects.order_by("-sale_seq_num").values_list("sale_seq_num", flat=True).first() or 0
            self.sale_seq_num = last + 1
        self.sale_num = f"SAL-{self.sale_seq_num}"
        self.full_clean()
        super().save(*args, **kwargs)


class POSDetail(BaseModel):
    pos_master = models.ForeignKey(POSMaster, related_name="items", on_delete=models.CASCADE, db_column="inv_pos_master_id")
    transaction_id = models.CharField(max_length=60)
    sale_num = models.CharField(max_length=40)
    seq_num = models.PositiveIntegerField()
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    item_code = models.CharField(max_length=60)
    item_name = models.CharField(max_length=180)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    price = models.DecimalField(max_digits=18, decimal_places=2)
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_perc = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_perc = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    net_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=INV_RETURN_STATUS_CHOICES, default=STATUS_CREATED)

    class Meta:
        db_table = "inv_pos_details"
        ordering = ["pos_master", "seq_num"]
        unique_together = (("pos_master", "seq_num"),)

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = POSDetail.all_objects.filter(pos_master=self.pos_master).order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
            self.seq_num = last + 1
        self.transaction_id = self.pos_master.transaction_id
        self.sale_num = self.pos_master.sale_num
        self.item_code = self.inventory_item.code
        self.item_name = self.inventory_item.item_name
        self.total_price = ((self.quantity or 0) * (self.price or 0)).quantize(TWO_DP)
        self.tax_amount = (self.tax_amount or Decimal("0.00")).quantize(TWO_DP)
        self.discount_amount = (self.discount_amount or Decimal("0.00")).quantize(TWO_DP)
        self.net_total = (self.total_price - self.discount_amount + self.tax_amount).quantize(TWO_DP)
        self.full_clean()
        super().save(*args, **kwargs)


class POSReturnMaster(BaseModel):
    transaction_id = models.CharField(max_length=60, unique=True)
    return_seq_num = models.PositiveIntegerField(unique=True, blank=True, null=True)
    return_num = models.CharField(max_length=40, unique=True, blank=True)
    pos_master = models.ForeignKey(POSMaster, related_name="returns", on_delete=models.PROTECT, db_column="inv_pos_master_id")
    sale_transaction_id = models.CharField(max_length=60)
    sale_num = models.CharField(max_length=40)
    return_date = models.DateField(default=timezone.localdate)
    total_invoice_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    adjusted_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    returned_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, db_column="inv_customer_id")
    pay_mode = models.CharField(max_length=20, choices=PAY_MODE_CHOICES, default="cash")
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=INV_RETURN_STATUS_CHOICES, default=STATUS_CREATED)
    posted = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=NO)

    class Meta:
        db_table = "inv_pos_return_masters"
        ordering = ["-return_date", "-id"]
        indexes = [models.Index(fields=["transaction_id"]), models.Index(fields=["return_num"]), models.Index(fields=["return_date"])]

    def save(self, *args, **kwargs):
        if not self.return_seq_num:
            last = POSReturnMaster.all_objects.order_by("-return_seq_num").values_list("return_seq_num", flat=True).first() or 0
            self.return_seq_num = last + 1
        self.return_num = f"SR-{self.return_seq_num}"
        self.sale_transaction_id = self.pos_master.transaction_id
        self.sale_num = self.pos_master.sale_num
        if not self.customer_id:
            self.customer = self.pos_master.customer
        self.total_invoice_amount = self.pos_master.net_amount
        self.full_clean()
        super().save(*args, **kwargs)


class POSReturnDetail(BaseModel):
    pos_return_master = models.ForeignKey(POSReturnMaster, related_name="items", on_delete=models.CASCADE, db_column="inv_pos_return_master_id")
    pos_master = models.ForeignKey(POSMaster, on_delete=models.PROTECT, db_column="inv_pos_master_id")
    pos_detail = models.ForeignKey(POSDetail, on_delete=models.PROTECT, db_column="inv_pos_detail_id")
    transaction_id = models.CharField(max_length=60)
    return_num = models.CharField(max_length=40)
    seq_num = models.PositiveIntegerField()
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    item_code = models.CharField(max_length=60)
    item_name = models.CharField(max_length=180)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    price = models.DecimalField(max_digits=18, decimal_places=2)
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    net_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=INV_RETURN_STATUS_CHOICES, default=STATUS_CREATED)

    class Meta:
        db_table = "inv_pos_return_details"
        ordering = ["pos_return_master", "seq_num"]

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = self.pos_return_master.items.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
            self.seq_num = last + 1
        self.transaction_id = self.pos_return_master.transaction_id
        self.return_num = self.pos_return_master.return_num
        self.pos_master = self.pos_return_master.pos_master
        self.inventory_item = self.pos_detail.inventory_item
        self.item_code = self.pos_detail.item_code
        self.item_name = self.pos_detail.item_name
        self.price = self.pos_detail.price
        self.total_price = ((self.quantity or 0) * (self.price or 0)).quantize(TWO_DP)
        self.tax_amount = (self.tax_amount or Decimal("0.00")).quantize(TWO_DP)
        self.discount_amount = (self.discount_amount or Decimal("0.00")).quantize(TWO_DP)
        self.net_total = (self.total_price - self.discount_amount + self.tax_amount).quantize(TWO_DP)
        self.full_clean()
        super().save(*args, **kwargs)


class PurchaseReturnMaster(BaseModel):
    transaction_id = models.CharField(max_length=60, unique=True)
    return_seq_num = models.PositiveIntegerField(unique=True, blank=True, null=True)
    return_num = models.CharField(max_length=40, unique=True, blank=True)
    purchase_master = models.ForeignKey(PurchaseMaster, related_name="purchase_returns", on_delete=models.PROTECT, db_column="inv_purchase_master_id")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, db_column="inv_purchase_order_id")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, db_column="inv_config_vendor_id")
    return_date = models.DateField(default=timezone.localdate)
    total_purchase_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    adjusted_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    returned_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=INV_RETURN_STATUS_CHOICES, default=STATUS_CREATED)
    posted = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=NO)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = "inv_purchase_return_masters"
        ordering = ["-return_date", "-id"]
        indexes = [models.Index(fields=["transaction_id"]), models.Index(fields=["return_num"]), models.Index(fields=["return_date"])]

    def save(self, *args, **kwargs):
        if not self.return_seq_num:
            last = PurchaseReturnMaster.all_objects.order_by("-return_seq_num").values_list("return_seq_num", flat=True).first() or 0
            self.return_seq_num = last + 1
        self.return_num = f"PR-{self.return_seq_num}"
        self.purchase_order = self.purchase_master.purchase_order
        self.vendor = self.purchase_master.vendor
        self.total_purchase_amount = self.purchase_master.total_amount
        self.full_clean()
        super().save(*args, **kwargs)


class PurchaseReturnDetail(BaseModel):
    purchase_return_master = models.ForeignKey(PurchaseReturnMaster, related_name="items", on_delete=models.CASCADE, db_column="inv_purchase_return_master_id")
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    item_code = models.CharField(max_length=60)
    item_name = models.CharField(max_length=180)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    rate = models.DecimalField(max_digits=18, decimal_places=2)
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=INV_RETURN_STATUS_CHOICES, default=STATUS_CREATED)

    class Meta:
        db_table = "inv_purchase_return_details"

    def save(self, *args, **kwargs):
        self.item_code = self.inventory_item.code
        self.item_name = self.inventory_item.item_name
        self.total_price = ((self.quantity or 0) * (self.rate or 0)).quantize(TWO_DP)
        self.full_clean()
        super().save(*args, **kwargs)


MANUAL_TRANSACTION_STATUS_CHOICES = (
    (STATUS_DRAFT, "Draft"),
    (STATUS_SUBMITTED, "Submitted"),
)


class ManualTransaction(BaseModel):
    transaction_id = models.CharField(max_length=60, db_index=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, null=True, blank=False, db_column="inv_config_vendor_id")
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    item_code = models.CharField(max_length=60)
    item_name = models.CharField(max_length=180)
    qty = models.DecimalField(max_digits=18, decimal_places=4)
    price = models.DecimalField(max_digits=18, decimal_places=2)
    descr = models.CharField(max_length=255, blank=True)
    selected = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=YES)
    status = models.CharField(max_length=20, choices=MANUAL_TRANSACTION_STATUS_CHOICES, default=STATUS_DRAFT)

    class Meta:
        db_table = "inv_manual_transaction"
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        self.item_code = self.inventory_item.code
        self.item_name = self.inventory_item.item_name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_id} - {self.item_name}"
