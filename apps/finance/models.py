from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.constants import (
    ACCOUNT_LEDGER_GENERAL,
    ACCOUNT_LEDGER_SUBSIDIARY,
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_LIABILITY,
    ACCOUNT_TYPE_REVENUE,
    FIN_ACCOUNT_LEDGER_CHOICES,
    FIN_ACCOUNT_NATURE_CHOICES,
    FIN_ACCOUNT_TYPE_CHOICES,
    FIN_ACCOUNT_TYPE_CODE_MAP,
    FIN_BALANCE_INCOME_CHOICES,
    FIN_COA_ACCOUNT_TYPE_CHOICES,
    FIN_VOUCHER_STATUS_CHOICES,
    FIN_VOUCHER_TYPE_CHOICES,
    NO,
    RECORD_STATUS_CHOICES,
    STATUS_ACTIVE,
    STATUS_CREATED,
    STATUS_INACTIVE,
    VOUCHER_TYPE_PAYMENT,
    YES,
    YES_NO_CHOICES,
)
from apps.core.models import BaseModel


class FiscalYear(BaseModel):
    title = models.CharField(max_length=120)
    code = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        db_table = "fin_fiscal_years"
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return self.title

    def clean(self):
        errors = {}
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            errors["end_date"] = "End date must be after start date."
        if errors:
            raise ValidationError(errors)

    def generate_periods(self) -> None:
        FiscalPeriod.objects.get_or_create(
            fiscal_year=self,
            code=f"{self.code}-00",
            defaults={"title": "Opening", "status": STATUS_INACTIVE},
        )
        current = self.start_date
        for index in range(1, 13):
            FiscalPeriod.objects.get_or_create(
                fiscal_year=self,
                code=f"{self.code}-{index:02d}",
                defaults={"title": current.strftime("%B %Y"), "status": STATUS_INACTIVE},
            )
            year = current.year + (1 if current.month == 12 else 0)
            month = 1 if current.month == 12 else current.month + 1
            current = date(year, month, min(current.day, monthrange(year, month)[1]))
        FiscalPeriod.objects.get_or_create(
            fiscal_year=self,
            code=f"{self.code}-99",
            defaults={"title": "Closing", "status": STATUS_INACTIVE},
        )


class FiscalPeriod(BaseModel):
    fiscal_year = models.ForeignKey(FiscalYear, related_name="periods", on_delete=models.CASCADE, db_column="fin_fiscal_year_id")
    title = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_INACTIVE)

    class Meta:
        db_table = "fin_fiscal_periods"
        ordering = ["fiscal_year", "code"]
        unique_together = ("fiscal_year", "code")

    def __str__(self) -> str:
        return f"{self.fiscal_year} - {self.title}"


