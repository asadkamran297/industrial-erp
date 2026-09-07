"""The conversion documents: grinding, and repacking.

Both move quantity and nothing else. No journal entry is posted, because until
the mill runs perpetual costing there is no cost to post -- and when it does,
``services.post_grinding_stock`` is the single place that gains one.

Yield is stored on the voucher rather than recomputed on the way out. The
figures are read on trend reports months later, and a product's unit weight
edited in the master would silently rewrite history if the reports derived them
again.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.constants import (
    PRD_PACKABLE_SPECS,
    PRD_SPEC_FINISH_PACKING,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    PRODUCTION_CONVERSION_PREFIX,
    PRODUCTION_GRINDING_PREFIX,
)
from apps.core.models import BaseModel

ZERO = Decimal("0")


def _next_seq(model) -> int:
    last = model.all_objects.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
    return last + 1


class GrindingVoucher(BaseModel):
    """One run of the mill: wheat and sacks in, finished goods and bran out."""

    seq_num = models.PositiveIntegerField()
    voucher_no = models.CharField(max_length=20)
    date = models.DateField()
    production_from = models.TimeField()
    production_to = models.TimeField()

    wheat_item = models.ForeignKey(
        "products.ProductNode",
        related_name="grinding_vouchers",
        on_delete=models.PROTECT,
    )
    disposal_wheat = models.DecimalField(max_digits=16, decimal_places=3, default=0)

    # Defaulted from what the wheat was received in, then stored. Re-deriving it
    # at report time would release the wrong sack whenever government wheat came
    # in under a private poly item, and the bag balances would drift.
    bag_item = models.ForeignKey(
        "products.ProductNode",
        null=True,
        blank=True,
        related_name="grinding_bag_uses",
        on_delete=models.PROTECT,
    )
    disposal_bag_qty = models.DecimalField(max_digits=14, decimal_places=3, default=0)

    godown = models.ForeignKey(
        "godowns.Godown",
        related_name="grinding_vouchers",
        on_delete=models.PROTECT,
    )
    issue_area = models.CharField(max_length=120, blank=True)
    prepared_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        related_name="prepared_grinding_vouchers",
        on_delete=models.PROTECT,
    )
    description = models.TextField(blank=True)

    # -- Yield, computed on save and kept. ----------------------------------
    total_output_kg = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    yield_percent = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    shortage_kg = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    shortage_percent = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    # Copied off the wheat item at save, so the variance shown on an old voucher
    # is the variance against the standard that was in force when it was run.
    standard_yield_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        db_table = "prod_grinding_vouchers"
        ordering = ["-date", "-seq_num"]
        constraints = [
            models.UniqueConstraint(
                fields=["voucher_no"],
                condition=models.Q(deleted_at__isnull=True),
                name="grinding_unique_voucher_no",
            ),
        ]
        indexes = [
            # The list screen, newest first, and its three filters.
            models.Index(fields=["-date", "-seq_num"], name="grind_date_seq_idx"),
            models.Index(fields=["wheat_item", "-date"], name="grind_wheat_date_idx"),
            models.Index(fields=["godown", "-date"], name="grind_godown_date_idx"),
            models.Index(fields=["voucher_no"], name="grind_voucher_no_idx"),
        ]

    def __str__(self) -> str:
        return self.voucher_no

    @property
    def yield_variance(self) -> Decimal:
        """Actual minus standard. Negative is a run that under-delivered."""
        return (self.yield_percent or ZERO) - (self.standard_yield_percent or ZERO)

    @property
    def is_below_standard(self) -> bool:
        return bool(self.standard_yield_percent) and self.yield_percent < self.standard_yield_percent

    @property
    def total_output_bags(self) -> Decimal:
        return sum((line.quantity or ZERO) for line in self.outputs.all()) or ZERO

    def ensure_number(self) -> None:
        """Allocate the number before validation rather than during save().

        ``full_clean`` runs first and would otherwise reject the voucher for the
        two fields save() was about to fill in.
        """
        if not self.seq_num:
            self.seq_num = _next_seq(GrindingVoucher)
        if not self.voucher_no:
            self.voucher_no = f"{PRODUCTION_GRINDING_PREFIX}-{self.seq_num:04d}"

    def clean(self):
        super().clean()
        self.ensure_number()
        if self.production_from and self.production_to and self.production_to < self.production_from:
            raise ValidationError({"production_to": "The run cannot end before it started."})
        if (self.disposal_wheat or ZERO) <= ZERO:
            raise ValidationError({"disposal_wheat": "Enter the wheat consumed."})
        if self.wheat_item_id and self.wheat_item.specification != PRD_SPEC_RAW_ITEM:
            raise ValidationError({"wheat_item": "Only a raw item is ground."})
        if self.bag_item_id and self.bag_item.specification != PRD_SPEC_RAW_PACKING:
            raise ValidationError({"bag_item": "The released sack must be a raw packing item."})
        if (self.disposal_bag_qty or ZERO) and not self.bag_item_id:
            raise ValidationError({"bag_item": "Choose the sack the bags were released from."})

    def save(self, *args, **kwargs):
        self.ensure_number()
        super().save(*args, **kwargs)


class GrindingOutput(BaseModel):
    """One product that came off the run."""

    voucher = models.ForeignKey(GrindingVoucher, related_name="outputs", on_delete=models.CASCADE)
    line_number = models.PositiveSmallIntegerField()
    product = models.ForeignKey(
        "products.ProductNode",
        related_name="grinding_outputs",
        on_delete=models.PROTECT,
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    # Snapshot. The master's unit weight is editable, and a later edit must not
    # move the yield of a run that has already been reported.
    unit_weight = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    pack_product = models.ForeignKey(
        "products.ProductNode",
        null=True,
        blank=True,
        related_name="grinding_pack_uses",
        on_delete=models.PROTECT,
    )
    # Normally equals quantity. Zero for loose output, which is weighed out of
    # the mill into no sack at all.
    pack_qty = models.DecimalField(max_digits=16, decimal_places=3, default=0)

    class Meta:
        db_table = "prod_grinding_outputs"
        ordering = ["voucher", "line_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["voucher", "line_number"],
                condition=models.Q(deleted_at__isnull=True),
                name="grinding_output_unique_line",
            ),
        ]
        indexes = [
            models.Index(fields=["voucher", "line_number"], name="grind_out_voucher_line_idx"),
            # "everything this product was ever produced on", the summary report.
            models.Index(fields=["product", "-id"], name="grind_out_product_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product} x {self.quantity}"

    @property
    def total_weight(self) -> Decimal:
        return (self.quantity or ZERO) * (self.unit_weight or ZERO)

    def clean(self):
        super().clean()
        if self.product_id and self.product.specification not in PRD_PACKABLE_SPECS:
            raise ValidationError({"product": "Only a finish item or by-product comes off the mill."})
        if (self.quantity or ZERO) <= ZERO:
            raise ValidationError({"quantity": "Enter the quantity produced."})
        if self.pack_product_id and self.pack_product.specification != PRD_SPEC_FINISH_PACKING:
            raise ValidationError({"pack_product": "The bag must be a finish packing item."})
        if (self.pack_qty or ZERO) < ZERO:
            raise ValidationError({"pack_qty": "Bag quantity cannot be negative."})
        if (self.pack_qty or ZERO) > ZERO and not self.pack_product_id:
            raise ValidationError({"pack_product": "Choose the bag these were packed in."})

    def save(self, *args, **kwargs):
        if not self.line_number:
            last = (
                GrindingOutput.all_objects.filter(voucher=self.voucher)
                .order_by("-line_number").values_list("line_number", flat=True).first() or 0
            )
            self.line_number = last + 1
        super().save(*args, **kwargs)


class ProductConversion(BaseModel):
    """Repacking: one finished product becomes another.

    Loose maida into 50 kg bags, or 40 kg bags broken into 20 kg bags. The same
    shape as grinding -- something consumed, something produced, quantity only.
    """

    seq_num = models.PositiveIntegerField()
    voucher_no = models.CharField(max_length=20)
    date = models.DateField()
    source_product = models.ForeignKey(
        "products.ProductNode",
        related_name="conversion_sources",
        on_delete=models.PROTECT,
    )
    source_quantity = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    source_unit_weight = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    godown = models.ForeignKey(
        "godowns.Godown",
        related_name="conversions",
        on_delete=models.PROTECT,
    )
    prepared_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        related_name="prepared_conversions",
        on_delete=models.PROTECT,
    )
    description = models.TextField(blank=True)
    total_output_kg = models.DecimalField(max_digits=16, decimal_places=3, default=0)

    class Meta:
        db_table = "prod_conversions"
        ordering = ["-date", "-seq_num"]
        constraints = [
            models.UniqueConstraint(
                fields=["voucher_no"],
                condition=models.Q(deleted_at__isnull=True),
                name="conversion_unique_voucher_no",
            ),
        ]
        indexes = [
            models.Index(fields=["-date", "-seq_num"], name="conv_date_seq_idx"),
            models.Index(fields=["source_product", "-date"], name="conv_source_date_idx"),
            models.Index(fields=["godown", "-date"], name="conv_godown_date_idx"),
        ]

    def __str__(self) -> str:
        return self.voucher_no

    @property
    def source_weight(self) -> Decimal:
        return (self.source_quantity or ZERO) * (self.source_unit_weight or ZERO)

    def ensure_number(self) -> None:
        if not self.seq_num:
            self.seq_num = _next_seq(ProductConversion)
        if not self.voucher_no:
            self.voucher_no = f"{PRODUCTION_CONVERSION_PREFIX}-{self.seq_num:04d}"

    def clean(self):
        super().clean()
        self.ensure_number()
        if (self.source_quantity or ZERO) <= ZERO:
            raise ValidationError({"source_quantity": "Enter what was consumed."})

    def save(self, *args, **kwargs):
        self.ensure_number()
        super().save(*args, **kwargs)


class ProductConversionLine(BaseModel):
    """What the repacking produced."""

    conversion = models.ForeignKey(ProductConversion, related_name="outputs", on_delete=models.CASCADE)
    line_number = models.PositiveSmallIntegerField()
    product = models.ForeignKey(
        "products.ProductNode",
        related_name="conversion_outputs",
        on_delete=models.PROTECT,
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    unit_weight = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    pack_product = models.ForeignKey(
        "products.ProductNode",
        null=True,
        blank=True,
        related_name="conversion_pack_uses",
        on_delete=models.PROTECT,
    )
    pack_qty = models.DecimalField(max_digits=16, decimal_places=3, default=0)

    class Meta:
        db_table = "prod_conversion_lines"
        ordering = ["conversion", "line_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversion", "line_number"],
                condition=models.Q(deleted_at__isnull=True),
                name="conversion_line_unique_line",
            ),
        ]
        indexes = [
            models.Index(fields=["conversion", "line_number"], name="conv_line_conv_line_idx"),
            models.Index(fields=["product", "-id"], name="conv_line_product_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product} x {self.quantity}"

    @property
    def total_weight(self) -> Decimal:
        return (self.quantity or ZERO) * (self.unit_weight or ZERO)

    def clean(self):
        super().clean()
        if (self.quantity or ZERO) <= ZERO:
            raise ValidationError({"quantity": "Enter the quantity produced."})
        if self.pack_product_id and self.pack_product.specification != PRD_SPEC_FINISH_PACKING:
            raise ValidationError({"pack_product": "The bag must be a finish packing item."})

    def save(self, *args, **kwargs):
        if not self.line_number:
            last = (
                ProductConversionLine.all_objects.filter(conversion=self.conversion)
                .order_by("-line_number").values_list("line_number", flat=True).first() or 0
            )
            self.line_number = last + 1
        super().save(*args, **kwargs)
