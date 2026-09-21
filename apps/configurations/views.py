from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.core.constants import RECORD_STATUS_CHOICES
from apps.core.constants import STATUS_ACTIVE, STATUS_INACTIVE
from apps.core.mixins import PagePermissionRequiredMixin, SearchFilterPaginationMixin, SortableListMixin
from apps.core.views import SaveAndNewMixin, display_value

from .forms import build_master_form
from .registry import MASTER_CONFIGS, MASTER_CONFIG_MAP


class MasterConfigMixin:
    def dispatch(self, request, *args, **kwargs):
        self.master_config = get_object_or_404_config(kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_page_key(self):
        return f"configurations.{get_object_or_404_config(self.kwargs['slug']).slug.replace('-', '_')}"

    def get_permission_required(self):
        return f"{self.get_page_key()}.{self.action or self._infer_action()}"

    def get_success_url(self):
        return reverse("configurations:master_list", kwargs={"slug": self.master_config.slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["master_config"] = self.master_config
        context["master_configs"] = MASTER_CONFIGS
        context["breadcrumbs"] = [("Dashboard", reverse("portal:dashboard")), ("Masters", ""), (self.master_config.label, "")]
        return context


def get_object_or_404_config(slug):
    config = MASTER_CONFIG_MAP.get(slug)
    if config is None:
        from django.http import Http404

        raise Http404("Master not found")
    return config


class MasterListView(MasterConfigMixin, SortableListMixin, SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    action = "index"
    template_name = "configurations/master_list.html"
    context_object_name = "records"
    search_fields = ("title", "code")
    filter_fields = {"status": "status"}
    sort_fields = {"title": "title", "code": "code", "status": ("status", "title")}
    default_sort = "title"

    def get_queryset(self):
        self.model = self.master_config.model
        return super().get_queryset().order_by("title")

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class MasterCreateView(SaveAndNewMixin, MasterConfigMixin, PagePermissionRequiredMixin, CreateView):
    action = "add"
    template_name = "configurations/master_form.html"

    def get_form_class(self):
        return build_master_form(self.master_config.model, self.master_config.extra_fields)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, f"{self.master_config.label} record saved.")
        return super().form_valid(form)


class MasterUpdateView(MasterCreateView, UpdateView):
    action = "edit"

    def get_queryset(self):
        return self.master_config.model.objects.all()

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, f"{self.master_config.label} record updated.")
        return super().form_valid(form)


class MasterToggleStatusView(MasterConfigMixin, PagePermissionRequiredMixin, View):
    action = "edit"

    def post(self, request, slug, pk):
        record = get_object_or_404(self.master_config.model, pk=pk)
        record.status = STATUS_INACTIVE if record.status == STATUS_ACTIVE else STATUS_ACTIVE
        record.updated_by = request.user
        record.save(update_fields=["status", "updated_by", "updated_at"])
        return redirect(request.META.get("HTTP_REFERER") or self.get_success_url())


class MasterDetailView(MasterConfigMixin, PagePermissionRequiredMixin, DetailView):
    action = "view"
    template_name = "core/master_detail.html"
    context_object_name = "record"

    def get_queryset(self):
        return self.master_config.model.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        record = self.object
        config = self.master_config
        items = [{"label": "Title", "value": record.title}, {"label": "Code", "value": record.code}]
        for name in config.extra_fields:
            field = record._meta.get_field(name)
            items.append({"label": field.verbose_name.title(), "value": display_value(record, name)})
        items.append({"label": "Status", "value": record.get_status_display()})
        context.update({
            "kind": config.singular,
            "title": record.title,
            "subtitle": record.code,
            "status_label": record.get_status_display(),
            "status_tone": "posted" if record.status == STATUS_ACTIVE else "closed",
            "detail_items": items,
            "list_url": self.get_success_url(),
            "edit_url": reverse("configurations:master_update", kwargs={"slug": config.slug, "pk": record.pk}) if context.get("can_edit") else "",
        })
        return context
