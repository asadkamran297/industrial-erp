from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.constants import ALLOWANCE_DEDUCTION_TYPE_CHOICES, WORKFLOW_STATUS_CHOICES
from apps.core.mixins import PortalPermissionRequiredMixin, SearchFilterPaginationMixin

from .forms import EmployeeSalaryForm, PayrollForm
from .models import EmployeeSalary, Payroll
from apps.hr.models import Employee


class EmployeeSalaryListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "payroll.view"
    template_name = "payroll/employee_salary_list.html"
    context_object_name = "salary_items"
    queryset = EmployeeSalary.objects.select_related("employee", "allowance_deduction").order_by("employee__full_name")
    search_fields = ("employee__full_name", "allowance_deduction__title")
    filter_fields = {"type": "allowance_deduction_type"}

    def get_filter_specs(self):
        return [{"name": "type", "label": "All types", "choices": ALLOWANCE_DEDUCTION_TYPE_CHOICES, "value": self.request.GET.get("type", "")}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Salary Items", "")]
        return context


class EmployeeSalaryCreateView(PortalPermissionRequiredMixin, CreateView):
    permission_required = "payroll.generate"
    model = EmployeeSalary
    form_class = EmployeeSalaryForm
    template_name = "payroll/employee_salary_form.html"
    success_url = reverse_lazy("payroll:employee_salary_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Salary item saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Salary Item"
        context["employee_salary_map"] = {str(employee.pk): float(employee.salary) for employee in Employee.objects.filter(status="active")}
        context["element_type_map"] = {
            str(item.pk): item.get_type_display() for item in context["form"].fields["allowance_deduction"].queryset
        }
        return context


class EmployeeSalaryUpdateView(EmployeeSalaryCreateView, UpdateView):
    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Salary item updated.")
        return super().form_valid(form)


class EmployeeSalaryDeleteView(PortalPermissionRequiredMixin, View):
    permission_required = "payroll.generate"

    def post(self, request, pk):
        EmployeeSalary.objects.get(pk=pk).soft_delete(request.user)
        messages.success(request, "Salary item deleted.")
        return redirect("payroll:employee_salary_list")


class PayrollListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "payroll.view"
    template_name = "payroll/payroll_list.html"
    context_object_name = "payrolls"
    queryset = Payroll.objects.select_related("employee").order_by("-year", "-month", "employee__full_name")
    search_fields = ("employee__full_name", "employee__cnic")
    filter_fields = {"status": "status", "month": "month", "year": "year"}

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": WORKFLOW_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Payrolls", "")]
        return context


class PayrollCreateView(PortalPermissionRequiredMixin, CreateView):
    permission_required = "payroll.generate"
    model = Payroll
    form_class = PayrollForm
    template_name = "payroll/payroll_form.html"
    success_url = reverse_lazy("payroll:payroll_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        form.instance.generated_by = self.request.user
        messages.success(self.request, "Payroll saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Payroll"
        return context


class PayrollUpdateView(PayrollCreateView, UpdateView):
    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Payroll updated.")
        return super().form_valid(form)


class PayrollDeleteView(PortalPermissionRequiredMixin, View):
    permission_required = "payroll.generate"

    def post(self, request, pk):
        Payroll.objects.get(pk=pk).soft_delete(request.user)
        messages.success(request, "Payroll deleted.")
        return redirect("payroll:payroll_list")
