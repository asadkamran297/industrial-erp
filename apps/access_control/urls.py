from django.urls import path

from .views import (
    PermissionCreateView,
    PermissionDeleteView,
    PermissionListView,
    PermissionUpdateView,
    RoleCreateView,
    RoleDeleteView,
    RoleListView,
    RoleUpdateView,
    UserAssignmentCreateView,
    UserAssignmentDeleteView,
    UserAssignmentListView,
    UserAssignmentUpdateView,
)

app_name = "access_control"

urlpatterns = [
    path("roles/", RoleListView.as_view(), name="role_list"),
    path("roles/new/", RoleCreateView.as_view(), name="role_create"),
    path("roles/<int:pk>/edit/", RoleUpdateView.as_view(), name="role_update"),
    path("roles/<int:pk>/delete/", RoleDeleteView.as_view(), name="role_delete"),
    path("permissions/", PermissionListView.as_view(), name="permission_list"),
    path("permissions/new/", PermissionCreateView.as_view(), name="permission_create"),
    path("permissions/<int:pk>/edit/", PermissionUpdateView.as_view(), name="permission_update"),
    path("permissions/<int:pk>/delete/", PermissionDeleteView.as_view(), name="permission_delete"),
    path("user-assignments/", UserAssignmentListView.as_view(), name="user_assignment_list"),
    path("user-assignments/new/", UserAssignmentCreateView.as_view(), name="user_assignment_create"),
    path("user-assignments/<int:pk>/edit/", UserAssignmentUpdateView.as_view(), name="user_assignment_update"),
    path("user-assignments/<int:pk>/delete/", UserAssignmentDeleteView.as_view(), name="user_assignment_delete"),
]
