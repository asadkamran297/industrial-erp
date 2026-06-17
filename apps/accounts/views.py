from django.contrib.auth.views import LoginView

from .forms import PortalAuthenticationForm


class PortalLoginView(LoginView):
    authentication_form = PortalAuthenticationForm
    template_name = "auth/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)
        return response
