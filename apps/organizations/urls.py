from django.urls import path

from .views import (
    BranchCreateView,
    BranchDetailView,
    BranchToggleStatusView,
    BranchListView,
    BranchUpdateView,
    OrganizationCreateView,
    OrganizationDetailView,
    OrganizationToggleStatusView,
    OrganizationListView,
    OrganizationUpdateView,
)

app_name = "organizations"

urlpatterns = [
    path("organizations/", OrganizationListView.as_view(), name="organization_list"),
    path("organizations/new/", OrganizationCreateView.as_view(), name="organization_create"),
    path("organizations/<int:pk>/edit/", OrganizationUpdateView.as_view(), name="organization_update"),
    path("organizations/<int:pk>/", OrganizationDetailView.as_view(), name="organization_detail"),
    path("organizations/<int:pk>/toggle-status/", OrganizationToggleStatusView.as_view(), name="organization_toggle_status"),
    path("branches/", BranchListView.as_view(), name="branch_list"),
    path("branches/new/", BranchCreateView.as_view(), name="branch_create"),
    path("branches/<int:pk>/edit/", BranchUpdateView.as_view(), name="branch_update"),
    path("branches/<int:pk>/", BranchDetailView.as_view(), name="branch_detail"),
    path("branches/<int:pk>/toggle-status/", BranchToggleStatusView.as_view(), name="branch_toggle_status"),
]
