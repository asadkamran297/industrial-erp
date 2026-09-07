from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.constants import GODOWN_STATUS_CHOICES, GODOWN_TYPE_CHOICES
from apps.core.mixins import PagePermissionRequiredMixin, SearchFilterPaginationMixin

from . import selectors, services
from .forms import GodownForm
from .models import Godown

PAGE = "godowns.godowns"


def _crumbs(*trail):
    return [("Dashboard", reverse("portal:dashboard")), ("Godowns", reverse("godowns:godown_list")), *trail]


class GodownListView(PagePermissionRequiredMixin, SearchFilterPaginationMixin, ListView):
    page = PAGE
    model = Godown
    template_name = "godowns/godown_list.html"
    context_object_name = "rows"
    paginate_by = 25
    search_fields = ("code", "name", "location", "incharge")
    filter_fields = {"godown_type": "godown_type", "status": "status"}

    def get_queryset(self):
        self.queryset = selectors.godowns()
        return super().get_queryset()

    def get_filter_specs(self):
        return [
            {"name": "godown_type", "label": "All types", "choices": GODOWN_TYPE_CHOICES,
             "value": self.request.GET.get("godown_type", "")},
            {"name": "status", "label": "All statuses", "choices": GODOWN_STATUS_CHOICES,
             "value": self.request.GET.get("status", "")},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Godowns"
        context["create_url"] = reverse("godowns:godown_create")
        context["breadcrumbs"] = _crumbs()
        return context


class GodownCreateView(PagePermissionRequiredMixin, CreateView):
    page = PAGE
    model = Godown
    form_class = GodownForm
    template_name = "godowns/godown_form.html"
    success_url = reverse_lazy("godowns:godown_list")

    def form_valid(self, form):
        self.object = services.save_godown(form.instance, self.request.user)
        messages.success(self.request, f"{self.object.name} saved.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("title", "Add Godown")
        context["breadcrumbs"] = _crumbs((context["title"], ""))
        return context


class GodownUpdateView(GodownCreateView, UpdateView):
    def get_context_data(self, **kwargs):
        return super().get_context_data(title=f"Edit {self.object.name}", **kwargs)


class GodownStatusToggleView(PagePermissionRequiredMixin, View):
    page = PAGE
    action = "edit"

    def post(self, request, pk):
        godown = get_object_or_404(Godown, pk=pk)
        services.toggle_status(godown, request.user)
        messages.success(request, f"{godown.name} is now {godown.get_status_display().lower()}.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("godowns:godown_list"))
