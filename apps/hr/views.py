from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.core.constants import RECORD_STATUS_CHOICES
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, SearchFilterPaginationMixin
from apps.organizations.models import Organization
from apps.payroll.forms import EmployeeSalaryInlineForm
from apps.payroll.models import EmployeeSalary, Payroll

from .forms import EmployeeExperienceForm, EmployeeForm, EmployeeQualificationForm
from .models import Employee, EmployeeExperience, EmployeeQualification


class EmployeeListView(SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "hr.employees"
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


class EmployeeDetailView(PagePermissionRequiredMixin, DetailView):
    page = "hr.employees"
    model = Employee
    template_name = "hr/employee_detail.html"
    context_object_name = "employee"

    def get_queryset(self):
        return Employee.objects.select_related(
            "organization",
            "branch",
            "department",
            "designation",
            "salutation",
            "gender",
            "blood_group",
            "job_type",
            "religion",
            "marital_status",
        ).prefetch_related("experiences", "qualifications")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "breadcrumbs": [("Dashboard", reverse_lazy("portal:dashboard")), ("Employees", reverse_lazy("hr:employee_list")), (self.object.full_name, "")],
                "experience_form": EmployeeExperienceForm(),
                "qualification_form": EmployeeQualificationForm(),
                "salary_items": EmployeeSalary.objects.select_related("allowance_deduction").filter(employee=self.object),
                "salary_item_form": EmployeeSalaryInlineForm(employee=self.object),
                "payrolls": Payroll.objects.filter(employee=self.object).order_by("-year", "-month"),
            }
        )
        return context


class EmployeeCreateView(PagePermissionRequiredMixin, CreateView):
    page = "hr.employees"
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


class EmployeeDeleteView(PagePermissionRequiredMixin, View):
    page = "hr.employees"
    action = "delete"

    def post(self, request, pk):
        Employee.objects.get(pk=pk).soft_delete(request.user)
        messages.success(request, "Employee deleted.")
        return redirect("hr:employee_list")


class EmployeeExperienceCreateView(PagePermissionRequiredMixin, View):
    page = "hr.employees"
    action = "edit"

    def post(self, request, employee_pk):
        employee = get_object_or_404(Employee, pk=employee_pk)
        form = EmployeeExperienceForm(request.POST)
        if form.is_valid():
            experience = form.save(commit=False)
            experience.employee = employee
            experience.created_by = request.user
            experience.updated_by = request.user
            experience.save()
            messages.success(request, "Experience saved.")
        else:
            messages.error(request, "Experience could not be saved. Please check the form.")
        return redirect("hr:employee_detail", pk=employee.pk)


class EmployeeExperienceDeleteView(PagePermissionRequiredMixin, View):
    page = "hr.employees"
    action = "edit"

    def post(self, request, employee_pk, pk):
        experience = get_object_or_404(EmployeeExperience, pk=pk, employee_id=employee_pk)
        experience.soft_delete(request.user)
        messages.success(request, "Experience deleted.")
        return redirect("hr:employee_detail", pk=employee_pk)


class EmployeeQualificationCreateView(PagePermissionRequiredMixin, View):
    page = "hr.employees"
    action = "edit"

    def post(self, request, employee_pk):
        employee = get_object_or_404(Employee, pk=employee_pk)
        form = EmployeeQualificationForm(request.POST)
        if form.is_valid():
            qualification = form.save(commit=False)
            qualification.employee = employee
            qualification.created_by = request.user
            qualification.updated_by = request.user
            qualification.save()
            messages.success(request, "Qualification saved.")
        else:
            messages.error(request, "Qualification could not be saved. Please check the form.")
        return redirect("hr:employee_detail", pk=employee.pk)


class EmployeeQualificationDeleteView(PagePermissionRequiredMixin, View):
    page = "hr.employees"
    action = "edit"

    def post(self, request, employee_pk, pk):
        qualification = get_object_or_404(EmployeeQualification, pk=pk, employee_id=employee_pk)
        qualification.soft_delete(request.user)
        messages.success(request, "Qualification deleted.")
        return redirect("hr:employee_detail", pk=employee_pk)


def employee_payroll_redirect(employee_pk: int):
    return HttpResponseRedirect(f"{reverse('hr:employee_detail', kwargs={'pk': employee_pk})}#payroll")


class EmployeeSalaryItemCreateView(PagePermissionRequiredMixin, View):
    page = "hr.employees"
    action = "edit"

    def post(self, request, employee_pk):
        employee = get_object_or_404(Employee, pk=employee_pk)
        form = EmployeeSalaryInlineForm(request.POST, employee=employee)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.updated_by = request.user
            item.save()
            messages.success(request, "Salary element saved.")
        else:
            messages.error(request, "Salary element could not be saved. Please check duplicate element or amount.")
        return employee_payroll_redirect(employee.pk)


class EmployeeSalaryItemUpdateView(PagePermissionRequiredMixin, View):
    page = "hr.employees"
    action = "edit"

    def post(self, request, employee_pk, pk):
        employee = get_object_or_404(Employee, pk=employee_pk)
        salary_item = get_object_or_404(EmployeeSalary, pk=pk, employee=employee)
        form = EmployeeSalaryInlineForm(request.POST, employee=employee, instance=salary_item)
        if form.is_valid():
            item = form.save(commit=False)
            item.updated_by = request.user
            item.save()
            messages.success(request, "Salary element updated.")
        else:
            messages.error(request, "Salary element could not be updated. Please check duplicate element or amount.")
        return employee_payroll_redirect(employee.pk)


class EmployeeSalaryItemDeleteView(PagePermissionRequiredMixin, View):
    page = "hr.employees"
    action = "edit"

    def post(self, request, employee_pk, pk):
        employee = get_object_or_404(Employee, pk=employee_pk)
        salary_item = get_object_or_404(EmployeeSalary, pk=pk, employee=employee)
        salary_item.soft_delete(request.user)
        messages.success(request, "Salary element deleted.")
        return employee_payroll_redirect(employee.pk)
