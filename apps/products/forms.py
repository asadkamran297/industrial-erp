from django import forms

from apps.core.constants import (
    PRD_LEVEL_ITEM,
    PRD_SEGMENT_WIDTHS,
    PRD_SPECIFICATION_CHOICES,
    PRD_STATUS_CHOICES,
    PRD_UNIT_CHOICES,
    STATUS_ACTIVE,
)
from apps.finance.models import ChartOfAccount

from . import selectors
from .models import ProductNode


class StyledModelForm(forms.ModelForm):
    """Same widget classes the rest of the portal uses."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.CheckboxInput):
                continue
            else:
                field.widget.attrs.setdefault("class", "form-input")


class SubGroupChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.complete_code}  {obj.name}"


class AccountChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.code}  {obj.title}" if obj.code else obj.title


class ProductForm(StyledModelForm):
    """Add / edit an item. Groups and sub-groups are seeded, not typed here.

    The code is not entered: it is the parent's code plus the next free segment,
    so two clerks adding a product at the same moment cannot invent the same
    code between them.
    """

    parent = SubGroupChoiceField(queryset=ProductNode.objects.none(), label="Sub group")

    class Meta:
        model = ProductNode
        fields = (
            "parent",
            "starting_date",
            "name",
            "specification",
            "status",
            "quick_code",
            "unit",
            "unit_weight",
            "fix_weight",
            "actual_weight",
            "color",
        )
        widgets = {
            "starting_date": forms.DateInput(attrs={"type": "date"}),
            "specification": forms.Select(choices=(("", "Select specification"), *PRD_SPECIFICATION_CHOICES)),
            "status": forms.Select(choices=PRD_STATUS_CHOICES),
            "unit": forms.Select(choices=(("", "Select unit"), *PRD_UNIT_CHOICES)),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = selectors.sub_groups()
        self.fields["quick_code"].required = False
        self.fields["color"].required = False
        self.fields["unit"].required = True
        self.fields["specification"].required = True
        if not self.instance.pk:
            self.fields["status"].initial = STATUS_ACTIVE

    def clean_quick_code(self):
        value = (self.cleaned_data.get("quick_code") or "").strip().upper()
        if not value:
            return ""
        clash = ProductNode.objects.filter(quick_code=value).exclude(pk=self.instance.pk).exists()
        if clash:
            raise forms.ValidationError("Another product already answers to this quick code.")
        return value

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get("parent")
        self.instance.level = PRD_LEVEL_ITEM
        if parent and not self.instance.pk:
            self.instance.code_segment = selectors.next_code_segment(parent, PRD_LEVEL_ITEM)
        return cleaned

    @property
    def preview_code(self) -> str:
        """What the code will be, shown live while the form is being filled."""
        if self.instance.pk:
            return self.instance.display_code
        parent = self.data.get("parent") or self.initial.get("parent")
        if not parent:
            return "--"
        node = ProductNode.objects.filter(pk=parent).first()
        if node is None:
            return "--"
        segment = selectors.next_code_segment(node, PRD_LEVEL_ITEM)
        return f"{node.complete_code}-{segment}".ljust(PRD_SEGMENT_WIDTHS[PRD_LEVEL_ITEM])


class AccountLinkForm(forms.Form):
    """One row of the account-linking grid."""

    product_id = forms.IntegerField(widget=forms.HiddenInput)
    purchase_account = AccountChoiceField(
        queryset=ChartOfAccount.objects.filter(is_group=False, status=STATUS_ACTIVE).order_by("code"),
        required=False,
        empty_label="Not linked",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