class AccountConfiguration(BaseModel):
    title = models.CharField(max_length=180)
    code = models.CharField(max_length=60, unique=True)
    nature = models.CharField(max_length=20, choices=FIN_ACCOUNT_TYPE_CHOICES)
    account_no = models.CharField(max_length=80, unique=True)
    account_type = models.CharField(max_length=20, choices=FIN_ACCOUNT_TYPE_CHOICES)
    account_ledger = models.CharField(max_length=1, choices=FIN_ACCOUNT_LEDGER_CHOICES, default=ACCOUNT_LEDGER_GENERAL)
    balance_income = models.CharField(max_length=1, choices=FIN_BALANCE_INCOME_CHOICES)
    post_to_account = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="subsidiary_accounts",
        on_delete=models.PROTECT,
        db_column="post_to_account",
    )
    account_nature = models.CharField(max_length=1, choices=FIN_ACCOUNT_NATURE_CHOICES)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "fin_account_configuration"
        ordering = ["account_no"]

    def __str__(self) -> str:
        return f"{self.account_no} - {self.title}"

    def clean(self):
        errors = {}
        existing_accounts = AccountConfiguration.objects.exclude(pk=self.pk)
        account_no = (self.account_no or "").strip()
        code = (self.code or "").strip().upper()

        first_general = existing_accounts.filter(account_ledger=ACCOUNT_LEDGER_GENERAL).order_by("id").first()
        if not existing_accounts.exists() and self.account_ledger != ACCOUNT_LEDGER_GENERAL:
            errors["account_ledger"] = "First account must be a general account."
        if first_general and account_no and len(account_no) != len(first_general.account_no):
            errors["account_no"] = f"Account number must be {len(first_general.account_no)} digits/characters."

        expected_prefix = FIN_ACCOUNT_TYPE_CODE_MAP.get(self.account_type, "")
        if expected_prefix and code and not code.startswith(expected_prefix):
            errors["code"] = f"Code must start with {expected_prefix} for {self.get_account_type_display().lower()} accounts."

        if self.account_ledger == ACCOUNT_LEDGER_SUBSIDIARY and not self.post_to_account:
            errors["post_to_account"] = "Subsidiary account must post to a general account."
        if self.account_ledger == ACCOUNT_LEDGER_GENERAL and self.post_to_account:
            errors["post_to_account"] = "General account cannot post to another account."
        if self.post_to_account and self.post_to_account.account_ledger != ACCOUNT_LEDGER_GENERAL:
            errors["post_to_account"] = "Post to account must be a general account."
        if self.post_to_account and self.post_to_account.status != STATUS_ACTIVE:
            errors["post_to_account"] = "Post to account must be active."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.account_no = (self.account_no or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class ChartOfAccount(BaseModel):
    """Hierarchical chart of accounts.

    A self-referencing tree of unlimited depth. Top-level nodes (``parent`` is
    null) are the five roots identified by ``account_type``; every descendant
    inherits its root's ``account_type`` automatically on save. ``is_group``
    marks a heading/folder node; leaves (``is_group=False``) are the postable
    accounts. ``sort_order`` drives sibling ordering for drag-and-drop.
    """

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
        db_column="parent_id",
    )
    title = models.CharField(max_length=180)
    code = models.CharField(max_length=60, blank=True)
    account_type = models.CharField(max_length=20, choices=FIN_COA_ACCOUNT_TYPE_CHOICES)
    is_group = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "fin_chart_of_accounts"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.title

    # Segmented account-code mask: LL-LL-LLL-LLLL (one segment per level).
    CODE_SEGMENT_WIDTHS = (2, 2, 3, 4)
    CODE_SEPARATOR = "-"
    MAX_LEVELS = len(CODE_SEGMENT_WIDTHS)

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def depth(self) -> int:
        """1 for roots, +1 per level down."""
        level, cursor = 1, self
        while cursor.parent_id is not None:
            level += 1
            cursor = cursor.parent
        return level

    @classmethod
    def format_code(cls, indices: list[int]) -> str:
        """Build a ``LL-LL-LLL-LLLL`` code from 1-based indices per level.

        Levels not yet reached are zero-filled, e.g. a level-1 node at
        position 3 -> ``03-00-000-0000``; its 2nd child -> ``03-02-000-0000``.
        """
        parts = []
        for level, width in enumerate(cls.CODE_SEGMENT_WIDTHS):
            value = indices[level] if level < len(indices) else 0
            parts.append(str(value).zfill(width))
        return cls.CODE_SEPARATOR.join(parts)

    @classmethod
    def rebuild_codes(cls) -> dict[int, str]:
        """Recompute every account's segmented code from its tree position.

        Returns an ``{id: code}`` map of the nodes whose code changed.
        """
        nodes = list(cls.objects.filter(status=STATUS_ACTIVE).order_by("sort_order", "id"))
        children_map: dict[int | None, list] = {}
        for node in nodes:
            children_map.setdefault(node.parent_id, []).append(node)

        changed: dict[int, str] = {}
        to_update: list = []

        def walk(parent_id, indices):
            for index, node in enumerate(children_map.get(parent_id, []), start=1):
                node_indices = indices + [index]
                code = cls.format_code(node_indices)
                if node.code != code:
                    node.code = code
                    changed[node.id] = code
                    to_update.append(node)
                walk(node.id, node_indices)

        walk(None, [])
        if to_update:
            cls.objects.bulk_update(to_update, ["code"])
        return changed

    def clean(self):
        # A node cannot be its own ancestor (guards drag-drop reparenting).
        ancestor = self.parent
        while ancestor is not None:
            if ancestor.pk == self.pk:
                raise ValidationError({"parent": "An account cannot be moved under its own descendant."})
            ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        if self.parent_id:
            self.account_type = self.parent.account_type
        super().save(*args, **kwargs)


