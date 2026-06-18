from dataclasses import dataclass
from typing import Any

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
    children: tuple["NavigationItem", ...] = ()


NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("Dashboard", permission="dashboard.view", url_name="portal:dashboard", icon="D"),
    NavigationItem("Operations", permission="operations.view", section="work", icon="O"),
    NavigationItem("Inventory", permission="inventory.view", section="work", icon="I"),
    NavigationItem("Employees", permission="employees.view", section="people", icon="E"),
    NavigationItem("Reports", permission="reports.view", section="insights", icon="R"),
    NavigationItem(
        "Organization Setup",
        permission="organizations.view",
        section="admin",
        icon="O",
        children=(
            NavigationItem("Organizations", permission="organizations.view", url_name="organizations:organization_list"),
            NavigationItem("Branches", permission="organizations.view", url_name="organizations:branch_list"),
        ),
    ),
    NavigationItem(
        "IAMS",
        permission="access_control.view",
        section="admin",
        icon="A",
        children=(
            NavigationItem("Roles", permission="access_control.view"),
            NavigationItem("Permissions", permission="access_control.view"),
            NavigationItem("User Assignments", permission="access_control.manage"),
        ),
    ),
    NavigationItem("Settings", permission="settings.view", section="admin", icon="S"),
    NavigationItem("Help", permission="help.view", section="support", icon="?"),
)


def resolve_nav_href(item: NavigationItem) -> str:
    if item.url_name:
        return reverse(item.url_name)
    return item.href


def user_can_view_item(item: NavigationItem, permission_codes: set[str]) -> bool:
    if not item.permission or "*" in permission_codes:
        return True
    return item.permission in permission_codes


def is_href_active(href: str, current_path: str) -> bool:
    if href == "#":
        return False
    if href == "/":
        return current_path == href
    normalized_href = href.rstrip("/")
    return current_path == normalized_href or current_path.startswith(f"{normalized_href}/")


def build_navigation_item(
    item: NavigationItem,
    permission_codes: set[str],
    current_path: str,
) -> dict[str, Any] | None:
    children = [
        child
        for child in (
            build_navigation_item(child_item, permission_codes, current_path)
            for child_item in item.children
        )
        if child is not None
    ]

    if not user_can_view_item(item, permission_codes) and not children:
        return None

    href = resolve_nav_href(item)
    is_active = is_href_active(href, current_path)
    has_active_child = any(child["is_active"] or child["is_open"] for child in children)

    return {
        "label": item.label,
        "href": href,
        "section": item.section,
        "icon": item.icon,
        "permission": item.permission or "",
        "children": children,
        "has_children": bool(children),
        "is_active": is_active or has_active_child,
        "is_current": is_active,
        "is_open": has_active_child,
    }


def get_portal_navigation(request: HttpRequest) -> list[dict[str, Any]]:
    permission_codes = get_user_permission_codes(request.user)
    current_path = request.path
    navigation = []

    for item in NAV_ITEMS:
        nav_item = build_navigation_item(item, permission_codes, current_path)
        if nav_item is not None:
            navigation.append(nav_item)

    return navigation
