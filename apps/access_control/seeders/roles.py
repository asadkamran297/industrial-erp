from apps.access_control.models import Permission, Role, RolePermission
from apps.core.constants import STATUS_ACTIVE


ROLE_PERMISSION_CODES = {
    "Super Admin": ["*"],
    "Admin": [
        "dashboard.view",
        "operations.view",
        "inventory.view",
        "configurations.view",
        "configurations.manage",
        "organizations.view",
        "organizations.manage",
        "access_control.view",
        "hr.view",
        "hr.manage",
        "employees.view",
        "employees.manage",
        "payroll.view",
        "reports.view",
        "settings.view",
        "help.view",
    ],
    "HR Manager": [
        "dashboard.view",
        "help.view",
        "hr.view",
        "hr.manage",
        "employees.view",
        "employees.manage",
        "reports.view",
    ],
    "Payroll Officer": [
        "dashboard.view",
        "help.view",
        "employees.view",
        "payroll.view",
        "payroll.generate",
        "reports.view",
    ],
    "Payroll Approver": [
        "dashboard.view",
        "help.view",
        "employees.view",
        "payroll.view",
        "payroll.approve",
        "reports.view",
    ],
    "Manager": [
        "dashboard.view",
        "operations.view",
        "inventory.view",
        "help.view",
        "employees.view",
        "payroll.view",
        "reports.view",
    ],
    "Operator": [
        "dashboard.view",
        "operations.view",
        "inventory.view",
        "help.view",
        "employees.view",
    ],
    "Viewer": [
        "dashboard.view",
        "help.view",
        "reports.view",
    ],
}


def seed_roles() -> int:
    created_count = 0
    all_permissions = list(Permission.objects.all())
    permissions_by_code = {permission.code: permission for permission in all_permissions}

    for role_title, permission_codes in ROLE_PERMISSION_CODES.items():
        role, created = Role.objects.update_or_create(
            title=role_title,
            defaults={"status": STATUS_ACTIVE},
        )
        created_count += int(created)

        selected_permissions = all_permissions if permission_codes == ["*"] else [
            permissions_by_code[code] for code in permission_codes if code in permissions_by_code
        ]
        for permission in selected_permissions:
            _, link_created = RolePermission.objects.get_or_create(role=role, permission=permission)
            created_count += int(link_created)

    return created_count
