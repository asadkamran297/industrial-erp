from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.constants import RECORD_STATUS_CHOICES
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, SearchFilterPaginationMixin
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


class SoftDeleteView(PagePermissionRequiredMixin, View):
    model = None
    success_url = None
    success_message = "Record deleted."
    permission_required = None

    def post(self, request, pk):
        record = self.model.objects.get(pk=pk)
        record.soft_delete(request.user)
        messages.success(request, self.success_message)
        return redirect(self.success_url)


class OrganizationListView(SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "organizations.organizations"
    template_name = "organizations/organization_list.html"
    context_object_name = "organizations"
    search_fields = ("title", "code", "parent__title")
    filter_fields = {"status": "status"}

    def get_queryset(self):
        return get_organizations()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Organizations", "")]
        return context

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class OrganizationCreateView(AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
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


class OrganizationDeleteView(SoftDeleteView):
    model = Organization
    success_url = reverse_lazy("organizations:organization_list")
    success_message = "Organization deleted."
    page = "organizations.organizations"
    action = "delete"


class BranchListView(SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "organizations.branches"
    template_name = "organizations/branch_list.html"
    context_object_name = "branches"
    search_fields = ("title", "code", "phone", "email", "organization__title", "city__title")
    filter_fields = {"status": "status", "organization": "organization_id"}

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


class BranchCreateView(AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
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


class BranchDeleteView(SoftDeleteView):
    model = Branch
    success_url = reverse_lazy("organizations:branch_list")
    success_message = "Branch deleted."
    page = "organizations.branches"
    action = "delete"
