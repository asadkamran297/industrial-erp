from calendar import monthrange
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.constants import (
    ACCOUNT_LEDGER_GENERAL,
    ACCOUNT_LEDGER_SUBSIDIARY,
    FIN_ACCOUNT_LEDGER_CHOICES,
    FIN_ACCOUNT_NATURE_CHOICES,
    FIN_ACCOUNT_TYPE_CHOICES,
    FIN_BALANCE_INCOME_CHOICES,
    FIN_VOUCHER_STATUS_CHOICES,
    FIN_VOUCHER_TYPE_CHOICES,
    NO,
    RECORD_STATUS_CHOICES,
    STATUS_ACTIVE,
    STATUS_CREATED,
    VOUCHER_TYPE_PAYMENT,
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

    def generate_periods(self) -> None:
        FiscalPeriod.objects.get_or_create(
            fiscal_year=self,
            code=f"{self.code}-OPEN",
            defaults={"title": "Opening", "status": STATUS_ACTIVE},
        )
        current = self.start_date
        for index in range(1, 13):
            FiscalPeriod.objects.get_or_create(
                fiscal_year=self,
                code=f"{self.code}-{index:02d}",
                defaults={"title": current.strftime("%B %Y"), "status": STATUS_ACTIVE},
            )
            year = current.year + (1 if current.month == 12 else 0)
            month = 1 if current.month == 12 else current.month + 1
            current = date(year, month, min(current.day, monthrange(year, month)[1]))
        FiscalPeriod.objects.get_or_create(
            fiscal_year=self,
            code=f"{self.code}-99",
            defaults={"title": "Closing", "status": STATUS_ACTIVE},
        )


class FiscalPeriod(BaseModel):
    fiscal_year = models.ForeignKey(FiscalYear, related_name="periods", on_delete=models.CASCADE, db_column="fin_fiscal_year_id")
    title = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

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

    def save(self, *args, **kwargs):
        if not self.voucher_no:
            prefix = "E" if self.voucher_type == VOUCHER_TYPE_PAYMENT else "R"
            last_id = AccountVoucher.all_objects.order_by("-id").values_list("id", flat=True).first() or 0
            self.voucher_no = f"{prefix}-{last_id + 1:06d}"
        super().save(*args, **kwargs)


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

    class Meta:
        db_table = "fin_account_voucher_lines"
        ordering = ["voucher", "line_number"]
        unique_together = ("voucher", "line_number")

    def __str__(self) -> str:
        return f"{self.voucher_no} - {self.line_number}"
