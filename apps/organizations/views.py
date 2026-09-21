from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.db.models import Count
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.constants import RECORD_STATUS_CHOICES
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, SearchFilterPaginationMixin, SortableListMixin
from apps.core.views import SaveAndNewMixin, MasterDetailView, ToggleStatusView
from .forms import BranchForm, OrganizationForm
from .models import Branch, Organization
from .selectors import get_branches, get_organizations


class AuditSaveMixin:
    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


class OrganizationListView(SortableListMixin, SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "organizations.organizations"
    model = Organization
    template_name = "organizations/organization_list.html"
    context_object_name = "organizations"
    search_fields = ("title", "code", "parent__title")
    filter_fields = {"status": "status"}
    sort_fields = {"title": "title", "code": "code", "parent": "parent__title", "subs": "sub_count", "status": ("status", "title")}
    default_sort = "title"

    def get_queryset(self):
        return get_organizations().annotate(sub_count=Count("children"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Organizations", "")]
        return context

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class OrganizationCreateView(SaveAndNewMixin, AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
    page = "organizations.organizations"
    model = Organization
    form_class = OrganizationForm
    template_name = "organizations/organization_form.html"
    success_url = reverse_lazy("organizations:organization_list")
    success_message = "Organization saved."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Organization"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Organizations", self.success_url), ("New", "")]
        return context


class OrganizationUpdateView(AuditSaveMixin, PagePermissionRequiredMixin, UpdateView):
    page = "organizations.organizations"
    model = Organization
    form_class = OrganizationForm
    template_name = "organizations/organization_form.html"
    success_url = reverse_lazy("organizations:organization_list")
    success_message = "Organization updated."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Organization"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Organizations", self.success_url), ("Edit", "")]
        return context


class BranchListView(SortableListMixin, SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "organizations.branches"
    model = Branch
    template_name = "organizations/branch_list.html"
    context_object_name = "branches"
    search_fields = ("title", "code", "phone", "email", "organization__title", "city__title")
    filter_fields = {"status": "status", "organization": "organization_id"}
    sort_fields = {"title": "title", "code": "code", "organization": ("organization__title", "title"), "city": "city__title", "status": ("status", "title")}
    default_sort = "title"

    def get_queryset(self):
        return get_branches()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Branches", "")]
        return context

    def get_filter_specs(self):
        return [
            {"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")},
            {
                "name": "organization",
                "label": "All organizations",
                "choices": [(str(org.pk), org.title) for org in Organization.objects.order_by("title")],
                "value": self.request.GET.get("organization", ""),
            },
        ]


class BranchCreateView(SaveAndNewMixin, AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
    page = "organizations.branches"
    model = Branch
    form_class = BranchForm
    template_name = "organizations/branch_form.html"
    success_url = reverse_lazy("organizations:branch_list")
    success_message = "Branch saved."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Branch"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Branches", self.success_url), ("New", "")]
        return context


class BranchUpdateView(AuditSaveMixin, PagePermissionRequiredMixin, UpdateView):
    page = "organizations.branches"
    model = Branch
    form_class = BranchForm
    template_name = "organizations/branch_form.html"
    success_url = reverse_lazy("organizations:branch_list")
    success_message = "Branch updated."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Branch"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Branches", self.success_url), ("Edit", "")]
        return context


class OrganizationToggleStatusView(ToggleStatusView):
    page = "organizations.organizations"
    model = Organization
    success_url_name = "organizations:organization_list"


class OrganizationDetailView(MasterDetailView):
    page = "organizations.organizations"
    model = Organization
    kind = "Organization"
    subtitle_attr = "code"
    list_url_name = "organizations:organization_list"
    edit_url_name = "organizations:organization_update"
    detail_fields = (
        ("Parent", "parent"), ("Phone", "phone"), ("Cell", "cell"), ("Fax", "fax"),
        ("Email", "email"), ("Website", "website"), ("Address", "address", "wide"), ("Status", "status"),
    )


class BranchToggleStatusView(ToggleStatusView):
    page = "organizations.branches"
    model = Branch
    success_url_name = "organizations:branch_list"


class BranchDetailView(MasterDetailView):
    page = "organizations.branches"
    model = Branch
    kind = "Branch"
    subtitle_attr = "code"
    list_url_name = "organizations:branch_list"
    edit_url_name = "organizations:branch_update"
    detail_fields = (
        ("Organization", "organization"), ("Parent Branch", "parent"), ("City", "city"), ("Phone", "phone"),
        ("Email", "email"), ("Fax", "fax"), ("Address", "address", "wide"), ("Status", "status"),
    )
