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


SECTION_WORKSPACE = "Workspace"
SECTION_OPERATIONS = "Operations"
SECTION_WORKFORCE = "Workforce"
SECTION_ANALYTICS = "Analytics"
SECTION_SETUP = "Setup"
SECTION_SUPPORT = "Support"


NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("Dashboard", permission="dashboard.view", url_name="portal:dashboard", section=SECTION_WORKSPACE, icon="D"),
    NavigationItem("Production", permission="operations.view", section=SECTION_OPERATIONS, icon="P"),
    NavigationItem("Inventory", permission="inventory.view", section=SECTION_OPERATIONS, icon="I"),
    NavigationItem("Employees", permission="employees.view", section=SECTION_WORKFORCE, icon="E"),
    NavigationItem("Reports", permission="reports.view", section=SECTION_ANALYTICS, icon="R"),
    NavigationItem(
        "Company Structure",
        permission="organizations.view",
        section=SECTION_SETUP,
        icon="C",
        children=(
            NavigationItem("Organizations", permission="organizations.view", url_name="organizations:organization_list"),
            NavigationItem("Branches", permission="organizations.view", url_name="organizations:branch_list"),
        ),
    ),
    NavigationItem(
        "Access Control",
        permission="access_control.view",
        section=SECTION_SETUP,
        icon="A",
        children=(
            NavigationItem("Roles", permission="access_control.view"),
            NavigationItem("Permissions", permission="access_control.view"),
            NavigationItem("User Assignments", permission="access_control.manage"),
        ),
    ),
    NavigationItem("System Settings", permission="settings.view", section=SECTION_SETUP, icon="S"),
    NavigationItem("Help Desk", permission="help.view", section=SECTION_SUPPORT, icon="?"),
)
