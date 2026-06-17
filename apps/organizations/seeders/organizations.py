from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE
from apps.organizations.models import Branch, Organization


def seed_organizations() -> int:
    created_count = 0
    organization, created = Organization.objects.update_or_create(
        code="MAIN",
        defaults={"title": "Main Organization", "status": STATUS_ACTIVE},
    )
    created_count += int(created)

    city = City.objects.filter(code="LHE").first() or City.objects.order_by("title").first()
    _, created = Branch.objects.update_or_create(
        code="HO",
        defaults={
            "organization": organization,
            "city": city,
            "title": "Head Office",
            "address": "Head Office",
            "phone": "+92-000-0000000",
            "email": "info@example.com",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    _, created = Branch.objects.update_or_create(
        code="FACTORY",
        defaults={
            "organization": organization,
            "city": city,
            "title": "Factory",
            "address": "Factory Site",
            "phone": "+92-000-0000000",
            "email": "factory@example.com",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    return created_count
