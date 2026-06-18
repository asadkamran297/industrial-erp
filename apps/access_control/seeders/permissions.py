from apps.access_control.models import Permission
from apps.core.constants import STATUS_ACTIVE


PERMISSIONS = [
    ("dashboard.view", "View Dashboard"),
    ("operations.view", "View Operations"),
    ("inventory.view", "View Inventory"),
    ("configurations.view", "View Configuration Masters"),
    ("configurations.manage", "Manage Configuration Masters"),
    ("organizations.view", "View Organizations"),
    ("organizations.manage", "Manage Organizations"),
    ("access_control.view", "View Access Control"),
    ("access_control.manage", "Manage Access Control"),
    ("hr.view", "View HR"),
    ("hr.manage", "Manage HR"),
    ("employees.view", "View Employees"),
    ("employees.manage", "Manage Employees"),
    ("payroll.view", "View Payroll"),
    ("payroll.generate", "Generate Payroll"),
    ("payroll.approve", "Approve Payroll"),
    ("finance.view", "View Finance"),
    ("finance.manage", "Manage Finance"),
    ("reports.view", "View Reports"),
    ("settings.view", "View Settings"),
    ("settings.manage", "Manage Settings"),
    ("help.view", "View Help"),
]


def seed_permissions() -> int:
    created_count = 0
    for seq, (code, title) in enumerate(PERMISSIONS, start=10):
        _, created = Permission.objects.update_or_create(
            code=code,
            defaults={"title": title, "seq": seq * 10, "status": STATUS_ACTIVE},
        )
        created_count += int(created)
    return created_count
