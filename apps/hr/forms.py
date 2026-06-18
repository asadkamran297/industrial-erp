from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import AutoSelectSingleChoiceMixin

from .models import Employee


class EmployeeForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = Employee
        fields = (
            "organization",
            "branch",
            "salutation",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "father_husband_name",
            "cnic",
            "dob",
            "doj",
            "contact",
            "address",
            "designation",
            "department",
            "gender",
            "blood_group",
            "job_type",
            "religion",
            "marital_status",
            "salary",
            "bank",
            "account_number",
            "emergency_contact",
            "status",
        )
        widgets = {
            field: forms.Select(attrs={"class": "form-select"})
            for field in (
                "organization",
                "branch",
                "salutation",
                "designation",
                "department",
                "gender",
                "blood_group",
                "job_type",
                "religion",
                "marital_status",
                "status",
            )
        }
        widgets.update(
            {
                "first_name": forms.TextInput(attrs={"class": "form-input"}),
                "middle_name": forms.TextInput(attrs={"class": "form-input"}),
                "last_name": forms.TextInput(attrs={"class": "form-input"}),
                "email": forms.EmailInput(attrs={"class": "form-input"}),
                "father_husband_name": forms.TextInput(attrs={"class": "form-input"}),
                "cnic": forms.TextInput(attrs={"class": "form-input"}),
                "dob": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
                "doj": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
                "contact": forms.TextInput(attrs={"class": "form-input"}),
                "address": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
                "salary": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
                "bank": forms.TextInput(attrs={"class": "form-input"}),
                "account_number": forms.TextInput(attrs={"class": "form-input"}),
                "emergency_contact": forms.TextInput(attrs={"class": "form-input"}),
            }
        )

    def clean_cnic(self):
        cnic = self.cleaned_data["cnic"].strip()
        qs = Employee.all_objects.filter(cnic__iexact=cnic, deleted_at__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("CNIC already exists.")
        return cnic

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get("first_name", "").strip()
        middle_name = cleaned_data.get("middle_name", "").strip()
        last_name = cleaned_data.get("last_name", "").strip()
        cleaned_data["full_name"] = " ".join(part for part in (first_name, middle_name, last_name) if part)
        branch = cleaned_data.get("branch")
        organization = cleaned_data.get("organization")
        if branch and organization and branch.organization_id != organization.pk:
            self.add_error("branch", "Branch must belong to the selected organization.")
        return cleaned_data

    def save(self, commit=True):
        self.instance.full_name = self.cleaned_data["full_name"]
        return super().save(commit)
