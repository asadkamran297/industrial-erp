from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import Customer


def seed_customers() -> int:
    created_count = 0
    _, created = Customer.objects.update_or_create(
        customer_code="CASH",
        defaults={
            "customer_name": "Cash Customer",
            "is_default": True,
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)
    return created_count
