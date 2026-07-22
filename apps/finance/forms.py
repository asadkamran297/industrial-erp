from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError

from apps.core.constants import ACCOUNT_LEDGER_GENERAL, NO, STATUS_ACTIVE
from apps.core.forms import AutoSelectSingleChoiceMixin

from .models import AccountConfiguration, AccountVoucher, AccountVoucherLine, ChartOfAccount, FiscalYear


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
            "code": forms.TextInput(attrs={"class": "form-input", "style": "text-transform:uppercase"}),
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
        return self.cleaned_data["account_no"].strip()


class AccountVoucherForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = AccountVoucher
        fields = (
            "voucher_date",
            "voucher_type",
            "account_no",
            "payment_method",
            "remarks",
            "status",
            "adj_entry",
            "adj_voucher",
        )
        widgets = {
            "voucher_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "voucher_type": forms.Select(attrs={"class": "form-select"}),
            "account_no": forms.TextInput(attrs={"class": "form-input"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "remarks": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "adj_entry": forms.Select(attrs={"class": "form-select"}),
            "adj_voucher": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["adj_voucher"].queryset = AccountVoucher.objects.order_by("-voucher_date", "-id")

    def clean_account_no(self):
        return self.cleaned_data["account_no"].strip()


class AccountVoucherLineForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = AccountVoucherLine
        fields = (
            "account_no",
            "payment_method",
            "debit_amount",
            "credit_amount",
            "remarks",
            "person_organization",
            "person_organization_title",
            "credit_card_payment",
            "credit_card_no",
            "credit_card_expiry",
            "receipt_no",
            "bank",
        )
        widgets = {
            "account_no": forms.TextInput(attrs={"class": "form-input"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "debit_amount": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "credit_amount": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "remarks": forms.Textarea(attrs={"class": "form-input", "rows": 2}),
            "person_organization": forms.TextInput(attrs={"class": "form-input"}),
            "person_organization_title": forms.TextInput(attrs={"class": "form-input"}),
            "credit_card_payment": forms.Select(attrs={"class": "form-select"}),
            "credit_card_no": forms.TextInput(attrs={"class": "form-input"}),
            "credit_card_expiry": forms.TextInput(attrs={"class": "form-input", "placeholder": "MM/YY"}),
            "receipt_no": forms.TextInput(attrs={"class": "form-input"}),
            "bank": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].required = False
        self.fields["remarks"].required = False
        self.fields["person_organization"].required = False
        self.fields["person_organization_title"].required = False
        self.fields["credit_card_payment"].required = False
        self.fields["credit_card_no"].required = False
        self.fields["credit_card_expiry"].required = False
        self.fields["receipt_no"].required = False
        self.fields["bank"].required = False
        self.fields["credit_card_payment"].initial = NO

    def clean_account_no(self):
        account_no = self.cleaned_data["account_no"].strip()
        if not ChartOfAccount.objects.filter(code=account_no, status=STATUS_ACTIVE, children__isnull=True).exists():
            raise ValidationError("Active leaf chart-of-account is required.")
        return account_no
