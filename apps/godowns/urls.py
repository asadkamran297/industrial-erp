from django.urls import path

from .views import GodownCreateView, GodownListView, GodownStatusToggleView, GodownUpdateView

app_name = "godowns"

urlpatterns = [
    path("", GodownListView.as_view(), name="godown_list"),
    path("new/", GodownCreateView.as_view(), name="godown_create"),
    path("<int:pk>/edit/", GodownUpdateView.as_view(), name="godown_update"),
    path("<int:pk>/toggle-status/", GodownStatusToggleView.as_view(), name="godown_status_toggle"),
]
