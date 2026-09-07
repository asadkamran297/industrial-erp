from django import forms

from .models import Godown


class GodownForm(forms.ModelForm):
    class Meta:
        model = Godown
        fields = ["code", "name", "godown_type", "location", "incharge", "status", "remarks"]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "MG"}),
            "name": forms.TextInput(attrs={"placeholder": "Main Godown"}),
            "remarks": forms.TextInput(),
        }

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()
