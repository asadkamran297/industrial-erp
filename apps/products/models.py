"""The mill's product tree and everything hung off it.

One table holds all three levels of the tree, because a group, a sub-group and
an item are the same thing seen at different depths: a name with a code segment
and a parent. Splitting them into three tables would mean three queries and
three sets of code to render one list.

The module keeps its own stock ledger. Nothing here reads or writes
``apps.inventory`` -- a flour mill counts wheat in and atta out through
grinding, not through the general item ledger, and the two must not be able to
drift into each other.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.core.constants import (
    PRD_BUYABLE_SPECS,
    PRD_LEDGER_SOURCE_CHOICES,
    PRD_LEVEL_CHOICES,
    PRD_LEVEL_GROUP,
    PRD_LEVEL_ITEM,
    PRD_PACKABLE_SPECS,
    PRD_SEGMENT_WIDTHS,
    PRD_SPEC_FINISH_PACKING,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    PRD_SPEC_RULES,
    PRD_SPECIFICATION_CHOICES,
    PRD_STATUS_CHOICES,
    PRD_UNIT_BASE_WEIGHT,
    PRD_UNIT_CHOICES,
    STATUS_ACTIVE,
)
from apps.core.models import BaseModel

SEGMENT_VALIDATOR = RegexValidator(r"^\d{2,3}$", "Code segment must be 2 or 3 digits.")


class ProductNode(BaseModel):
    """A node of the GG-SS-III tree: group, sub-group, or the item itself.

    Only a level-3 node is postable. A heading's code is written with 000 in the
    segments below it (``01-000-000``), which is what makes "ends in 000" the
    rule for "cannot be posted to" that the mill's clerks already use.
    """

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.PROTECT,
    )
    level = models.PositiveSmallIntegerField(choices=PRD_LEVEL_CHOICES)
    code_segment = models.CharField(max_length=3, validators=[SEGMENT_VALIDATOR])
    # Denormalised so the list screen can sort, search and group by code without
    # walking to the root for every row. Rebuilt on every save.
    complete_code = models.CharField(max_length=12, db_index=True)
    name = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=PRD_STATUS_CHOICES, default=STATUS_ACTIVE)

    # -- Item-only fields. Blank on a heading, which has none of them. -------
    starting_date = models.DateField(null=True, blank=True)
    specification = models.CharField(max_length=20, choices=PRD_SPECIFICATION_CHOICES, blank=True)
    quick_code = models.CharField(max_length=20, blank=True)
    unit = models.CharField(max_length=10, choices=PRD_UNIT_CHOICES, blank=True)
    # Kilograms in one unit. 1 for kg, 40 for a mound, the bag size for a piece.
    unit_weight = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    fix_weight = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    actual_weight = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    color = models.CharField(max_length=40, blank=True)

    class Meta:
        db_table = "prod_nodes"
        ordering = ["complete_code"]
        constraints = [
            # A segment is unique among its siblings, which is what makes the
            # assembled complete_code unique without a second uniqueness rule
            # that could disagree with this one.
            models.UniqueConstraint(
                fields=["parent", "code_segment"],
                condition=models.Q(deleted_at__isnull=True),
                name="prod_node_unique_segment_per_parent",
            ),
            models.UniqueConstraint(
                fields=["quick_code"],
                condition=models.Q(deleted_at__isnull=True) & ~models.Q(quick_code=""),
                name="prod_node_unique_quick_code",
            ),
        ]
        indexes = [
            # The list screen: filtered by status, read in code order.
            models.Index(fields=["status", "complete_code"], name="prod_node_status_code_idx"),
            # "every item under this sub-group", the tree render's inner loop.
            models.Index(fields=["parent", "code_segment"], name="prod_node_parent_seg_idx"),
            # The pickers on purchase, sale and packing screens filter on this.
            models.Index(fields=["specification", "status"], name="prod_node_spec_status_idx"),
            models.Index(fields=["quick_code"], name="prod_node_quick_code_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.complete_code} {self.name}"

    # -- Code assembly -------------------------------------------------------
    def build_complete_code(self) -> str:
        """``01``, ``01-01``, ``01-01-002`` -- as deep as the node itself goes."""
        segments = []
        node = self
        while node is not None:
            segments.append(node.code_segment)
            node = node.parent
        return "-".join(reversed(segments))

    @property
    def display_code(self) -> str:
        """The full-width code, headings padded with 000 in the levels below."""
        parts = self.complete_code.split("-")
        for level in range(self.level + 1, PRD_LEVEL_ITEM + 1):
            parts.append("0" * PRD_SEGMENT_WIDTHS[level])
        return "-".join(parts)

    @property
    def is_postable(self) -> bool:
        return self.level == PRD_LEVEL_ITEM

    @property
    def is_heading(self) -> bool:
        return self.level != PRD_LEVEL_ITEM

    # -- Specification rules -------------------------------------------------
    def _rule(self, name: str) -> bool:
        return PRD_SPEC_RULES.get(self.specification, {}).get(name, False)

    @property
    def can_buy(self) -> bool:
        return self._rule("can_buy")

    @property
    def can_produce(self) -> bool:
        return self._rule("can_produce")

    @property
    def can_sell(self) -> bool:
        return self._rule("can_sell")

    @property
    def keeps_stock(self) -> bool:
        return self._rule("keeps_stock")

    @property
    def effective_unit_weight(self) -> Decimal:
        """Kg in one unit: fixed by the unit where the unit fixes it."""
        base = PRD_UNIT_BASE_WEIGHT.get(self.unit)
        return Decimal(base) if base else (self.unit_weight or Decimal("0"))

    @property
    def stock_kg(self):
        """Total weight of what is on hand. Derived, never stored.

        Reads the ``stock`` annotation the list screen adds; a row fetched
        without it has no stock figure to weigh and reports zero rather than
        going back to the database once per row.
        """
        return (getattr(self, "stock", None) or Decimal("0")) * self.effective_unit_weight

    def clean(self):
        super().clean()
        # Derived here as well as in save(), because full_clean() checks the
        # field before save() would have filled it in.
        if self.parent_id and not self.level:
            self.level = self.parent.level + 1
        self.complete_code = self.build_complete_code()
        expected_width = PRD_SEGMENT_WIDTHS.get(self.level)
        if expected_width and len(self.code_segment or "") != expected_width:
            raise ValidationError({"code_segment": f"Level {self.level} code is {expected_width} digits."})
        if self.level == PRD_LEVEL_GROUP and self.parent_id:
            raise ValidationError({"parent": "A group sits at the top of the tree and has no parent."})
        if self.level != PRD_LEVEL_GROUP and not self.parent_id:
            raise ValidationError({"parent": "Choose the node this one sits under."})
        if self.parent_id and self.parent.level != self.level - 1:
            raise ValidationError({"parent": "A node must sit directly under the level above it."})
        if self.level == PRD_LEVEL_ITEM and not self.specification:
            raise ValidationError({"specification": "An item needs a specification."})

    def save(self, *args, **kwargs):
        if self.parent_id and not self.level:
            self.level = self.parent.level + 1
        self.level = self.level or PRD_LEVEL_GROUP
        self.complete_code = self.build_complete_code()
        super().save(*args, **kwargs)
        # A renumbered segment moves every code beneath it, so descendants are
        # rewritten rather than left holding a code that no longer exists.
        if self.level < PRD_LEVEL_ITEM:
            for child in self.children.all():
                if child.build_complete_code() != child.complete_code:
                    child.save()


class ProductAccountLink(BaseModel):
    """The purchase account a bought product is charged to.

    One row per purchasable product. A finish item or by-product never gets a
    row: it is produced, and a purchase account for it would be an invitation
    to book a purchase that cannot happen.
    """

    product = models.OneToOneField(
        ProductNode,
        related_name="account_link",
        on_delete=models.CASCADE,
    )
    purchase_account = models.ForeignKey(
        "finance.ChartOfAccount",
        related_name="product_purchase_links",
        on_delete=models.PROTECT,
    )

    class Meta:
        db_table = "prod_account_links"
        indexes = [models.Index(fields=["purchase_account"], name="prod_acct_link_acct_idx")]

    def __str__(self) -> str:
        return f"{self.product.name} -> {self.purchase_account.title}"

    def clean(self):
        super().clean()
        if self.product_id and self.product.specification not in PRD_BUYABLE_SPECS:
            raise ValidationError({"product": f"{self.product.get_specification_display()} is never bought."})


class RawBardanaLink(BaseModel):
    """The sack a wheat item arrives in.

    Wheat is bought by weight but delivered in sacks, and the sacks are stock in
    their own right until grinding empties them. The link is what lets a wheat
    purchase bring the right bardana in on the same document.
    """

    wheat_item = models.OneToOneField(
        ProductNode,
        related_name="raw_bardana_link",
        on_delete=models.CASCADE,
    )
    bardana_item = models.ForeignKey(
        ProductNode,
        related_name="raw_bardana_uses",
        on_delete=models.PROTECT,
    )

    class Meta:
        db_table = "prod_raw_bardana_links"
        indexes = [models.Index(fields=["bardana_item"], name="prod_raw_bard_item_idx")]

    def __str__(self) -> str:
        return f"{self.wheat_item.name} -> {self.bardana_item.name}"

    def clean(self):
        super().clean()
        if self.wheat_item_id and self.wheat_item.specification != PRD_SPEC_RAW_ITEM:
            raise ValidationError({"wheat_item": "Only a raw item arrives in bardana."})
        if self.bardana_item_id and self.bardana_item.specification != PRD_SPEC_RAW_PACKING:
            raise ValidationError({"bardana_item": "The sack must be a raw packing item."})


class FinishBardanaLink(BaseModel):
    """The bag a finished product is packed in.

    Grinding reads this table to decide what to consume when it books output.
    Loose sales point at the "Open Stock without Bardana" packing row rather
    than at nothing, so the grinding code has one path instead of two.
    """

    finish_item = models.OneToOneField(
        ProductNode,
        related_name="finish_bardana_link",
        on_delete=models.CASCADE,
    )
    bag_item = models.ForeignKey(
        ProductNode,
        related_name="finish_bardana_uses",
        on_delete=models.PROTECT,
    )

    class Meta:
        db_table = "prod_finish_bardana_links"
        indexes = [models.Index(fields=["bag_item"], name="prod_fin_bard_item_idx")]

    def __str__(self) -> str:
        return f"{self.finish_item.name} -> {self.bag_item.name}"

    def clean(self):
        super().clean()
        if self.finish_item_id and self.finish_item.specification not in PRD_PACKABLE_SPECS:
            raise ValidationError({"finish_item": "Only a produced item is packed."})
        if self.bag_item_id and self.bag_item.specification != PRD_SPEC_FINISH_PACKING:
            raise ValidationError({"bag_item": "The bag must be a finish packing item."})


class ProductOpeningBalance(BaseModel):
    """What was on hand before the module started counting.

    Held on its own rather than as a column on the product, because the opening
    is an event with a date: it is posted to the ledger like any other movement,
    and editing it has to move that ledger row rather than silently disagree
    with it.
    """

    product = models.OneToOneField(
        ProductNode,
        related_name="opening_balance",
        on_delete=models.CASCADE,
    )
    as_of_date = models.DateField()
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    rate = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "prod_opening_balances"
        indexes = [models.Index(fields=["as_of_date"], name="prod_opening_date_idx")]

    def __str__(self) -> str:
        return f"{self.product.name} opening {self.quantity}"


class ProductRate(BaseModel):
    """A product's rate, kept as history rather than overwritten.

    A rate update writes a new row and clears the flag on the old one, so a
    document raised last month can still be explained by the rate that was
    current when it was raised.
    """

    product = models.ForeignKey(
        ProductNode,
        related_name="rates",
        on_delete=models.CASCADE,
    )
    rate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    effective_date = models.DateField()
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = "prod_rates"
        ordering = ["-effective_date", "-id"]
        indexes = [
            # "the rate history of this product, newest first" -- the only way
            # this table is ever read.
            models.Index(fields=["product", "-effective_date"], name="prod_rate_prod_date_idx"),
            models.Index(fields=["product", "is_current"], name="prod_rate_current_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} @ {self.rate}"


class ProductLedger(BaseModel):
    """Every movement of a stocked product. Stock is the sum of this table.

    Quantity is signed: in is positive, out is negative, so a balance is one
    SUM with no CASE over movement types. ``source`` and ``reference`` say what
    caused the row without this module having to import the module that caused
    it.
    """

    product = models.ForeignKey(
        ProductNode,
        related_name="ledger_entries",
        on_delete=models.PROTECT,
    )
    entry_date = models.DateField()
    source = models.CharField(max_length=30, choices=PRD_LEDGER_SOURCE_CHOICES)
    # Free-form pointer at the document that caused this: "PI-0012", "GRD-88".
    reference = models.CharField(max_length=60, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    rate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.CharField(max_length=240, blank=True)

    class Meta:
        db_table = "prod_ledgers"
        ordering = ["-entry_date", "-id"]
        indexes = [
            # Per-product history, and the running balance built from it.
            models.Index(fields=["product", "-entry_date"], name="prod_ledger_prod_date_idx"),
            models.Index(fields=["source", "-entry_date"], name="prod_ledger_src_date_idx"),
            models.Index(fields=["reference"], name="prod_ledger_reference_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} {self.quantity} on {self.entry_date}"
