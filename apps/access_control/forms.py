from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.core.constants import STATUS_ACTIVE

from .models import Permission, Role, RolePermission, UserAssignment

User = get_user_model()


class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.filter(status=STATUS_ACTIVE).order_by("seq", "title"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Role
        fields = ("title", "status", "permissions")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "Role title"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["permissions"].initial = Permission.objects.filter(role_links__role=self.instance)

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        qs = Role.all_objects.filter(title__iexact=title, deleted_at__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Role title already exists.")
        return title

    def save(self, commit=True):
        role = super().save(commit)
        if commit:
            RolePermission.objects.filter(role=role).delete()
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, permission=permission) for permission in self.cleaned_data["permissions"]]
            )
        return role


class PermissionForm(forms.ModelForm):
    class Meta:
        model = Permission
        fields = ("title", "code", "seq", "status")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "Permission title"}),
            "code": forms.TextInput(attrs={"class": "form-input", "placeholder": "module.action"}),
            "seq": forms.NumberInput(attrs={"class": "form-input", "min": 0}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_code(self):
        code = self.cleaned_data["code"].strip().lower()
        qs = Permission.all_objects.filter(code__iexact=code, deleted_at__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Permission code already exists.")
        if "." not in code:
            raise ValidationError("Use permission code format like module.action.")
        return code

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        qs = Permission.all_objects.filter(title__iexact=title, deleted_at__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Permission title already exists.")
        return title


class UserAssignmentForm(forms.ModelForm):
    class Meta:
        model = UserAssignment
        fields = ("user", "organization", "branch", "role", "start_date", "end_date", "is_primary", "status")
        widgets = {
            "user": forms.Select(attrs={"class": "form-select"}),
            "organization": forms.Select(attrs={"class": "form-select"}),
            "branch": forms.Select(attrs={"class": "form-select"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "start_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "is_primary": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-slate-300 text-[var(--primary-color)]"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["role"].queryset = Role.objects.filter(status=STATUS_ACTIVE).order_by("title")

    def clean(self):
        cleaned_data = super().clean()
        organization = cleaned_data.get("organization")
        branch = cleaned_data.get("branch")
        user = cleaned_data.get("user")
        is_primary = cleaned_data.get("is_primary")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if branch and organization and branch.organization_id != organization.pk:
            self.add_error("branch", "Branch must belong to the selected organization.")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date cannot be before start date.")
        if user and is_primary:
            qs = UserAssignment.objects.filter(user=user, is_primary=True, deleted_at__isnull=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("is_primary", "This user already has a primary assignment.")
        return cleaned_data
