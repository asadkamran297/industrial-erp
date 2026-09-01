import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import IntegerField, Max, Q
from django.db.models.functions import Cast, Substr
from django.utils import timezone

from apps.core.constants import (
    INV_CUSTOMER_LEDGER_TRANSACTION_TYPE_CHOICES,
    INV_IMPORTED_CHOICES,
    INV_ITEM_KIND_CHOICES,
    INV_ITEM_TYPE_CHOICES,
    INV_POS_STATUS_CHOICES,
    INV_PURCHASE_BILL_STATUS_CHOICES,
    INV_PO_CANCEL_REASONS,
    INV_PO_CLOSE_SHORT_REASONS,
    INV_PURCHASE_INVOICE_STATUS_CHOICES,
    INV_PURCHASE_ORDER_STATUS_CHOICES,
    INV_RETURN_STATUS_CHOICES,
    INV_SALES_ORDER_STATUS_CHOICES,
    INV_TRANSACTION_TYPE_CHOICES,
    INVENTORY_KIND_PRODUCT,
    NO,
    PAY_MODE_CHOICES,
    RECORD_STATUS_CHOICES,
    STATUS_ACTIVE,
    STATUS_CREATED,
    STATUS_DRAFT,
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_CLOSED,
    STATUS_FULLY_INVOICED,
    STATUS_FULLY_INVOICED,
    STATUS_PARTIALLY_INVOICED,
    STATUS_POSTED,
    STATUS_SUBMITTED,
    STATUS_SUBMITTED,
    YES,
    YES_NO_CHOICES,
)
from apps.core.models import BaseModel


TWO_DP = Decimal("0.01")