class AccountVoucher(BaseModel):
    voucher_no = models.CharField(max_length=80, unique=True, blank=True)
    account_no = models.CharField(max_length=80)
    voucher_date = models.DateField(default=timezone.localdate)
    voucher_type = models.CharField(max_length=2, choices=FIN_VOUCHER_TYPE_CHOICES)
    payment_method = models.ForeignKey(
        "configurations.PaymentMethod", null=True, blank=True, on_delete=models.SET_NULL, db_column="conf_payment_method_id"
    )
    debit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=FIN_VOUCHER_STATUS_CHOICES, default=STATUS_CREATED)
    posted = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=NO)
    adj_entry = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=NO)
    adj_voucher = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, db_column="adj_voucher_id")
    credit_card_payment = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=NO)
    credit_card_no = models.CharField(max_length=40, blank=True)
    credit_card_expiry = models.CharField(max_length=10, blank=True)

    class Meta:
        db_table = "fin_account_voucher"
        ordering = ["-voucher_date", "-id"]

    def __str__(self) -> str:
        return self.voucher_no or "New voucher"

    @property
    def is_balanced(self) -> bool:
        return self.debit_amount == self.credit_amount and self.debit_amount > 0

    @property
    def balance_difference(self) -> Decimal:
        return (self.debit_amount or Decimal("0.00")) - (self.credit_amount or Decimal("0.00"))

    def clean(self):
        errors = {}
        self.account_no = (self.account_no or "").strip()
        account = AccountConfiguration.objects.filter(account_no=self.account_no, status=STATUS_ACTIVE).first()
        if not account:
            errors["account_no"] = "Active account number is required."
        elif self.voucher_type == VOUCHER_TYPE_PAYMENT and account.account_type not in (ACCOUNT_TYPE_EXPENSE, ACCOUNT_TYPE_LIABILITY):
            errors["account_no"] = "Payment voucher account must be expense or liability."
        elif self.voucher_type != VOUCHER_TYPE_PAYMENT and account.account_type not in (ACCOUNT_TYPE_REVENUE, ACCOUNT_TYPE_ASSET):
            errors["account_no"] = "Receipt voucher account must be revenue or asset."

        if self.adj_entry == YES and not self.adj_voucher:
            errors["adj_voucher"] = "Adjustment voucher is required when adjustment entry is yes."
        if self.adj_entry == NO and self.adj_voucher:
            errors["adj_voucher"] = "Adjustment voucher can only be set when adjustment entry is yes."

        has_lines = self.pk and self.lines.exists()
        if self.status != STATUS_CREATED or self.posted == YES:
            if not has_lines:
                errors["status"] = "Voucher lines are required before submission or posting."
            elif not self.is_balanced:
                errors["status"] = "Voucher cannot move forward until debit and credit totals are equal."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.voucher_no:
            prefix = "E" if self.voucher_type == VOUCHER_TYPE_PAYMENT else "R"
            last_id = AccountVoucher.all_objects.order_by("-id").values_list("id", flat=True).first() or 0
            self.voucher_no = f"{prefix}-{last_id + 1:06d}"
        self.full_clean()
        super().save(*args, **kwargs)

    def recalculate_totals(self, save=True):
        debit_total = Decimal("0.00")
        credit_total = Decimal("0.00")
        for line in self.lines.all():
            debit_total += line.debit_amount or Decimal("0.00")
            credit_total += line.credit_amount or Decimal("0.00")
        self.debit_amount = debit_total
        self.credit_amount = credit_total
        if save:
            AccountVoucher.all_objects.filter(pk=self.pk).update(
                debit_amount=debit_total,
                credit_amount=credit_total,
                updated_at=timezone.now(),
            )
            self.refresh_from_db(fields=["debit_amount", "credit_amount", "updated_at"])


class AccountVoucherLine(BaseModel):
    voucher = models.ForeignKey(AccountVoucher, related_name="lines", on_delete=models.CASCADE, db_column="fin_account_voucher_id")
    line_number = models.PositiveIntegerField()
    voucher_no = models.CharField(max_length=80)
    account_no = models.CharField(max_length=80)
    voucher_date = models.DateField()
    payment_method = models.ForeignKey(
        "configurations.PaymentMethod", null=True, blank=True, on_delete=models.SET_NULL, db_column="conf_payment_method_id"
    )
    debit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.TextField(blank=True)
    person_organization = models.CharField(max_length=180, blank=True)
    person_organization_title = models.CharField(max_length=180, blank=True)
    credit_card_payment = models.CharField(max_length=1, choices=YES_NO_CHOICES, default=NO)
    credit_card_no = models.CharField(max_length=40, blank=True)
    credit_card_expiry = models.CharField(max_length=10, blank=True)
    receipt_no = models.CharField(max_length=80, blank=True)
    bank = models.ForeignKey(
        "configurations.Bank",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="conf_bank_id",
    )

    class Meta:
        db_table = "fin_account_voucher_lines"
        ordering = ["voucher", "line_number"]
        unique_together = ("voucher", "line_number")

    def __str__(self) -> str:
        return f"{self.voucher_no} - {self.line_number}"

    def clean(self):
        errors = {}
        self.account_no = (self.account_no or "").strip()
        account = AccountConfiguration.objects.filter(account_no=self.account_no, status=STATUS_ACTIVE).first()
        if not account:
            errors["account_no"] = "Active account number is required."

        debit = self.debit_amount or Decimal("0.00")
        credit = self.credit_amount or Decimal("0.00")
        if (debit > 0 and credit > 0) or (debit <= 0 and credit <= 0):
            errors["debit_amount"] = "Enter either debit or credit amount."
            errors["credit_amount"] = "Enter either debit or credit amount."

        payment_method_title = (self.payment_method.title if self.payment_method else "").strip().lower()
        if self.credit_card_payment == YES:
            if self.voucher and self.voucher.voucher_type != "RV":
                errors["credit_card_payment"] = "Credit card payment is only allowed on receipt vouchers."
            if payment_method_title != "card":
                errors["payment_method"] = "Payment method must be Card for credit card payment."
            if not self.credit_card_no:
                errors["credit_card_no"] = "Credit card number is required."
            if not self.credit_card_expiry:
                errors["credit_card_expiry"] = "Credit card expiry is required."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.voucher.recalculate_totals()

    def soft_delete(self, user=None) -> None:
        super().soft_delete(user=user)
        self.voucher.recalculate_totals()
