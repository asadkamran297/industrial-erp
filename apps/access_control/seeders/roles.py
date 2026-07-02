from apps.access_control.models import Permission, Role, RolePermission
from apps.access_control.pages import all_codes
from apps.core.constants import STATUS_ACTIVE


# Role definitions in the page-level scheme. Entries support:
#   "*"              -> every permission (wildcard)
#   "<page>.*"       -> all actions of a page or module prefix (e.g. "inventory.*")
#   "<page>.<action>"-> a single explicit code
ROLE_PERMISSION_CODES = {
    "Super Admin": ["*"],
    "Admin": [
        "dashboard.*",
        "operations.*",
        "reports.*",
        "settings.*",
        "help.*",
        "inventory.*",
        "finance.*",
        "hr.*",
        "payroll.*",
        "organizations.*",
        "configurations.*",
        "access_control.roles.index",
        "access_control.permissions.index",
        "access_control.user_assignments.index",
    ],
    "HR Manager": [
        "dashboard.index",
        "help.index",
        "reports.index",
        "hr.*",
        "payroll.salary_items.index",
        "payroll.runs.index",
    ],
    "Payroll Officer": [
        "dashboard.index",
        "help.index",
        "reports.index",
        "hr.employees.index",
        "hr.employees.view",
        "payroll.*",
    ],
    "Payroll Approver": [
        "dashboard.index",
        "help.index",
        "reports.index",
        "hr.employees.index",
        "hr.employees.view",
        "payroll.salary_items.index",
        "payroll.runs.*",
    ],
    "Manager": [
        "dashboard.index",
        "operations.index",
        "help.index",
        "reports.index",
        "inventory.*",
        "hr.employees.index",
        "hr.employees.view",
        "payroll.salary_items.index",
        "payroll.runs.index",
    ],
    "Operator": [
        "dashboard.index",
        "operations.index",
        "help.index",
        "inventory.*",
        "hr.employees.index",
    ],
    "Viewer": [
        "dashboard.index",
        "help.index",
        "reports.index",
    ],
}


def _expand(patterns: list[str], every_code: list[str]) -> set[str]:
    if patterns == ["*"]:
        return set(every_code)
    resolved: set[str] = set()
    for pattern in patterns:
        if pattern == "*":
            resolved.update(every_code)
        elif pattern.endswith(".*"):
            prefix = pattern[:-2]
            resolved.update(code for code in every_code if code == prefix or code.startswith(f"{prefix}."))
        else:
            resolved.add(pattern)
    return resolved


def seed_roles() -> int:
    created_count = 0
    every_code = all_codes()
    permissions_by_code = {permission.code: permission for permission in Permission.objects.all()}

    for role_title, patterns in ROLE_PERMISSION_CODES.items():
        role, created = Role.objects.update_or_create(
            title=role_title,
            defaults={"status": STATUS_ACTIVE},
        )
        created_count += int(created)

        wanted_codes = _expand(patterns, every_code)
        selected_permissions = [permissions_by_code[code] for code in wanted_codes if code in permissions_by_code]

        # Reset links so stale (coarse) permissions are removed on reseed.
        RolePermission.objects.filter(role=role).delete()
        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission=permission) for permission in selected_permissions]
        )
        created_count += len(selected_permissions)

    return created_count
