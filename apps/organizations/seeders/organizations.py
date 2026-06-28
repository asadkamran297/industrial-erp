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

    lhe = _city("LHE", "Lahore")
    khi = _city("KHI", "Karachi", lhe)
    isb = _city("ISB", "Islamabad", lhe)
    fsd = _city("FSD", "Faisalabad", lhe)
    mul = _city("MUL", "Multan", lhe)
    pew = _city("PEW", "Peshawar", lhe)

    # ══════════════════════════════════════════════════════════════
    # GROUP HOLDING COMPANY
    # ══════════════════════════════════════════════════════════════
    group, created = Organization.objects.update_or_create(
        code="IEMG",
        defaults={
            "title": "Industrial ERP Manufacturing Group (Pvt) Ltd",
            "logo": "https://placehold.co/200x60/1e3a5f/ffffff?text=IEMG+Group",
            "phone": "+92-42-35761000",
            "cell": "+92-300-8500000",
            "fax": "+92-42-35761001",
            "email": "group@iemg.pk",
            "website": "https://www.iemg.pk",
            "address": "1-A, Main Boulevard, Gulberg V, Lahore, Punjab 54660, Pakistan",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    # ── Sub-org 1: Steel & Metals Division ───────────────────────
    steel_div, created = Organization.objects.update_or_create(
        code="IEMG-STL",
        defaults={
            "parent": group,
            "title": "IEMG Steel & Metals Division",
            "logo": "https://placehold.co/200x60/374151/f9fafb?text=IEMG+Steel",
            "phone": "+92-42-36501234",
            "cell": "+92-300-8500011",
            "email": "steel@iemg.pk",
            "address": "Kot Lakhpat Industrial Estate, Lahore",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    # ── Sub-org 2: Chemical & Polymer Division ────────────────────
    chem_div, created = Organization.objects.update_or_create(
        code="IEMG-CHM",
        defaults={
            "parent": group,
            "title": "IEMG Chemical & Polymer Division",
            "logo": "https://placehold.co/200x60/065f46/d1fae5?text=IEMG+Chemical",
            "phone": "+92-21-32890123",
            "cell": "+92-300-8500022",
            "email": "chemical@iemg.pk",
            "address": "S.I.T.E. Industrial Area, Karachi, Sindh",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    # ── Sub-org 3: Textile Division ───────────────────────────────
    textile_div, created = Organization.objects.update_or_create(
        code="IEMG-TEX",
        defaults={
            "parent": group,
            "title": "IEMG Textile Division",
            "logo": "https://placehold.co/200x60/4c1d95/ede9fe?text=IEMG+Textile",
            "phone": "+92-41-28901234",
            "cell": "+92-300-8500033",
            "email": "textile@iemg.pk",
            "address": "Sammundri Road Industrial Zone, Faisalabad, Punjab",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    # ── Sub-org 4: Trading & Distribution ────────────────────────
    trading_div, created = Organization.objects.update_or_create(
        code="IEMG-TRD",
        defaults={
            "parent": group,
            "title": "IEMG Trading & Distribution (Pvt) Ltd",
            "logo": "https://placehold.co/200x60/92400e/fef3c7?text=IEMG+Trading",
            "phone": "+92-51-28345678",
            "cell": "+92-300-8500044",
            "email": "trading@iemg.pk",
            "address": "G-9 Markaz, Islamabad Capital Territory",
            "status": STATUS_ACTIVE,
        },
    )
    created_count += int(created)

    # ══════════════════════════════════════════════════════════════
    # ORIGINAL NTC GROUP (kept from previous seed)
    # ══════════════════════════════════════════════════════════════
    main_org, created = Organization.objects.update_or_create(
        code="MAIN",
        defaults={
            "title": "National Trading Corporation (Pvt) Ltd",
            "logo": "https://placehold.co/200x60/7a0000/ffffff?text=NTC+Pvt+Ltd",
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

    # ══════════════════════════════════════════════════════════════
    # BRANCHES
    # ══════════════════════════════════════════════════════════════
    branches = [
        # ── IEMG Group Branches ───────────────────────────────────
        {
            "code": "IEMG-HO",
            "defaults": {
                "organization": group,
                "city": lhe,
                "title": "IEMG Group Head Office — Lahore",
                "address": "1-A, Main Boulevard, Gulberg V, Lahore 54660",
                "phone": "+92-42-35761000",
                "fax": "+92-42-35761001",
                "email": "ho@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "IEMG-RO-KHI",
            "defaults": {
                "organization": group,
                "city": khi,
                "title": "IEMG Regional Office — Karachi",
                "address": "Plot 47, Korangi Industrial Area, Karachi 74900",
                "phone": "+92-21-35112345",
                "email": "karachi@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "IEMG-RO-ISB",
            "defaults": {
                "organization": group,
                "city": isb,
                "title": "IEMG Regional Office — Islamabad",
                "address": "G-9 Markaz, Islamabad 44000",
                "phone": "+92-51-28345678",
                "email": "islamabad@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        # ── Steel Division Branches ───────────────────────────────
        {
            "code": "IEMG-STL-LHE",
            "defaults": {
                "organization": steel_div,
                "city": lhe,
                "title": "Steel Plant — Kot Lakhpat, Lahore",
                "address": "Kot Lakhpat Industrial Estate, Lahore",
                "phone": "+92-42-36501234",
                "email": "plant.lhe@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "IEMG-STL-WH",
            "defaults": {
                "organization": steel_div,
                "city": khi,
                "title": "Steel Warehouse — Port Qasim, Karachi",
                "address": "Bin Qasim Industrial Zone, Karachi",
                "phone": "+92-21-34761234",
                "email": "warehouse.khi@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        # ── Chemical Division Branches ────────────────────────────
        {
            "code": "IEMG-CHM-KHI",
            "defaults": {
                "organization": chem_div,
                "city": khi,
                "title": "Chemical Plant — S.I.T.E., Karachi",
                "address": "S.I.T.E. Superhighway, Karachi 75700",
                "phone": "+92-21-32890123",
                "email": "plant.khi@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "IEMG-CHM-MUL",
            "defaults": {
                "organization": chem_div,
                "city": mul,
                "title": "Chemical Distribution — Multan",
                "address": "Bosan Road Industrial Estate, Multan",
                "phone": "+92-61-45234567",
                "email": "multan@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        # ── Textile Division Branches ─────────────────────────────
        {
            "code": "IEMG-TEX-FSD",
            "defaults": {
                "organization": textile_div,
                "city": fsd,
                "title": "Textile Mill — Sammundri Road, Faisalabad",
                "address": "Sammundri Road Industrial Zone, Faisalabad",
                "phone": "+92-41-28901234",
                "email": "mill.fsd@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "IEMG-TEX-LHE",
            "defaults": {
                "organization": textile_div,
                "city": lhe,
                "title": "Textile Showroom — Lahore",
                "address": "Liberty Market, Gulberg III, Lahore",
                "phone": "+92-42-35123456",
                "email": "showroom.lhe@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        # ── Trading Division Branches ─────────────────────────────
        {
            "code": "IEMG-TRD-ISB",
            "defaults": {
                "organization": trading_div,
                "city": isb,
                "title": "Trading Office — Islamabad",
                "address": "Blue Area, Islamabad 44000",
                "phone": "+92-51-28901234",
                "email": "trade.isb@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        {
            "code": "IEMG-TRD-PEW",
            "defaults": {
                "organization": trading_div,
                "city": pew,
                "title": "Trading Office — Peshawar",
                "address": "Hayatabad Industrial Estate, Peshawar",
                "phone": "+92-91-23456789",
                "email": "trade.pew@iemg.pk",
                "status": STATUS_ACTIVE,
            },
        },
        # ── NTC Branches ──────────────────────────────────────────
        {
            "code": "HO-LHE",
            "defaults": {
                "organization": main_org,
                "city": lhe,
                "title": "Head Office — Lahore",
                "address": "23-B, Gulberg III, Lahore, Punjab 54660",
                "phone": "+92-42-35761234",
                "fax": "+92-42-35761235",
                "email": "headoffice@ntcpvtltd.pk",
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
