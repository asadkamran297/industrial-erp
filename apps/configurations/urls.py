from django.urls import path

from .views import MasterCreateView, MasterToggleStatusView, MasterDetailView, MasterListView, MasterUpdateView

app_name = "configurations"

urlpatterns = [
    path("<slug:slug>/", MasterListView.as_view(), name="master_list"),
    path("<slug:slug>/new/", MasterCreateView.as_view(), name="master_create"),
    path("<slug:slug>/<int:pk>/edit/", MasterUpdateView.as_view(), name="master_update"),
    path("<slug:slug>/<int:pk>/", MasterDetailView.as_view(), name="master_detail"),
    path("<slug:slug>/<int:pk>/toggle-status/", MasterToggleStatusView.as_view(), name="master_toggle_status"),
]
