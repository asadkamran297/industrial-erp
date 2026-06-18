from dataclasses import dataclass


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
