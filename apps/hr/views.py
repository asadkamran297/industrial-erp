from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.constants import RECORD_STATUS_CHOICES
from apps.core.mixins import PortalPermissionRequiredMixin, SearchFilterPaginationMixin
from apps.organizations.models import Organization

from .forms import EmployeeForm
from .models import Employee


class EmployeeListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "employees.view"
    template_name = "hr/employee_list.html"
    context_object_name = "employees"
    queryset = Employee.objects.select_related("organization", "branch", "department", "designation").order_by("full_name")
    search_fields = ("full_name", "cnic", "email", "contact", "department__title", "designation__title")
    filter_fields = {"status": "status", "organization": "organization_id"}

    def get_filter_specs(self):
        return [
            {"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")},
            {"name": "organization", "label": "All organizations", "choices": [(str(o.pk), o.title) for o in Organization.objects.order_by("title")], "value": self.request.GET.get("organization", "")},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Employees", "")]
        return context


class EmployeeCreateView(PortalPermissionRequiredMixin, CreateView):
    permission_required = "employees.manage"
    model = Employee
    form_class = EmployeeForm
    template_name = "hr/employee_form.html"
    success_url = reverse_lazy("hr:employee_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Employee saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Employee"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Employees", self.success_url), ("New", "")]
        return context


class EmployeeUpdateView(EmployeeCreateView, UpdateView):
    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Employee updated.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Employee"
        return context


class EmployeeDeleteView(PortalPermissionRequiredMixin, View):
    permission_required = "employees.manage"

    def post(self, request, pk):
        Employee.objects.get(pk=pk).soft_delete(request.user)
        messages.success(request, "Employee deleted.")
        return redirect("hr:employee_list")
