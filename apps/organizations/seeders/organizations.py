from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE
from apps.organizations.models import Branch, Organization


def seed_organizations() -> int:
    created_count = 0

    # ── Main (parent) organization ────────────────────────────────
    main_org, created = Organization.objects.update_or_create(
        code="MAIN",
        defaults={
            "title": "National Trading Corporation (Pvt) Ltd",
            "logo": "",
            "phone": "+92-42-35761234",
            "cell": "+92-300-8421234",
            "fax": "+92-42-35761235",
            "email": "info@ntcpvtltd.pk",
            "website": "https://www.ntcpvtltd.pk",
            "address": "23-B, Gulberg III, Lahore, Punjab, Pakistan",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    # ── Sub-organization: Manufacturing Division ──────────────────
    mfg_org, created = Organization.objects.update_or_create(
        code="NTC-MFG",
        defaults={
            "parent": main_org,
            "title": "NTC Manufacturing Division",
            "phone": "+92-41-23456789",
            "cell": "+92-300-8421235",
            "email": "mfg@ntcpvtltd.pk",
            "address": "Kot Lakhpat Industrial Estate, Lahore",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    # ── Sub-organization: Trading Division ────────────────────────
    trading_org, created = Organization.objects.update_or_create(
        code="NTC-TRD",
        defaults={
            "parent": main_org,
            "title": "NTC Trading Division",
            "phone": "+92-21-32561890",
            "cell": "+92-300-8421236",
            "email": "trading@ntcpvtltd.pk",
            "address": "SITE Industrial Area, Karachi",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    # ── Branches ──────────────────────────────────────────────────
    lhe = City.objects.filter(code="LHE").first() or City.objects.filter(title__icontains="Lahore").first() or City.objects.order_by("title").first()
    khi = City.objects.filter(code="KHI").first() or City.objects.filter(title__icontains="Karachi").first() or lhe
    isb = City.objects.filter(code="ISB").first() or City.objects.filter(title__icontains="Islamabad").first() or lhe
    fsd = City.objects.filter(code="FSD").first() or City.objects.filter(title__icontains="Faisalabad").first() or lhe

    branches = [
        {
            "code": "HO-LHE",
            "defaults": {
                "organization": main_org,
                "city": lhe,
                "title": "Head Office — Lahore",
                "address": "23-B, Gulberg III, Lahore, Punjab 54660",
                "phone": "+92-42-35761234",
                "email": "headoffice@ntcpvtltd.pk",
                "fax": "+92-42-35761235",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "RO-KHI",
            "defaults": {
                "organization": main_org,
                "city": khi,
                "title": "Regional Office — Karachi",
                "address": "Plot 12, S.I.T.E., Karachi, Sindh 75700",
                "phone": "+92-21-32561890",
                "email": "karachi@ntcpvtltd.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "RO-ISB",
            "defaults": {
                "organization": main_org,
                "city": isb,
                "title": "Regional Office — Islamabad",
                "address": "F-8 Markaz, Islamabad 44000",
                "phone": "+92-51-28234567",
                "email": "islamabad@ntcpvtltd.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "FACTORY",
            "defaults": {
                "organization": mfg_org,
                "city": lhe,
                "title": "Factory — Kot Lakhpat",
                "address": "Kot Lakhpat Industrial Estate, Lahore",
                "phone": "+92-42-35128890",
                "email": "factory@ntcpvtltd.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "WH-FSD",
            "defaults": {
                "organization": mfg_org,
                "city": fsd,
                "title": "Warehouse — Faisalabad",
                "address": "Jaranwala Road, Faisalabad, Punjab",
                "phone": "+92-41-26789012",
                "email": "fsd.warehouse@ntcpvtltd.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "SHOWROOM-KHI",
            "defaults": {
                "organization": trading_org,
                "city": khi,
                "title": "Showroom — Karachi",
                "address": "Bolton Market, Karachi",
                "phone": "+92-21-32145678",
                "email": "showroom.khi@ntcpvtltd.pk",
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
