from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q

from apps.access_control.selectors import user_has_permission
from apps.core.constants import STATUS_ACTIVE


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

    def test_func(self):
        return user_has_permission(self.request.user, self.permission_required)


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
            search_query = Q()
            for field in self.search_fields:
                search_query |= Q(**{f"{field}__icontains": query})
            queryset = queryset.filter(search_query)

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
