from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.constants import RECORD_STATUS_CHOICES
from apps.core.mixins import PortalPermissionRequiredMixin, SearchFilterPaginationMixin
from apps.organizations.models import Organization

from .forms import PermissionForm, RoleForm, UserAssignmentForm
from .models import Permission, Role, UserAssignment


class AuditSaveMixin:
    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


class SoftDeleteView(PortalPermissionRequiredMixin, View):
    model = None
    success_url = None
    success_message = "Record deleted."

    def post(self, request, pk):
        record = self.model.objects.get(pk=pk)
        record.soft_delete(request.user)
        messages.success(request, self.success_message)
        return redirect(self.success_url)


class RoleListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "access_control.view"
    model = Role
    template_name = "access_control/role_list.html"
    context_object_name = "roles"
    queryset = Role.objects.prefetch_related("permission_links__permission").order_by("title")
    search_fields = ("title",)
    filter_fields = {"status": "status"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Roles", "")]
        return context

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class RoleCreateView(AuditSaveMixin, PortalPermissionRequiredMixin, CreateView):
    permission_required = "access_control.manage"
    model = Role
    form_class = RoleForm
    template_name = "access_control/role_form.html"
    success_url = reverse_lazy("access_control:role_list")
    success_message = "Role saved."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Role"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Roles", self.success_url), ("New", "")]
        return context


class RoleUpdateView(AuditSaveMixin, PortalPermissionRequiredMixin, UpdateView):
    permission_required = "access_control.manage"
    model = Role
    form_class = RoleForm
    template_name = "access_control/role_form.html"
    success_url = reverse_lazy("access_control:role_list")
    success_message = "Role updated."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Role"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Roles", self.success_url), ("Edit", "")]
        return context


class RoleDeleteView(SoftDeleteView):
    permission_required = "access_control.manage"
    model = Role
    success_url = reverse_lazy("access_control:role_list")
    success_message = "Role deleted."


class PermissionListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "access_control.view"
    model = Permission
    template_name = "access_control/permission_list.html"
    context_object_name = "permissions"
    queryset = Permission.objects.order_by("seq", "title")
    search_fields = ("title", "code")
    filter_fields = {"status": "status"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Permissions", "")]
        return context

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class PermissionCreateView(AuditSaveMixin, PortalPermissionRequiredMixin, CreateView):
    permission_required = "access_control.manage"
    model = Permission
    form_class = PermissionForm
    template_name = "access_control/permission_form.html"
    success_url = reverse_lazy("access_control:permission_list")
    success_message = "Permission saved."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Permission"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Permissions", self.success_url), ("New", "")]
        return context


class PermissionUpdateView(AuditSaveMixin, PortalPermissionRequiredMixin, UpdateView):
    permission_required = "access_control.manage"
    model = Permission
    form_class = PermissionForm
    template_name = "access_control/permission_form.html"
    success_url = reverse_lazy("access_control:permission_list")
    success_message = "Permission updated."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Permission"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Permissions", self.success_url), ("Edit", "")]
        return context


class PermissionDeleteView(SoftDeleteView):
    permission_required = "access_control.manage"
    model = Permission
    success_url = reverse_lazy("access_control:permission_list")
    success_message = "Permission deleted."


class UserAssignmentListView(SearchFilterPaginationMixin, PortalPermissionRequiredMixin, ListView):
    permission_required = "access_control.view"
    template_name = "access_control/user_assignment_list.html"
    context_object_name = "assignments"
    queryset = UserAssignment.objects.select_related("user", "role", "organization", "branch")
    search_fields = ("user__username", "user__name", "user__email", "role__title", "organization__title", "branch__title")
    filter_fields = {"status": "status", "role": "role_id", "organization": "organization_id"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("User Assignments", "")]
        return context

    def get_filter_specs(self):
        return [
            {"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")},
            {"name": "role", "label": "All roles", "choices": [(str(role.pk), role.title) for role in Role.objects.order_by("title")], "value": self.request.GET.get("role", "")},
            {
                "name": "organization",
                "label": "All organizations",
                "choices": [(str(org.pk), org.title) for org in Organization.objects.order_by("title")],
                "value": self.request.GET.get("organization", ""),
            },
        ]


class UserAssignmentCreateView(AuditSaveMixin, PortalPermissionRequiredMixin, CreateView):
    permission_required = "access_control.manage"
    model = UserAssignment
    form_class = UserAssignmentForm
    template_name = "access_control/user_assignment_form.html"
    success_url = reverse_lazy("access_control:user_assignment_list")
    success_message = "User assignment saved."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New User Assignment"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("User Assignments", self.success_url), ("New", "")]
        return context


class UserAssignmentUpdateView(AuditSaveMixin, PortalPermissionRequiredMixin, UpdateView):
    permission_required = "access_control.manage"
    model = UserAssignment
    form_class = UserAssignmentForm
    template_name = "access_control/user_assignment_form.html"
    success_url = reverse_lazy("access_control:user_assignment_list")
    success_message = "User assignment updated."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit User Assignment"
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("User Assignments", self.success_url), ("Edit", "")]
        return context


class UserAssignmentDeleteView(SoftDeleteView):
    permission_required = "access_control.manage"
    model = UserAssignment
    success_url = reverse_lazy("access_control:user_assignment_list")
    success_message = "User assignment deleted."
