from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.constants import RECORD_STATUS_CHOICES
from apps.core.mixins import PortalPermissionRequiredMixin, SearchFilterPaginationMixin

from .forms import build_master_form
from .registry import MASTER_CONFIGS, MASTER_CONFIG_MAP


class MasterConfigMixin:
    def dispatch(self, request, *args, **kwargs):
        self.master_config = get_object_or_404_config(kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

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


class MasterListView(MasterConfigMixin, SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "configurations.view"
    template_name = "configurations/master_list.html"
    context_object_name = "records"
    search_fields = ("title", "code")
    filter_fields = {"status": "status"}

    def get_queryset(self):
        self.model = self.master_config.model
        return super().get_queryset().order_by("title")

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class MasterCreateView(MasterConfigMixin, PortalPermissionRequiredMixin, CreateView):
    permission_required = "configurations.manage"
    template_name = "configurations/master_form.html"

    def get_form_class(self):
        return build_master_form(self.master_config.model, self.master_config.extra_fields)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, f"{self.master_config.label} record saved.")
        return super().form_valid(form)


class MasterUpdateView(MasterCreateView, UpdateView):
    def get_queryset(self):
        return self.master_config.model.objects.all()

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, f"{self.master_config.label} record updated.")
        return super().form_valid(form)


class MasterDeleteView(MasterConfigMixin, PortalPermissionRequiredMixin, View):
    permission_required = "configurations.manage"

    def post(self, request, slug, pk):
        record = get_object_or_404(self.master_config.model, pk=pk)
        record.soft_delete(request.user)
        messages.success(request, f"{self.master_config.label} record deleted.")
        return redirect(self.get_success_url())
