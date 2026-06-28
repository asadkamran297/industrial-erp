from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import AutoSelectSingleChoiceMixin

from .models import Branch, Organization


class OrganizationForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = Organization
        fields = ("parent", "title", "code", "logo", "phone", "cell", "fax", "email", "website", "address", "status")
        widgets = {
            "parent": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "Organization title"}),
            "code": forms.TextInput(attrs={"class": "form-input", "placeholder": "Unique code e.g. MAIN"}),
            "logo": forms.TextInput(attrs={"class": "form-input", "placeholder": "Logo URL (https://...)"}),
            "phone": forms.TextInput(attrs={"class": "form-input", "placeholder": "+92-42-XXXXXXX"}),
            "cell": forms.TextInput(attrs={"class": "form-input", "placeholder": "+92-3XX-XXXXXXX"}),
            "fax": forms.TextInput(attrs={"class": "form-input", "placeholder": "Fax number"}),
            "email": forms.EmailInput(attrs={"class": "form-input", "placeholder": "info@company.pk"}),
            "website": forms.TextInput(attrs={"class": "form-input", "placeholder": "https://www.company.pk"}),
            "address": forms.Textarea(attrs={"class": "form-input", "rows": 3, "placeholder": "Registered address"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        qs = Organization.all_objects.filter(code__iexact=code, deleted_at__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Organization code already exists.")
        return code

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.pk and cleaned_data.get("parent") and cleaned_data["parent"].pk == self.instance.pk:
            self.add_error("parent", "Organization cannot be its own parent.")
        return cleaned_data


class BranchForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = Branch
        fields = (
            "organization",
            "city",
            "parent",
            "title",
            "code",
            "address",
            "phone",
            "email",
            "lat",
            "lng",
            "fax",
            "status",
        )
        widgets = {
            "organization": forms.Select(attrs={"class": "form-select"}),
            "city": forms.Select(attrs={"class": "form-select"}),
            "parent": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "Branch title"}),
            "code": forms.TextInput(attrs={"class": "form-input", "placeholder": "Branch code"}),
            "address": forms.Textarea(attrs={"class": "form-input", "rows": 3, "placeholder": "Address"}),
            "phone": forms.TextInput(attrs={"class": "form-input", "placeholder": "Phone"}),
            "email": forms.EmailInput(attrs={"class": "form-input", "placeholder": "Email"}),
            "lat": forms.NumberInput(attrs={"class": "form-input", "step": "0.0000001"}),
            "lng": forms.NumberInput(attrs={"class": "form-input", "step": "0.0000001"}),
            "fax": forms.TextInput(attrs={"class": "form-input", "placeholder": "Fax"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        qs = Branch.all_objects.filter(code__iexact=code, deleted_at__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Branch code already exists.")
        return code

    def clean(self):
        cleaned_data = super().clean()
        organization = cleaned_data.get("organization")
        parent = cleaned_data.get("parent")
        if self.instance.pk and parent and parent.pk == self.instance.pk:
            self.add_error("parent", "Branch cannot be its own parent.")
        if organization and parent and parent.organization_id != organization.pk:
            self.add_error("parent", "Parent branch must belong to the selected organization.")
        return cleaned_data
