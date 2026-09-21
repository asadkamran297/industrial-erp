from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE
from apps.organizations.models import Branch, Organization


def _city(code, name_fragment, fallback=None):
    return (
        City.objects.filter(code=code).first()
        or City.objects.filter(title__icontains=name_fragment).first()
        or fallback
        or City.objects.order_by("title").first()
    )


def seed_organizations() -> int:
    created_count = 0

    sgd = _city("SGD", "Sargodha")
    lhe = _city("LHE", "Lahore", sgd)
    fsd = _city("FSD", "Faisalabad", sgd)

    mill, created = Organization.objects.update_or_create(
        code="ZFM",
        defaults={
            "title": "Zafaran Flour Mills (Pvt) Ltd",
            "phone": "+92-48-3712000",
            "cell": "+92-300-8600000",
            "fax": "+92-48-3712001",
            "email": "info@zafaranflour.pk",
            "website": "https://www.zafaranflour.pk",
            "address": "Mill Road, Sargodha, Punjab, Pakistan",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    branches = [
        {
            "code": "ZFM-MILL",
            "defaults": {
                "organization": mill,
                "city": sgd,
                "title": "Mill — Sargodha",
                "address": "Mill Road, Sargodha",
                "phone": "+92-48-3712000",
                "fax": "+92-48-3712001",
                "email": "mill@zafaranflour.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "ZFM-HO",
            "defaults": {
                "organization": mill,
                "city": sgd,
                "title": "Head Office — Sargodha",
                "address": "Katchery Road, Sargodha",
                "phone": "+92-48-3712100",
                "email": "office@zafaranflour.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "ZFM-DEPOT-LHE",
            "defaults": {
                "organization": mill,
                "city": lhe,
                "title": "Sales Depot — Lahore",
                "address": "Badami Bagh Grain Market, Lahore",
                "phone": "+92-42-37120000",
                "email": "lahore@zafaranflour.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "ZFM-DEPOT-FSD",
            "defaults": {
                "organization": mill,
                "city": fsd,
                "title": "Sales Depot — Faisalabad",
                "address": "Ghalla Mandi, Faisalabad",
                "phone": "+92-41-2612000",
                "email": "faisalabad@zafaranflour.pk",
                "status": STATUS_ACTIVE,
            },
        },
    ]

    for branch_data in branches:
        _, created = Branch.objects.update_or_create(
            code=branch_data["code"],
            defaults=branch_data["defaults"],
        )
        created_count += int(created)

    return created_count
