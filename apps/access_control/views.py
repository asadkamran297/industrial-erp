from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.constants import RECORD_STATUS_CHOICES
from apps.core.mixins import PagePermissionRequiredMixin, PortalPermissionRequiredMixin, SearchFilterPaginationMixin, SortableListMixin
from apps.core.views import SaveAndNewMixin, MasterDetailView, ToggleStatusView
from django.db.models import Count
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


class RoleListView(SortableListMixin, SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "access_control.roles"
    model = Role
    template_name = "access_control/role_list.html"
    context_object_name = "roles"
    queryset = Role.objects.annotate(permission_count=Count("permission_links")).order_by("title")
    search_fields = ("title",)
    filter_fields = {"status": "status"}
    sort_fields = {"title": "title", "permissions": "permission_count", "status": ("status", "title")}
    default_sort = "title"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Roles", "")]
        return context

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class RoleCreateView(SaveAndNewMixin, AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
    page = "access_control.roles"
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


class RoleUpdateView(AuditSaveMixin, PagePermissionRequiredMixin, UpdateView):
    page = "access_control.roles"
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





class PermissionListView(SortableListMixin, SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "access_control.permissions"
    model = Permission
    template_name = "access_control/permission_list.html"
    context_object_name = "permissions"
    queryset = Permission.objects.order_by("seq", "title")
    search_fields = ("title", "code")
    filter_fields = {"status": "status"}
    sort_fields = {"title": "title", "code": "code", "seq": ("seq", "title"), "status": ("status", "title")}
    default_sort = "seq"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [("Dashboard", reverse_lazy("portal:dashboard")), ("Permissions", "")]
        return context

    def get_filter_specs(self):
        return [{"name": "status", "label": "All statuses", "choices": RECORD_STATUS_CHOICES, "value": self.request.GET.get("status", "")}]


class PermissionCreateView(SaveAndNewMixin, AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
    page = "access_control.permissions"
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


class PermissionUpdateView(AuditSaveMixin, PagePermissionRequiredMixin, UpdateView):
    page = "access_control.permissions"
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





class UserAssignmentListView(SortableListMixin, SearchFilterPaginationMixin, PagePermissionRequiredMixin, ListView):
    page = "access_control.user_assignments"
    model = UserAssignment
    template_name = "access_control/user_assignment_list.html"
    context_object_name = "assignments"
    queryset = UserAssignment.objects.select_related("user", "role", "organization", "branch")
    search_fields = ("user__username", "user__name", "user__email", "role__title", "organization__title", "branch__title")
    filter_fields = {"status": "status", "role": "role_id", "organization": "organization_id"}
    sort_fields = {"user": "user__name", "role": "role__title", "organization": "organization__title", "branch": "branch__title", "primary": "-is_primary", "status": ("status", "user__name")}
    default_sort = "user"

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


class UserAssignmentCreateView(SaveAndNewMixin, AuditSaveMixin, PagePermissionRequiredMixin, CreateView):
    page = "access_control.user_assignments"
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


class UserAssignmentUpdateView(AuditSaveMixin, PagePermissionRequiredMixin, UpdateView):
    page = "access_control.user_assignments"
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




class RoleToggleStatusView(ToggleStatusView):
    page = "access_control.roles"
    model = Role
    success_url_name = "access_control:role_list"


class RoleDetailView(MasterDetailView):
    page = "access_control.roles"
    model = Role
    kind = "Role"
    list_url_name = "access_control:role_list"
    edit_url_name = "access_control:role_update"
    detail_fields = (("Title", "title"), ("Status", "status"))
    template_name = "access_control/role_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["permissions"] = Permission.objects.filter(role_links__role=self.object).order_by("seq", "title")
        return context


class PermissionToggleStatusView(ToggleStatusView):
    page = "access_control.permissions"
    model = Permission
    success_url_name = "access_control:permission_list"


class PermissionDetailView(MasterDetailView):
    page = "access_control.permissions"
    model = Permission
    kind = "Permission"
    list_url_name = "access_control:permission_list"
    edit_url_name = "access_control:permission_update"
    detail_fields = (("Title", "title"), ("Code", "code"), ("Sequence", "seq"), ("Status", "status"))


class UserAssignmentToggleStatusView(ToggleStatusView):
    page = "access_control.user_assignments"
    model = UserAssignment
    success_url_name = "access_control:user_assignment_list"


class UserAssignmentDetailView(MasterDetailView):
    page = "access_control.user_assignments"
    model = UserAssignment
    kind = "User Assignment"
    title_attr = "user.display_name"
    subtitle_attr = "role.title"
    list_url_name = "access_control:user_assignment_list"
    edit_url_name = "access_control:user_assignment_update"
    detail_fields = (
        ("User", "user.display_name"), ("Role", "role"), ("Organization", "organization"), ("Branch", "branch"),
        ("Start Date", "start_date"), ("End Date", "end_date"), ("Primary", "is_primary"), ("Status", "status"),
    )
