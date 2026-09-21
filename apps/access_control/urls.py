from django.urls import path

from .views import (
    PermissionCreateView,
    PermissionDetailView,
    PermissionToggleStatusView,
    PermissionListView,
    PermissionUpdateView,
    RoleCreateView,
    RoleDetailView,
    RoleToggleStatusView,
    RoleListView,
    RoleUpdateView,
    UserAssignmentCreateView,
    UserAssignmentDetailView,
    UserAssignmentToggleStatusView,
    UserAssignmentListView,
    UserAssignmentUpdateView,
)

app_name = "access_control"

urlpatterns = [
    path("roles/", RoleListView.as_view(), name="role_list"),
    path("roles/new/", RoleCreateView.as_view(), name="role_create"),
    path("roles/<int:pk>/edit/", RoleUpdateView.as_view(), name="role_update"),
    path("roles/<int:pk>/", RoleDetailView.as_view(), name="role_detail"),
    path("roles/<int:pk>/toggle-status/", RoleToggleStatusView.as_view(), name="role_toggle_status"),
    path("permissions/", PermissionListView.as_view(), name="permission_list"),
    path("permissions/new/", PermissionCreateView.as_view(), name="permission_create"),
    path("permissions/<int:pk>/edit/", PermissionUpdateView.as_view(), name="permission_update"),
    path("permissions/<int:pk>/", PermissionDetailView.as_view(), name="permission_detail"),
    path("permissions/<int:pk>/toggle-status/", PermissionToggleStatusView.as_view(), name="permission_toggle_status"),
    path("user-assignments/", UserAssignmentListView.as_view(), name="user_assignment_list"),
    path("user-assignments/new/", UserAssignmentCreateView.as_view(), name="user_assignment_create"),
    path("user-assignments/<int:pk>/edit/", UserAssignmentUpdateView.as_view(), name="user_assignment_update"),
    path("user-assignments/<int:pk>/", UserAssignmentDetailView.as_view(), name="user_assignment_detail"),
    path("user-assignments/<int:pk>/toggle-status/", UserAssignmentToggleStatusView.as_view(), name="user_assignment_toggle_status"),
]
