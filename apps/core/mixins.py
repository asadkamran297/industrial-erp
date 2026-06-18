from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q

from apps.access_control.selectors import user_has_permission


class PortalPermissionRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    permission_required: str | None = None

    def test_func(self):
        return user_has_permission(self.request.user, self.permission_required)


class SearchFilterPaginationMixin:
    paginate_by = 10
    search_fields: tuple[str, ...] = ()
    filter_fields: dict[str, str] = {}

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
                "has_table_filters": bool(query_string),
                "page_query": query_string,
                "page_query_prefix": f"{query_string}&" if query_string else "",
            }
        )
        return context
