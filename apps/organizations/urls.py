from django.urls import path

from .views import (
    BranchCreateView,
    BranchListView,
    BranchUpdateView,
    OrganizationCreateView,
    OrganizationListView,
    OrganizationUpdateView,
)

app_name = "organizations"

urlpatterns = [
    path("organizations/", OrganizationListView.as_view(), name="organization_list"),
    path("organizations/new/", OrganizationCreateView.as_view(), name="organization_create"),
    path("organizations/<int:pk>/edit/", OrganizationUpdateView.as_view(), name="organization_update"),
    path("branches/", BranchListView.as_view(), name="branch_list"),
    path("branches/new/", BranchCreateView.as_view(), name="branch_create"),
    path("branches/<int:pk>/edit/", BranchUpdateView.as_view(), name="branch_update"),
]
