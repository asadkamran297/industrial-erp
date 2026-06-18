from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError

from apps.core.constants import (
    ACCOUNT_LEDGER_GENERAL,
    ACCOUNT_LEDGER_SUBSIDIARY,
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_LIABILITY,
    ACCOUNT_TYPE_REVENUE,
    STATUS_ACTIVE,
    VOUCHER_TYPE_PAYMENT,
    VOUCHER_TYPE_RECEIPT,
    YES,
)
from apps.core.forms import AutoSelectSingleChoiceMixin

from .models import AccountConfiguration, AccountVoucher, AccountVoucherLine, FiscalYear


class FiscalYearForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = FiscalYear
        fields = ("title", "code", "start_date", "end_date", "status")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input"}),
            "code": forms.TextInput(attrs={"class": "form-input"}),
            "start_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and not end_date:
            cleaned_data["end_date"] = start_date + timedelta(days=364)
        if start_date and end_date and end_date <= start_date:
            self.add_error("end_date", "End date must be after start date.")
        return cleaned_data


class AccountConfigurationForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = AccountConfiguration
        fields = (
            "title",
            "code",
            "nature",
            "account_no",
            "account_type",
            "account_ledger",
            "balance_income",
            "post_to_account",
            "account_nature",
            "status",
        )
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input"}),
            "code": forms.TextInput(attrs={"class": "form-input"}),
            "nature": forms.Select(attrs={"class": "form-select"}),
            "account_no": forms.TextInput(attrs={"class": "form-input"}),
            "account_type": forms.Select(attrs={"class": "form-select"}),
            "account_ledger": forms.Select(attrs={"class": "form-select"}),
            "balance_income": forms.Select(attrs={"class": "form-select"}),
            "post_to_account": forms.Select(attrs={"class": "form-select"}),
            "account_nature": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = AccountConfiguration.objects.filter(account_ledger=ACCOUNT_LEDGER_GENERAL, status=STATUS_ACTIVE)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["post_to_account"].queryset = qs.order_by("account_no")

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def clean_account_no(self):
        account_no = self.cleaned_data["account_no"].strip()
        first_general = (
            AccountConfiguration.objects.filter(account_ledger=ACCOUNT_LEDGER_GENERAL)
            .exclude(pk=self.instance.pk or None)
            .order_by("id")
            .first()
        )
        if first_general and len(account_no) != len(first_general.account_no):
            raise ValidationError(f"Account number must be {len(first_general.account_no)} digits/characters.")
        return account_no

    def clean(self):
        cleaned_data = super().clean()
        account_ledger = cleaned_data.get("account_ledger")
        post_to_account = cleaned_data.get("post_to_account")
        existing_accounts = AccountConfiguration.objects.exclude(pk=self.instance.pk or None)
        if not existing_accounts.exists() and account_ledger != ACCOUNT_LEDGER_GENERAL:
            self.add_error("account_ledger", "First account must be a general account.")
        if account_ledger == ACCOUNT_LEDGER_SUBSIDIARY and not post_to_account:
            self.add_error("post_to_account", "Subsidiary account must post to a general account.")
        if account_ledger == ACCOUNT_LEDGER_GENERAL and post_to_account:
            self.add_error("post_to_account", "General account cannot post to another account.")
        return cleaned_data


class AccountVoucherForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = AccountVoucher
        fields = (
            "voucher_date",
            "voucher_type",
            "account_no",
            "payment_method",
            "debit_amount",
            "credit_amount",
            "remarks",
            "status",
            "posted",
            "adj_entry",
            "adj_voucher",
            "credit_card_payment",
            "credit_card_no",
            "credit_card_expiry",
        )
        widgets = {
            "voucher_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "voucher_type": forms.Select(attrs={"class": "form-select"}),
            "account_no": forms.TextInput(attrs={"class": "form-input"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "debit_amount": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "credit_amount": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "remarks": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "posted": forms.Select(attrs={"class": "form-select"}),
            "adj_entry": forms.Select(attrs={"class": "form-select"}),
            "adj_voucher": forms.Select(attrs={"class": "form-select"}),
            "credit_card_payment": forms.Select(attrs={"class": "form-select"}),
            "credit_card_no": forms.TextInput(attrs={"class": "form-input"}),
            "credit_card_expiry": forms.TextInput(attrs={"class": "form-input", "placeholder": "MM/YY"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        debit = cleaned_data.get("debit_amount") or 0
        credit = cleaned_data.get("credit_amount") or 0
        account_no = cleaned_data.get("account_no", "").strip()
        voucher_type = cleaned_data.get("voucher_type")
        if debit <= 0 and credit <= 0:
            raise ValidationError("Debit or credit amount is required.")
        account = AccountConfiguration.objects.filter(account_no=account_no, status=STATUS_ACTIVE).first()
        if not account:
            self.add_error("account_no", "Active account number is required.")
        elif voucher_type == VOUCHER_TYPE_PAYMENT and account.account_type not in (ACCOUNT_TYPE_EXPENSE, ACCOUNT_TYPE_LIABILITY):
            self.add_error("account_no", "Payment voucher account must be expense or liability.")
        elif voucher_type == VOUCHER_TYPE_RECEIPT and account.account_type not in (ACCOUNT_TYPE_REVENUE, ACCOUNT_TYPE_ASSET):
            self.add_error("account_no", "Receipt voucher account must be revenue or asset.")
        if cleaned_data.get("credit_card_payment") == YES and not cleaned_data.get("credit_card_no"):
            self.add_error("credit_card_no", "Credit card number is required.")
        return cleaned_data


class AccountVoucherLineForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = AccountVoucherLine
        fields = ("account_no", "payment_method", "debit_amount", "credit_amount", "remarks", "person_organization", "person_organization_title")
        widgets = {
            "account_no": forms.TextInput(attrs={"class": "form-input"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "debit_amount": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "credit_amount": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "remarks": forms.Textarea(attrs={"class": "form-input", "rows": 2}),
            "person_organization": forms.TextInput(attrs={"class": "form-input"}),
            "person_organization_title": forms.TextInput(attrs={"class": "form-input"}),
        }

    def clean_account_no(self):
        account_no = self.cleaned_data["account_no"].strip()
        if not AccountConfiguration.objects.filter(account_no=account_no, status=STATUS_ACTIVE).exists():
            raise ValidationError("Active account number is required.")
        return account_no

    def clean(self):
        cleaned_data = super().clean()
        debit = cleaned_data.get("debit_amount") or 0
        credit = cleaned_data.get("credit_amount") or 0
        if debit <= 0 and credit <= 0:
            raise ValidationError("Debit or credit amount is required.")
        return cleaned_data
