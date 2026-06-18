from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import AutoSelectSingleChoiceMixin

from .models import Employee, EmployeeExperience, EmployeeQualification


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


class EmployeeExperienceForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = EmployeeExperience
        fields = ("organization", "from_date", "to_date", "leave_reason", "salary")
        widgets = {
            "organization": forms.TextInput(attrs={"class": "form-input"}),
            "from_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "to_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "leave_reason": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "salary": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        if from_date and to_date and to_date < from_date:
            self.add_error("to_date", "To date cannot be before from date.")
        return cleaned_data


class EmployeeQualificationForm(AutoSelectSingleChoiceMixin, forms.ModelForm):
    class Meta:
        model = EmployeeQualification
        fields = ("qualification", "specialization", "qualification_type", "institute", "from_date", "to_date", "status")
        widgets = {
            "qualification": forms.Select(attrs={"class": "form-select"}),
            "specialization": forms.Select(attrs={"class": "form-select"}),
            "qualification_type": forms.Select(attrs={"class": "form-select"}),
            "institute": forms.TextInput(attrs={"class": "form-input"}),
            "from_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "to_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        if from_date and to_date and to_date < from_date:
            self.add_error("to_date", "To date cannot be before from date.")
        return cleaned_data
