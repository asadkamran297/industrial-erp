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
    NavigationItem("Finance", permission="finance.view", section=SECTION_OPERATIONS, icon="F", children=(
        NavigationItem("Fiscal Years", permission="finance.view", url_name="finance:fiscal_year_list"),
        NavigationItem("Chart of Accounts", permission="finance.view", url_name="finance:account_configuration_list"),
        NavigationItem("Vouchers", permission="finance.view", url_name="finance:account_voucher_list"),
    )),
    NavigationItem("Employees", permission="employees.view", section=SECTION_WORKFORCE, icon="E", url_name="hr:employee_list"),
    NavigationItem("Payroll", permission="payroll.view", section=SECTION_WORKFORCE, icon="P", children=(
        NavigationItem("Salary Items", permission="payroll.view", url_name="payroll:employee_salary_list"),
        NavigationItem("Payroll Runs", permission="payroll.view", url_name="payroll:payroll_list"),
    )),
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
            NavigationItem("Roles", permission="access_control.view", url_name="access_control:role_list"),
            NavigationItem("Permissions", permission="access_control.view", url_name="access_control:permission_list"),
            NavigationItem("User Assignments", permission="access_control.manage", url_name="access_control:user_assignment_list"),
        ),
    ),
    NavigationItem("Master Data", permission="configurations.view", section=SECTION_SETUP, icon="M", children=(
        NavigationItem("Departments", permission="configurations.view", href="/masters/departments/"),
        NavigationItem("Designations", permission="configurations.view", href="/masters/designations/"),
        NavigationItem("Cities", permission="configurations.view", href="/masters/cities/"),
        NavigationItem("Job Types", permission="configurations.view", href="/masters/job-types/"),
        NavigationItem("Banks", permission="configurations.view", href="/masters/banks/"),
        NavigationItem("Allowances & Deductions", permission="configurations.view", href="/masters/allowance-deductions/"),
    )),
    NavigationItem("System Settings", permission="settings.view", section=SECTION_SETUP, icon="S"),
    NavigationItem("Help Desk", permission="help.view", section=SECTION_SUPPORT, icon="?"),
)
