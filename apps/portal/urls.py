from django.urls import path

from .views import DashboardView, FavouriteToggleView

app_name = "portal"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("favourites/toggle/", FavouriteToggleView.as_view(), name="favourite_toggle"),
]
