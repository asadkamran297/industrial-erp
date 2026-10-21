from decimal import Decimal

from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import DetailView, View

from apps.core.constants import STATUS_ACTIVE, STATUS_INACTIVE
from apps.core.formatting import format_amount
from apps.core.mixins import PagePermissionRequiredMixin


class ToggleStatusView(PagePermissionRequiredMixin, View):
    """Flip a master record between active and inactive. Masters are never deleted (rule 23)."""

    model = None
    action = "edit"
    success_url_name = ""

    def post(self, request, pk):
        record = get_object_or_404(self.model, pk=pk)
        record.status = STATUS_INACTIVE if record.status == STATUS_ACTIVE else STATUS_ACTIVE
        if hasattr(record, "updated_by"):
            record.updated_by = request.user
            record.save(update_fields=["status", "updated_by", "updated_at"])
        else:
            record.save(update_fields=["status"])
        return redirect(request.META.get("HTTP_REFERER") or reverse(self.success_url_name))


def display_value(obj, attr):
    """Resolve a dotted attribute for a detail grid: choices via get_*_display, callables called."""
    value = obj
    parts = attr.split(".")
    for index, part in enumerate(parts):
        if value is None:
            return None
        if index == len(parts) - 1 and hasattr(value, f"get_{part}_display"):
            return getattr(value, f"get_{part}_display")()
        value = getattr(value, part, None)
        if callable(value):
            value = value()
    return value


class MasterDetailView(PagePermissionRequiredMixin, DetailView):
    """One master record on the DETAIL contract: header, status pill, grid of ``detail_fields``.

    ``detail_fields`` is a tuple of ``(label, attr)`` or ``(label, attr, kind)`` where kind is
    ``money`` (2 dp, right-aligned), ``weight`` (3 dp) or ``wide``.
    """

    template_name = "core/master_detail.html"
    kind = ""
    title_attr = "title"
    subtitle_attr = ""
    detail_fields = ()
    # (label, attr, flavour, tone): shown as key figures above the grid; header and figure attrs are not repeated in it.
    figure_fields = ()
    list_url_name = ""
    edit_url_name = ""
    create_url_name = ""

    def _formatted(self, attr, flavour):
        value = display_value(self.object, attr)
        if flavour == "money" and value is not None:
            return format_amount(value)
        if flavour == "weight" and value is not None:
            return f"{Decimal(value):.3f}"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        return value

    def get_figures(self):
        return [
            {"label": spec[0], "value": self._formatted(spec[1], spec[2] if len(spec) > 2 else ""),
             "tone": spec[3] if len(spec) > 3 else "slate"}
            for spec in self.figure_fields
        ]

    def get_detail_items(self):
        shown_above = {spec[1] for spec in self.figure_fields} | {self.title_attr, self.subtitle_attr, "status"}
        items = []
        for spec in self.detail_fields:
            label, attr = spec[0], spec[1]
            if attr in shown_above:
                continue
            flavour = spec[2] if len(spec) > 2 else ""
            items.append({"label": label, "value": self._formatted(attr, flavour),
                          "num": flavour in ("money", "weight"), "wide": flavour == "wide"})
        return items

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.object
        context["kind"] = self.kind or obj._meta.verbose_name.title()
        context["title"] = display_value(obj, self.title_attr)
        context["subtitle"] = display_value(obj, self.subtitle_attr) if self.subtitle_attr else ""
        status = getattr(obj, "status", "")
        context["status_label"] = obj.get_status_display() if status and hasattr(obj, "get_status_display") else status
        context["status_tone"] = "posted" if status == STATUS_ACTIVE else "closed"
        context["detail_items"] = self.get_detail_items()
        context["figures"] = self.get_figures()
        context["list_url"] = reverse(self.list_url_name) if self.list_url_name else ""
        context["edit_url"] = reverse(self.edit_url_name, args=[obj.pk]) if self.edit_url_name and context.get("can_edit") else ""
        context["doc_actions"] = {"new_url": self.create_url(context), "edit_url": context["edit_url"]}
        context.setdefault("doc_links", [])
        return context

    def create_url(self, context):
        if not context.get("can_add"):
            return ""
        return reverse(self.create_url_name) if self.create_url_name else ""


class SaveAndNewMixin:
    """Save & New on a create screen reopens the same blank form; on an edit screen it behaves like Save."""

    def get_success_url(self):
        from django.views.generic import UpdateView

        if "save_and_new" in self.request.POST and not isinstance(self, UpdateView):
            return self.request.get_full_path()
        return super().get_success_url()
