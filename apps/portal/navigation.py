from dataclasses import dataclass

from django.http import HttpRequest
from django.urls import reverse

from apps.access_control.selectors import get_user_permission_codes


@dataclass(frozen=True)
class NavigationItem:
    label: str
    permission: str | None = None
    url_name: str | None = None
    href: str = "#"
    section: str = "main"
    icon: str = ""


NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("Dashboard", permission="dashboard.view", url_name="portal:dashboard", icon="D"),
    NavigationItem("Operations", permission="operations.view", section="work", icon="O"),
    NavigationItem("Inventory", permission="inventory.view", section="work", icon="I"),
    NavigationItem("Employees", permission="employees.view", section="people", icon="E"),
    NavigationItem("Reports", permission="reports.view", section="insights", icon="R"),
    NavigationItem("Settings", permission="settings.view", section="admin", icon="S"),
    NavigationItem("Help", permission="help.view", section="support", icon="?"),
)


def resolve_nav_href(item: NavigationItem) -> str:
    if item.url_name:
        return reverse(item.url_name)
    return item.href


def get_portal_navigation(request: HttpRequest) -> list[dict[str, str | bool]]:
    permission_codes = get_user_permission_codes(request.user)
    current_path = request.path
    navigation = []

    for item in NAV_ITEMS:
        if item.permission and "*" not in permission_codes and item.permission not in permission_codes:
            continue

        href = resolve_nav_href(item)
        navigation.append(
            {
                "label": item.label,
                "href": href,
                "section": item.section,
                "icon": item.icon,
                "permission": item.permission or "",
                "is_active": href != "#" and current_path.startswith(href),
            }
        )

    return navigation
