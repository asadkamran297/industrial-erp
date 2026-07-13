from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.detail import DetailView

from apps.access_control.selectors import user_has_permission
from apps.core.constants import ACTION_ADD, ACTION_DELETE, ACTION_EDIT, ACTION_INDEX, ACTION_VIEW, STATUS_ACTIVE


class PrintContextMixin:
    """Injects organization + branch (header/footer data) into any print view."""

    def _build_print_context(self, request):
        from apps.organizations.models import Branch, Organization
        return {
            "org": Organization.objects.filter(status=STATUS_ACTIVE).order_by("id").first(),
            "branch": Branch.objects.filter(status=STATUS_ACTIVE).select_related("city").order_by("id").first(),
            "printed_by": request.user,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for key, val in self._build_print_context(self.request).items():
            context.setdefault(key, val)
        return context

    def get_print_context(self, request):
        """For plain View subclasses that don't use get_context_data."""
        return self._build_print_context(request)


class PortalPermissionRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    permission_required: str | None = None

    def get_permission_required(self) -> str | None:
        return self.permission_required

    def test_func(self):
        return user_has_permission(self.request.user, self.get_permission_required())


class PagePermissionRequiredMixin(PortalPermissionRequiredMixin):
    """Page-level access control.

    Set ``page`` (e.g. ``"inventory.items"``) on a view and the required
    permission code is ``<page>.<action>`` where the action is inferred from the
    generic view type (Create->add, Update->edit, Delete->delete, Detail->view,
    otherwise index). Override ``action`` for non-CRUD verbs, or set
    ``permission_required`` directly as an escape hatch.
    """

    page: str | None = None
    action: str | None = None

    def _infer_action(self) -> str:
        # Order matters: update views commonly subclass create views
        # (``class FooUpdateView(FooCreateView, UpdateView)``), so check the more
        # specific verbs first.
        if isinstance(self, DeleteView):
            return ACTION_DELETE
        if isinstance(self, UpdateView):
            return ACTION_EDIT
        if isinstance(self, CreateView):
            return ACTION_ADD
        if isinstance(self, DetailView):
            return ACTION_VIEW
        return ACTION_INDEX

    def get_permission_required(self) -> str | None:
        if self.permission_required:
            return self.permission_required
        if not self.page:
            return None
        return f"{self.page}.{self.action or self._infer_action()}"

    def get_page_key(self) -> str | None:
        return self.page

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.get_page_key()
        if page:
            user = self.request.user
            context.setdefault("can_view", user_has_permission(user, f"{page}.view"))
            context.setdefault("can_add", user_has_permission(user, f"{page}.add"))
            context.setdefault("can_edit", user_has_permission(user, f"{page}.edit"))
            context.setdefault("can_delete", user_has_permission(user, f"{page}.delete"))
        return context


class SearchFilterPaginationMixin:
    paginate_by = 10
    search_fields: tuple[str, ...] = ()
    filter_fields: dict[str, str] = {}
    # Generic from/to date-range filters. Each entry:
    #   {"field": <model field>, "label": <str>,
    #    "from_param": <GET key>, "to_param": <GET key>}
    # from_param/to_param default to "date_from"/"date_to" when omitted.
    date_filters: list[dict] = []

    def _date_filter_specs(self) -> list[dict]:
        specs = []
        for spec in self.date_filters:
            from_param = spec.get("from_param", "date_from")
            to_param = spec.get("to_param", "date_to")
            specs.append(
                {
                    "field": spec["field"],
                    "label": spec.get("label", "Date range"),
                    "from_param": from_param,
                    "to_param": to_param,
                    "from_value": self.request.GET.get(from_param, "").strip(),
                    "to_value": self.request.GET.get(to_param, "").strip(),
                }
            )
        return specs

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query and self.search_fields:
            for term in query.split():
                term_query = Q()
                for field in self.search_fields:
                    term_query |= Q(**{f"{field}__icontains": term})
                queryset = queryset.filter(term_query)

        for param, field in self.filter_fields.items():
            value = self.request.GET.get(param, "").strip()
            if value:
                queryset = queryset.filter(**{field: value})

        for spec in self._date_filter_specs():
            if spec["from_value"]:
                queryset = queryset.filter(**{f"{spec['field']}__gte": spec["from_value"]})
            if spec["to_value"]:
                queryset = queryset.filter(**{f"{spec['field']}__lte": spec["to_value"]})
        return queryset

    def get_filter_specs(self) -> list[dict]:
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        query_string = query_params.urlencode()
        context.update(
            {
                "search_query": self.request.GET.get("q", "").strip(),
                "filter_specs": self.get_filter_specs(),
                "date_filter_specs": self._date_filter_specs(),
                "has_table_filters": bool(query_string),
                "page_query": query_string,
                "page_query_prefix": f"{query_string}&" if query_string else "",
            }
        )
        return context
