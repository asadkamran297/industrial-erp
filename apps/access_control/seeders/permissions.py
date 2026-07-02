from apps.access_control.models import Permission
from apps.access_control.pages import iter_page_permissions
from apps.core.constants import STATUS_ACTIVE

# Coarse module-level codes replaced by page-level codes. Pruned on reseed so the
# switch to page-level access control is clean. User-created custom permissions
# (any code outside this list) are left untouched.
LEGACY_CODES = [
    "dashboard.view",
    "operations.view",
    "inventory.view",
    "inventory.manage",
    "configurations.view",
    "configurations.manage",
    "organizations.view",
    "organizations.manage",
    "access_control.view",
    "access_control.manage",
    "hr.view",
    "hr.manage",
    "employees.view",
    "employees.manage",
    "payroll.view",
    "payroll.generate",
    "payroll.approve",
    "finance.view",
    "finance.manage",
    "reports.view",
    "settings.view",
    "settings.manage",
    "help.view",
]


def seed_permissions() -> int:
    Permission.all_objects.filter(code__in=LEGACY_CODES).delete()

    created_count = 0
    for code, title, seq in iter_page_permissions():
        _, created = Permission.objects.update_or_create(
            code=code,
            defaults={"title": title, "seq": seq, "status": STATUS_ACTIVE},
        )
        created_count += int(created)
    return created_count
