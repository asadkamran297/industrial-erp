from typing import Any

from django.http import HttpRequest
from django.urls import reverse

from apps.access_control.selectors import get_user_permission_codes

from .constants import NAV_ITEMS, NavigationItem


def resolve_nav_href(item: NavigationItem) -> str:
    href = reverse(item.url_name) if item.url_name else item.href
    return f"{href}?{item.query}" if item.query else href


def user_can_view_item(item: NavigationItem, permission_codes: set[str]) -> bool:
    if not item.permission or "*" in permission_codes:
        return True
    return item.permission in permission_codes


def is_href_active(href: str, current_path: str, current_query: str = "") -> bool:
    if href == "#":
        return False
    # Siblings that share a path and differ only by query (the voucher types)
    # must match on the query as well, or they would all light up together.
    if "?" in href:
        path, _, query = href.partition("?")
        return current_path.rstrip("/") == path.rstrip("/") and query == current_query
    if href == "/":
        return current_path == href
    normalized_href = href.rstrip("/")
    return current_path == normalized_href or current_path.startswith(f"{normalized_href}/")


def build_navigation_item(
    item: NavigationItem,
    permission_codes: set[str],
    current_path: str,
    depth: int = 0,
    current_query: str = "",
) -> dict[str, Any] | None:
    children = [
        child
        for child in (
            build_navigation_item(child_item, permission_codes, current_path, depth + 1, current_query)
            for child_item in item.children
        )
        if child is not None
    ]

    # A parent that declares children but has none visible is hidden entirely.
    if item.children and not children:
        return None

    if not user_can_view_item(item, permission_codes) and not children:
        return None

    href = resolve_nav_href(item)
    is_active = is_href_active(href, current_path, current_query)
    has_active_child = any(child["is_active"] or child["is_open"] for child in children)

    return {
        "label": item.label,
        "href": href,
        "section": item.section,
        "icon": item.icon,
        "permission": item.permission or "",
        "depth": depth,
        "children": children,
        "has_children": bool(children),
        "is_active": is_active or has_active_child,
        "is_current": is_active,
        "is_open": has_active_child,
        "item_class": get_nav_item_class(depth, bool(children), is_active or has_active_child),
        "icon_class": get_nav_icon_class(is_active or has_active_child),
    }


def get_nav_item_class(depth: int, has_children: bool, is_active: bool) -> str:
    base = "flex w-full items-center text-left text-sm outline-none transition focus-visible:ring-2 focus-visible:ring-[var(--primary-color)]/30"
    if depth == 0:
        size = "min-h-10 gap-3 rounded-lg px-3 font-semibold"
        active = "bg-[var(--primary-color)] text-white shadow-sm shadow-blue-900/10"
        inactive = "text-slate-700 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
    else:
        size = "min-h-9 gap-2 rounded-md px-3"
        active = "bg-slate-100 font-semibold text-[var(--primary-color)] dark:bg-slate-800"
        inactive = "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
    if depth >= 2 and not has_children:
        size = "min-h-9 rounded-md px-3"
    return f"{base} {size} {active if is_active else inactive}"


def get_nav_icon_class(is_active: bool) -> str:
    base = "grid h-7 w-7 shrink-0 place-items-center rounded-md text-xs font-bold"
    active = "bg-white/15 text-white"
    inactive = "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300"
    return f"{base} {active if is_active else inactive}"


def get_portal_navigation(request: HttpRequest) -> list[dict[str, Any]]:
    permission_codes = get_user_permission_codes(request.user)
    current_path = request.path
    current_query = request.GET.urlencode()
    navigation = []

    for item in NAV_ITEMS:
        nav_item = build_navigation_item(item, permission_codes, current_path, current_query=current_query)
        if nav_item is not None:
            navigation.append(nav_item)

    return navigation
