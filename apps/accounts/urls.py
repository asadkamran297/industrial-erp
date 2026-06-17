from django.urls import path

from .views import PortalLoginView

app_name = "accounts"

urlpatterns = [
    path("login/", PortalLoginView.as_view(), name="login"),
]
