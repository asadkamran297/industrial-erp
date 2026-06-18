from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import BranchForm, OrganizationForm
from .models import Branch, Organization
from .selectors import get_branches, get_organizations


class OrganizationListView(LoginRequiredMixin, ListView):
    template_name = "organizations/organization_list.html"
    context_object_name = "organizations"

    def get_queryset(self):
        return get_organizations()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Organizations", "")]
        return context


class OrganizationCreateView(LoginRequiredMixin, CreateView):
    model = Organization
    form_class = OrganizationForm
    template_name = "organizations/organization_form.html"
    success_url = reverse_lazy("organizations:organization_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Organization"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Organizations", self.success_url), ("New", "")]
        return context


class OrganizationUpdateView(LoginRequiredMixin, UpdateView):
    model = Organization
    form_class = OrganizationForm
    template_name = "organizations/organization_form.html"
    success_url = reverse_lazy("organizations:organization_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Organization"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Organizations", self.success_url), ("Edit", "")]
        return context


class BranchListView(LoginRequiredMixin, ListView):
    template_name = "organizations/branch_list.html"
    context_object_name = "branches"

    def get_queryset(self):
        return get_branches()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Branches", "")]
        return context


class BranchCreateView(LoginRequiredMixin, CreateView):
    model = Branch
    form_class = BranchForm
    template_name = "organizations/branch_form.html"
    success_url = reverse_lazy("organizations:branch_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Branch"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Branches", self.success_url), ("New", "")]
        return context


class BranchUpdateView(LoginRequiredMixin, UpdateView):
    model = Branch
    form_class = BranchForm
    template_name = "organizations/branch_form.html"
    success_url = reverse_lazy("organizations:branch_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Branch"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Branches", self.success_url), ("Edit", "")]
        return context
