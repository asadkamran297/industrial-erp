from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelform_factory

from apps.core.forms import AutoSelectSingleChoiceMixin


def build_master_form(model, extra_fields=()):
    fields = ("title", "code", *extra_fields, "status")
    widgets = {
        "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "Title"}),
        "code": forms.TextInput(attrs={"class": "form-input", "placeholder": "Code"}),
        "status": forms.Select(attrs={"class": "form-select"}),
    }
    for field in extra_fields:
        widgets[field] = forms.Select(attrs={"class": "form-select"})

    class MasterFormBase(AutoSelectSingleChoiceMixin, forms.ModelForm):

        def clean_title(self):
            title = self.cleaned_data["title"].strip()
            qs = self._meta.model.all_objects.filter(title__iexact=title, deleted_at__isnull=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Title already exists.")
            return title

        def clean_code(self):
            code = self.cleaned_data.get("code", "").strip().upper()
            if code:
                qs = self._meta.model.all_objects.filter(code__iexact=code, deleted_at__isnull=True)
                if self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise ValidationError("Code already exists.")
            return code

    return modelform_factory(model, form=MasterFormBase, fields=fields, widgets=widgets)