class InventoryClass(BaseModel):
    title = models.CharField("Category Name", max_length=160)
    class_code = models.CharField("Category Code", max_length=20, unique=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "inv_config_classess"
        ordering = ["title"]
        # Called a category everywhere it is shown; the table name stays as it
        # was so existing data and migrations are left alone.
        verbose_name = "item category"
        verbose_name_plural = "item categories"

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
        # One rate per pair. A second row for the same two units would leave
        # every reader picking between two answers to the same question.
        if self.uom_from_id and self.uom_to_id:
            # Soft-deleted rows do not count: the pair is free again.
            clash = UOMConversion.objects.filter(uom_from_id=self.uom_from_id, uom_to_id=self.uom_to_id)
            if self.pk:
                clash = clash.exclude(pk=self.pk)
            if clash.exists():
                raise ValidationError({"uom_to": f"{self.uom_from} already converts to {self.uom_to}. Edit that conversion instead."})

    def __str__(self):
        return f"{self.uom_from} -> {self.uom_to}"


class Supplier(BaseModel):
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
    supplier_current_status = models.CharField(max_length=60, blank=True)

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
        db_table = "inv_config_suppliers"
        ordering = ["name"]

    CODE_PREFIX = "SUP"

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
        """Next code in the supplier sequence: SUP-0001, SUP-0002, …

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
            while Supplier.all_objects.filter(code=self.code).exclude(pk=self.pk).exists():
                self.code = self.next_code()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"


class InventoryItem(BaseModel):
    item_name = models.CharField(max_length=180)
    code = models.CharField(max_length=60, unique=True, blank=True)
    # Optional: a service, or an item filed before anyone settles how it is
    # measured, carries no unit. Quantities are still held in the base unit
    # wherever one is set.
    uom = models.ForeignKey(UOM, null=True, blank=True, on_delete=models.PROTECT, related_name="items", db_column="inv_config_uom_id")
    # Optional second unit the item is also handled in — bought by the bag,
    # issued by the kilo. Quantities are still held in the base unit.
    secondary_uom = models.ForeignKey(UOM, null=True, blank=True, on_delete=models.PROTECT, related_name="secondary_items", db_column="inv_config_secondary_uom_id")
    # Optional: an item can be filed before anyone decides which category it
    # belongs to. Uncategorised items fall back to the generic code prefix.
    item_class = models.ForeignKey(InventoryClass, null=True, blank=True, on_delete=models.PROTECT, db_column="inv_config_class_id")
    conversion = models.ForeignKey(UOMConversion, null=True, blank=True, on_delete=models.SET_NULL, db_column="conversion_id")
    item_bar_code = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)
    imported = models.CharField(max_length=1, choices=INV_IMPORTED_CHOICES, default="L")
    inventory = models.CharField(max_length=1, choices=INV_ITEM_TYPE_CHOICES, default="I")
    # A service is sold but never stocked, so it carries no quantity and no
    # opening balance; everything else on the record behaves the same.
    item_kind = models.CharField(max_length=1, choices=INV_ITEM_KIND_CHOICES, default=INVENTORY_KIND_PRODUCT)
    price = models.DecimalField("Sale Price", max_digits=18, decimal_places=2, default=Decimal("0.00"))
    # What the item is expected to cost. A goods receipt still sets the real
    # landed cost on the stock record; this is the figure quoted before one.
    purchase_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "inv_inventory_codes"
        ordering = ["item_name"]
        indexes = [models.Index(fields=["code"]), models.Index(fields=["item_name"])]

    @property
    def code_prefix(self):
        return ((self.item_class.class_code if self.item_class_id else "") or "ITM").upper()

    @staticmethod
    def next_code(prefix):
        """The next free code under one category prefix.

        The sequence is counted per prefix, not off the row id, so the first
        pump reads PMP-0001 whatever else is already in the table. The regex is
        anchored at both ends so a prefix is never counted against a longer one
        that starts with the same letters (CAT against CATERING). Soft-deleted
        rows still hold their number: a code that reached a posted voucher is
        never handed to a second item.
        """
        prefix = prefix.upper()
        last = (
            InventoryItem.all_objects.filter(code__regex=rf"^{re.escape(prefix)}-[0-9]+$")
            .annotate(seq=Cast(Substr("code", len(prefix) + 2), IntegerField()))
            .aggregate(highest=Max("seq"))["highest"]
            or 0
        )
        return f"{prefix}-{last + 1:04d}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        self.code = (self.code or "").strip().upper()
        if not self.code:
            self.code = self.next_code(self.code_prefix)
            # A second save racing this one would take the same number, so the
            # collision is walked past rather than raised at the user.
            while InventoryItem.all_objects.filter(code=self.code).exclude(pk=self.pk).exists():
                self.code = self.next_code(self.code_prefix)
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
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_column="inv_config_supplier_id")
    # Counted per kind, not across both. Orders and bills are two different
    # documents with two different numbers on them; sharing one counter left
    # gaps in each series, and a gap in a numbered series is the first thing an
    # auditor asks about.
    seq_num = models.PositiveIntegerField(blank=True, null=True)
    purchase_num = models.CharField(max_length=40, unique=True, blank=True)
    descr = models.TextField(blank=True)
    purchase_date = models.DateField(default=timezone.localdate)
    quot_num = models.CharField(max_length=80, blank=True)
    quot_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=INV_PURCHASE_ORDER_STATUS_CHOICES, default=STATUS_DRAFT)
    # When the goods were promised. Nothing enforces it; it is what makes a
    # delivery late, which is the only way an order that is quietly not
    # arriving ever gets noticed.
    expected_date = models.DateField(null=True, blank=True)
    # Whatever the site added to the purchase order form for itself, keyed by
    # the field's code. Held as JSON rather than as columns because the set is
    # configured by the site and changes without a migration; nothing in the
    # books reads it, so an order still posts the same with or without it.
    extra_data = models.JSONField(default=dict, blank=True)

    # Who let the money out of the door, and when. An approval limit is only a
    # control if the name of whoever cleared it is kept beside the order.
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="approved_purchase_orders", db_column="approved_by_id")
    approved_at = models.DateTimeField(null=True, blank=True)
    # What the order was worth when it was raised, so an approval limit is
    # measured against the figure that was actually approved rather than
    # against whatever the lines add up to today.
    approved_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # How an order ended, when it did not end by everything arriving. The
    # reason is kept because "cancelled" on its own tells the next reader
    # nothing, and because releasing a commitment is a decision someone made.
    close_reason = models.CharField(max_length=40, blank=True)
    # What the reason list could not say. A picked reason groups the decision;
    # this is where the particular one is written down.
    close_remarks = models.TextField(blank=True)
    closed_on = models.DateField(null=True, blank=True)
    closed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="closed_purchase_orders", db_column="closed_by_id")
    # Quantity and value given up when the balance was closed short. Held on
    # the order so the register can total it without walking every line.
    short_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    short_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "inv_purchase_orders"
        ordering = ["-purchase_date", "-id"]
        indexes = [
            models.Index(fields=["purchase_num"]),
            models.Index(fields=["purchase_date"]),
            # Order lists filter by status and page newest first.
            models.Index(fields=["status", "-purchase_date"]),
            # Supplier history and the pending-receipt lookup.
            models.Index(fields=["supplier", "-purchase_date"]),
        ]

    @property
    def is_closed(self):
        """Finished with, however it finished. Nothing more is expected on it."""
        return self.status in (STATUS_FULLY_INVOICED, STATUS_CLOSED, STATUS_CANCELLED)

    @property
    def is_open(self):
        """Still live: committed, and something on it is still to be invoiced."""
        return self.status in (STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED)

    @property
    def qty_pending(self):
        """Still to be invoiced across the whole order."""
        return sum((line.qty_pending for line in self.items.all()), Decimal("0.0000"))

    def invoiced_status(self):
        """What this order's status should be, read off its own lines.

        Draft and the two ended states are decisions somebody made and are left
        alone; everything else follows the lines, so an order cannot sit at
        "submitted" with nothing left on it.
        """
        if self.status in (STATUS_DRAFT, STATUS_CANCELLED, STATUS_CLOSED):
            return self.status
        lines = list(self.items.all())
        if not lines:
            return STATUS_SUBMITTED
        if all(line.is_fully_invoiced for line in lines):
            return STATUS_FULLY_INVOICED
        if any((line.qty_invoiced or Decimal("0")) > 0 for line in lines):
            return STATUS_PARTIALLY_INVOICED
        return STATUS_SUBMITTED

    @property
    def close_reason_label(self):
        reasons = dict(INV_PO_CANCEL_REASONS) | dict(INV_PO_CLOSE_SHORT_REASONS)
        return reasons.get(self.close_reason, self.close_reason)

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = (
                PurchaseOrder.all_objects.order_by("-seq_num")
                .values_list("seq_num", flat=True).first() or 0
            )
            self.seq_num = last + 1
        # One kind of purchase order now: an invoice is its own document with
        # its own counter, so nothing here has to branch on which it is.
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
    # Copied off the item, which is allowed to carry none.
    uom = models.ForeignKey(UOM, null=True, blank=True, on_delete=models.PROTECT, db_column="inv_config_uom_id")
    last_receive_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    curr_receive_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    tax_perc = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    discount_perc = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    extra_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    retail_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_receive_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    # How much of this line an invoice has been entered against. The invoice is
    # the only thing that books goods in, so this is what says whether the line
    # is still owed.
    qty_invoiced = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    descr = models.CharField(max_length=255)
    remarks = models.CharField(max_length=255, blank=True, default="")
    # Set when somebody decides the balance on this line is never coming. It
    # stops the line counting towards what is still on order without pretending
    # the quantity arrived, which is what writing the receipt up would do.
    closed = models.BooleanField(default=False)

    class Meta:
        db_table = "inv_purchase_order_items"
        ordering = ["purchase_order", "seq_num"]
        unique_together = (("purchase_order", "seq_num"),)

    @property
    def pending_receive_qty(self):
        pending_qty = (self.quantity or Decimal("0.0000")) - (self.total_receive_qty or Decimal("0.0000"))
        return pending_qty if pending_qty > Decimal("0.0000") else Decimal("0.0000")

    @property
    def open_receive_qty(self):
        """Still genuinely expected — nil once the line has been closed short."""
        return Decimal("0.0000") if self.closed else self.pending_receive_qty

    @property
    def qty_ordered(self):
        """What was ordered on this line.

        An alias over ``quantity`` rather than a column of its own: the two
        would have to be kept equal for ever, and a second copy of a number is
        a second thing that can be wrong.
        """
        return self.quantity or Decimal("0.0000")

    @property
    def qty_pending(self):
        """Ordered but not yet invoiced. Nil once the line has been closed.

        Derived rather than stored for the same reason: a column holding a
        subtraction drifts the first time one of its two inputs is written
        without the other.
        """
        if self.closed:
            return Decimal("0.0000")
        pending = self.qty_ordered - (self.qty_invoiced or Decimal("0.0000"))
        return pending if pending > Decimal("0.0000") else Decimal("0.0000")

    @property
    def is_fully_invoiced(self):
        return self.qty_pending <= Decimal("0.0000")

    @property
    def pending_bill_qty(self):
        """Old name for :attr:`qty_pending`, kept while callers move over."""
        return self.qty_pending

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


class PurchaseInvoice(BaseModel):
    """The supplier's invoice. The only financial document on the purchase side.

    Submitting one takes the goods into stock, writes the item ledger and posts
    the voucher, in a single transaction. An order may sit behind it and may
    not; the order is a statement of intent and moves nothing, so an invoice
    entered with no order behind it is a complete purchase rather than an
    exception for somebody to reconcile later.

    Nothing is matched against anything. There is no receipt between the order
    and the invoice, so freight and discount land on the invoice total instead
    of being held apart as a variance against a figure that no longer exists.
    """

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_column="inv_config_supplier_id")
    # Nullable on purpose: this is what "the order is optional" means in the
    # schema rather than in a comment.
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, related_name="invoices",
                                       on_delete=models.PROTECT, db_column="inv_purchase_order_id")
    seq_num = models.PositiveIntegerField(unique=True, blank=True, null=True)
    invoice_num = models.CharField(max_length=40, unique=True, blank=True)
    # The supplier's own number. Required, and unique per supplier, because it
    # is the only thing that catches the same invoice being entered twice --
    # which is the most common way a supplier is paid twice for one delivery.
    supplier_invoice_num = models.CharField(max_length=80)
    supplier_invoice_date = models.DateField(null=True, blank=True)
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)

    goods_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    freight_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(max_length=20, choices=INV_PURCHASE_INVOICE_STATUS_CHOICES, default=STATUS_POSTED)
    # When it hit the books, and which voucher carries it. Kept on the invoice
    # so the document reads on its own, without a join to the ledger to answer
    # the first question anybody asks of it.
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="posted_purchase_invoices", db_column="posted_by_id")
    journal_ref = models.CharField(max_length=80, blank=True)
    # The PB- number this purchase carried before it became one document.
    # Read-only, and blank on everything entered since.
    legacy_bill_no = models.CharField(max_length=40, blank=True)

    reversal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="reversals", db_column="reversal_of_id")
    reverse_reason = models.CharField(max_length=40, blank=True)
    reversed_on = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = "inv_purchase_invoices"
        ordering = ["-invoice_date", "-id"]
        # One invoice number per supplier. The database says it as well as the
        # service does, so a double submit cannot slip a duplicate through.
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "supplier_invoice_num"],
                condition=Q(status=STATUS_POSTED),
                name="uniq_supplier_invoice_number",
            )
        ]
        indexes = [
            models.Index(fields=["invoice_num"]),
            models.Index(fields=["invoice_date"]),
            # The board filters by state and pages newest first.
            models.Index(fields=["status", "-invoice_date"]),
            # Supplier history, and what a supplier is owed.
            models.Index(fields=["supplier", "-invoice_date"]),
            # Walking back from an order to what was invoiced against it.
            models.Index(fields=["purchase_order"]),
        ]

    @property
    def balance_amount(self):
        """Still owed on this invoice. Derived, so it cannot drift from paid."""
        return (self.total_amount or Decimal("0.00")) - (self.paid_amount or Decimal("0.00"))

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = (
                PurchaseInvoice.all_objects.order_by("-seq_num")
                .values_list("seq_num", flat=True).first() or 0
            )
            self.seq_num = last + 1
        if not self.invoice_num:
            self.invoice_num = f"PI-{self.seq_num:06d}"
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_num


class PurchaseInvoiceLine(BaseModel):
    """One invoiced line, and the order line it came off if there was one.

    Pulled from an order, the link is what bounds it: the quantity cannot run
    past what was ordered and not yet invoiced, and the rate can be read
    against the rate that was agreed. Entered without an order, it is bounded
    by nothing but what the supplier wrote.
    """

    invoice = models.ForeignKey(PurchaseInvoice, related_name="items", on_delete=models.CASCADE,
                                db_column="inv_purchase_invoice_id")
    purchase_order_item = models.ForeignKey(PurchaseOrderItem, null=True, blank=True,
                                            related_name="invoice_lines", on_delete=models.PROTECT,
                                            db_column="inv_purchase_order_item_id")
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    seq_num = models.PositiveIntegerField()
    descr = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    rate = models.DecimalField(max_digits=18, decimal_places=2)
    uom = models.ForeignKey(UOM, null=True, blank=True, on_delete=models.PROTECT, db_column="inv_config_uom_id")
    tax_perc = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "inv_purchase_invoice_items"
        ordering = ["invoice", "seq_num"]
        unique_together = (("invoice", "seq_num"),)
        indexes = [
            # An item's purchase history, read straight off the lines.
            models.Index(fields=["inventory_item", "-id"]),
        ]

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = (
                PurchaseInvoiceLine.all_objects.filter(invoice=self.invoice)
                .order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
            )
            self.seq_num = last + 1
        if not self.descr:
            self.descr = self.inventory_item.item_name
        self.amount = (
            (self.quantity or Decimal("0")) * (self.rate or Decimal("0"))
            - (self.discount_amount or Decimal("0.00"))
        ).quantize(TWO_DP)
        self.full_clean()
        super().save(*args, **kwargs)


class PurchaseMaster(BaseModel):
    transaction_id = models.CharField(max_length=60, unique=True)
    inv_purchase_order_inv_num = models.CharField(max_length=80, blank=True)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    adjusted_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    return_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    purchase_order = models.ForeignKey(PurchaseOrder, related_name="purchase_masters", on_delete=models.PROTECT, db_column="inv_purchase_order_id")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_column="inv_config_supplier_id")

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
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["transaction_no"]),
            models.Index(fields=["transaction_date"]),
            # Stock card: one item over a date range.
            models.Index(fields=["inventory_item", "-transaction_date"]),
            # Tracing entries back to the document that produced them.
            models.Index(fields=["ref_table", "ref_id"]),
        ]

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
        indexes = [
            models.Index(fields=["transaction_no"]),
            models.Index(fields=["transaction_date"]),
            # Customer statement over a date range.
            models.Index(fields=["customer", "-transaction_date"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Ledger is insert-only. Use reversal entries instead of editing.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer_id} - {self.transaction_no}"


class SalesOrder(BaseModel):
    """What a customer has asked for. Commits nothing to the books.

    The mirror of :class:`PurchaseOrder`, and deliberately the same shape: an
    order is a statement of intent, the invoice is the event. Nothing here
    touches stock or the ledger, so an order can be raised, amended and
    abandoned without anything needing to be unwound.
    """

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, db_column="inv_customer_id")
    seq_num = models.PositiveIntegerField(unique=True, blank=True, null=True)
    order_num = models.CharField(max_length=40, unique=True, blank=True)
    order_date = models.DateField(default=timezone.localdate)
    # When the customer was promised it. Nothing enforces it; it is what makes
    # an order late, which is the only way one quietly going nowhere is noticed.
    expected_date = models.DateField(null=True, blank=True)
    customer_ref = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=INV_SALES_ORDER_STATUS_CHOICES, default=STATUS_DRAFT)

    close_reason = models.CharField(max_length=40, blank=True)
    close_remarks = models.TextField(blank=True)
    closed_on = models.DateField(null=True, blank=True)
    closed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="closed_sales_orders", db_column="closed_by_id")
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = "inv_sales_orders"
        ordering = ["-order_date", "-id"]
        indexes = [
            models.Index(fields=["order_num"]),
            models.Index(fields=["order_date"]),
            # The board filters by state and pages newest first.
            models.Index(fields=["status", "-order_date"]),
            # A customer's order history, and the open-order lookup the sales
            # invoice screen makes the moment a customer is picked.
            models.Index(fields=["customer", "-order_date"]),
        ]

    @property
    def is_closed(self):
        return self.status in (STATUS_FULLY_INVOICED, STATUS_CLOSED, STATUS_CANCELLED)

    @property
    def is_open(self):
        return self.status in (STATUS_SUBMITTED, STATUS_PARTIALLY_INVOICED)

    @property
    def qty_pending(self):
        return sum((line.qty_pending for line in self.items.all()), Decimal("0.0000"))

    @property
    def total_amount(self):
        return sum((line.total_amount for line in self.items.all()), Decimal("0.00"))

    def invoiced_status(self):
        """What this order's status should be, read off its own lines.

        Same rule as the purchase side, and written the same way on purpose:
        the two boards answer the same question, and a reader who has learnt
        one should not have to learn the other.
        """
        if self.status in (STATUS_DRAFT, STATUS_CANCELLED, STATUS_CLOSED):
            return self.status
        lines = list(self.items.all())
        if not lines:
            return STATUS_SUBMITTED
        if all(line.is_fully_invoiced for line in lines):
            return STATUS_FULLY_INVOICED
        if any((line.qty_invoiced or Decimal("0")) > 0 for line in lines):
            return STATUS_PARTIALLY_INVOICED
        return STATUS_SUBMITTED

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = (
                SalesOrder.all_objects.order_by("-seq_num")
                .values_list("seq_num", flat=True).first() or 0
            )
            self.seq_num = last + 1
        if not self.order_num:
            self.order_num = f"SO-{self.seq_num:06d}"
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_num


class SalesOrderItem(BaseModel):
    """One ordered line, and how much of it has been invoiced."""

    sales_order = models.ForeignKey(SalesOrder, related_name="items", on_delete=models.CASCADE,
                                    db_column="inv_sales_order_id")
    seq_num = models.PositiveIntegerField()
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, db_column="inv_inventory_code_id")
    descr = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    rate = models.DecimalField(max_digits=18, decimal_places=2)
    uom = models.ForeignKey(UOM, null=True, blank=True, on_delete=models.PROTECT, db_column="inv_config_uom_id")
    tax_perc = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    qty_invoiced = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    # Set when somebody decides the balance on this line is never going out. It
    # stops the line counting as still owed without pretending it shipped.
    closed = models.BooleanField(default=False)

    class Meta:
        db_table = "inv_sales_order_items"
        ordering = ["sales_order", "seq_num"]
        unique_together = (("sales_order", "seq_num"),)

    @property
    def qty_ordered(self):
        return self.quantity or Decimal("0.0000")

    @property
    def qty_pending(self):
        if self.closed:
            return Decimal("0.0000")
        pending = self.qty_ordered - (self.qty_invoiced or Decimal("0.0000"))
        return pending if pending > Decimal("0.0000") else Decimal("0.0000")

    @property
    def is_fully_invoiced(self):
        return self.qty_pending <= Decimal("0.0000")

    @property
    def total_amount(self):
        return (self.quantity or Decimal("0")) * (self.rate or Decimal("0")) - (self.discount_amount or Decimal("0"))

    def save(self, *args, **kwargs):
        if not self.seq_num:
            last = (
                SalesOrderItem.all_objects.filter(sales_order=self.sales_order)
                .order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
            )
            self.seq_num = last + 1
        if not self.descr:
            self.descr = self.inventory_item.item_name
        self.full_clean()
        super().save(*args, **kwargs)


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
    # Nullable on purpose: the order is optional, exactly as on the purchase
    # side. A sale with no order behind it is a complete sale, not an exception.
    sales_order = models.ForeignKey(SalesOrder, null=True, blank=True, related_name="invoices",
                                    on_delete=models.PROTECT, db_column="inv_sales_order_id")
    # When it hit the books and which voucher carries it, so the invoice reads
    # on its own without a join to the ledger.
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="posted_sales_invoices", db_column="posted_by_id")
    journal_ref = models.CharField(max_length=80, blank=True)
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
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["sale_num"]),
            models.Index(fields=["sale_date"]),
            models.Index(fields=["status", "-sale_date"]),
            models.Index(fields=["posted", "-sale_date"]),
            models.Index(fields=["customer", "-sale_date"]),
        ]

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
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["return_num"]),
            models.Index(fields=["return_date"]),
            models.Index(fields=["status", "-return_date"]),
        ]

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
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_column="inv_config_supplier_id")
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
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["return_num"]),
            models.Index(fields=["return_date"]),
            models.Index(fields=["status", "-return_date"]),
        ]

    def save(self, *args, **kwargs):
        if not self.return_seq_num:
            last = PurchaseReturnMaster.all_objects.order_by("-return_seq_num").values_list("return_seq_num", flat=True).first() or 0
            self.return_seq_num = last + 1
        self.return_num = f"PR-{self.return_seq_num}"
        self.purchase_order = self.purchase_master.purchase_order
        self.supplier = self.purchase_master.supplier
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
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True, blank=False, db_column="inv_config_supplier_id")
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
