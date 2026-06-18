from django import forms

from .models import Branch, Organization


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ("parent", "title", "code", "status")
        widgets = {
            "parent": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "Organization title"}),
            "code": forms.TextInput(attrs={"class": "form-input", "placeholder": "Organization code"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }


class BranchForm(forms.ModelForm):
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
