from django import forms
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from apps.core import features, numbering
from apps.core.mixins import PagePermissionRequiredMixin
from apps.core.models import SystemSetting

TAB_FEATURES = "features"
TAB_NUMBERING = "numbering"
TAB_COMPANY = "company"
TAB_WHEAT = "wheat"
TABS = ((TAB_FEATURES, "Features"), (TAB_NUMBERING, "Numbering"), (TAB_COMPANY, "Company"), (TAB_WHEAT, "Wheat"))


class CompanyForm(forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = ["company_name", "company_tagline", "company_logo", "support_phone", "support_email", "footer_text"]


class WheatForm(forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = ["wheat_withholding_rate_per_40kg", "wheat_brokerage_rate_per_100kg"]
        labels = {
            "wheat_withholding_rate_per_40kg": "Withholding / 40 kg",
            "wheat_brokerage_rate_per_100kg": "Brokerage / 100 kg",
        }


class GeneralSettingsView(PagePermissionRequiredMixin, TemplateView):
    page = "settings"
    template_name = "portal/general_settings.html"

    def tab(self):
        value = self.request.POST.get("tab") or self.request.GET.get("tab") or TAB_FEATURES
        return value if value in dict(TABS) else TAB_FEATURES

    def setting(self):
        setting = SystemSetting.get_solo()
        if not setting.pk:
            setting.save()
        return setting

    def series_rows(self, errors=None, posted=None):
        rows = []
        for row in numbering.all_series():
            last = numbering.last_used(row.code)
            values = (posted or {}).get(row.code) or {"prefix": row.prefix, "start_number": row.start_number, "padding": row.padding}
            rows.append({
                "series": row, "values": values, "last": last,
                "next": numbering.preview(row.code, last), "error": (errors or {}).get(row.code, ""),
            })
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        setting = self.setting()
        tab = self.tab()
        base = reverse("portal:general_settings")
        context.update({
            "title": "General Settings",
            "tab": tab,
            "tabs": [{"href": f"{base}?tab={key}", "label": label, "on": key == tab} for key, label in TABS],
            "feature_groups": features.grouped(),
            "company_form": kwargs.get("company_form") or CompanyForm(instance=setting),
            "wheat_form": kwargs.get("wheat_form") or WheatForm(instance=setting),
            "series_rows": kwargs.get("series_rows") or (self.series_rows() if tab == TAB_NUMBERING else []),
        })
        return context

    def post(self, request, *args, **kwargs):
        tab = self.tab()
        back = f"{reverse('portal:general_settings')}?tab={tab}"
        setting = self.setting()
        if tab == TAB_FEATURES:
            features.save(set(request.POST.getlist("features")))
            messages.success(request, "Features saved.")
            return redirect(back)
        if tab == TAB_COMPANY:
            form = CompanyForm(request.POST, request.FILES, instance=setting)
            if form.is_valid():
                form.save()
                messages.success(request, "Company details saved.")
                return redirect(back)
            return self.render_to_response(self.get_context_data(company_form=form))
        if tab == TAB_WHEAT:
            form = WheatForm(request.POST, instance=setting)
            if form.is_valid():
                form.save()
                messages.success(request, "Wheat rates saved.")
                return redirect(back)
            return self.render_to_response(self.get_context_data(wheat_form=form))
        return self._save_numbering(request, back)

    def _save_numbering(self, request, back):
        errors, posted, updates = {}, {}, []
        for row in numbering.all_series():
            prefix = (request.POST.get(f"{row.code}-prefix") or "").strip().upper()
            start = (request.POST.get(f"{row.code}-start_number") or "").strip()
            padding = (request.POST.get(f"{row.code}-padding") or "").strip()
            posted[row.code] = {"prefix": prefix, "start_number": start, "padding": padding}
            try:
                start_number, pad = int(start), int(padding)
            except ValueError:
                errors[row.code] = "Whole numbers only."
                continue
            if not prefix or len(prefix) > 12 or not prefix.replace("-", "").isalnum():
                errors[row.code] = "Prefix: letters and digits, up to 12."
            elif start_number < 0 or not 0 <= pad <= 10:
                errors[row.code] = "Start 0 or more; padding 0 to 10."
            elif start_number != row.start_number and prefix == row.prefix:
                last = numbering.last_used(row.code)
                if last is not None and start_number <= last:
                    errors[row.code] = f"Already used up to {last}."
            if row.code not in errors:
                updates.append((row, prefix, start_number, pad))
        if errors:
            messages.error(request, "Some series were not saved.")
            return self.render_to_response(self.get_context_data(series_rows=self.series_rows(errors, posted)))
        for row, prefix, start_number, pad in updates:
            row.prefix, row.start_number, row.padding = prefix, start_number, pad
            row.updated_by = request.user
            row.save(update_fields=["prefix", "start_number", "padding", "updated_by", "updated_at"])
        messages.success(request, "Numbering saved.")
        return redirect(back)
