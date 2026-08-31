from typing import Any
from urllib.parse import parse_qs

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
    # must match on the query as well, or they would all light up together. The
    # item's own params must be present; the page's other params (period, page,
    # search) are free to vary without dropping the highlight.
    if "?" in href:
        path, _, query = href.partition("?")
        normalized = path.rstrip("/")
        # Pages under the item's path count too (the list's own entry screen),
        # provided the item's params match — otherwise a sibling type would match.
        if current_path.rstrip("/") != normalized and not current_path.startswith(f"{normalized}/"):
            return False
        current = parse_qs(current_query)
        return all(value in current.get(key, []) for key, values in parse_qs(query).items() for value in values)
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
    is_active = is_href_active(href, current_path, current_query) or any(
        is_href_active(path, current_path, current_query) for path in item.match_paths
    )
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
        # The page you are on and the branch leading to it read differently: only
        # one item at a time is the current page.
        "item_class": get_nav_item_class(depth, bool(children), is_active, has_active_child),
        "icon_class": get_nav_icon_class(is_active, has_active_child),
    }


def get_nav_item_class(depth: int, has_children: bool, is_active: bool, on_active_path: bool = False) -> str:
    base = "flex w-full items-center text-left text-sm outline-none transition focus-visible:ring-2 focus-visible:ring-[var(--primary-color)]/30"
    if depth == 0:
        size = "min-h-10 gap-3 rounded-lg px-3 font-semibold"
        active = "bg-[var(--primary-color)] text-white shadow-sm shadow-blue-900/10"
        # An open branch is marked, not filled: the filled pill stays reserved for
        # the page actually on screen.
        on_path = "bg-[color-mix(in_srgb,var(--primary-color)_12%,transparent)] text-[var(--primary-color)] dark:bg-[color-mix(in_srgb,var(--primary-color)_28%,transparent)]"
        inactive = "text-slate-700 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
    else:
        size = "min-h-9 gap-2 rounded-lg px-3"
        # The same filled pill the top level gets, in the brand hue chosen in
        # the header. The page somebody is actually on is marked one way
        # throughout the menu: a child that was merely tinted read as another
        # shade of "nearby" next to its own parent, which is also tinted.
        active = "bg-[var(--primary-color)] font-semibold text-white shadow-sm shadow-blue-900/10"
        on_path = "font-semibold text-[var(--primary-color)] dark:text-white"
        inactive = "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
    if depth >= 2 and not has_children:
        size = "min-h-9 rounded-md px-3"
    state = active if is_active else (on_path if on_active_path else inactive)
    return f"{base} {size} {state}"


def get_nav_icon_class(is_active: bool, on_active_path: bool = False) -> str:
    base = "grid h-7 w-7 shrink-0 place-items-center rounded-md text-xs font-bold"
    # White only works on the filled pill; an open branch keeps a tinted chip.
    active = "bg-white/15 text-white"
    on_path = "bg-[color-mix(in_srgb,var(--primary-color)_12%,transparent)] text-[var(--primary-color)] dark:bg-[color-mix(in_srgb,var(--primary-color)_28%,transparent)]"
    inactive = "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300"
    return f"{base} {active if is_active else (on_path if on_active_path else inactive)}"


def get_portal_navigation(request: HttpRequest) -> list[dict[str, Any]]:
    permission_codes = get_user_permission_codes(request.user)
    current_path = request.path
    # A record page (voucher detail/edit/print) carries no query of its own, so
    # nothing would tell the sidebar which of the query-scoped siblings it
    # belongs to. Views set ``nav_query`` to say so.
    current_query = getattr(request, "nav_query", "") or request.GET.urlencode()
    navigation = []

    for item in NAV_ITEMS:
        nav_item = build_navigation_item(item, permission_codes, current_path, current_query=current_query)
        if nav_item is not None:
            navigation.append(nav_item)

    return navigation
