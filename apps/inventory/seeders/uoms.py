from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import UOM


UOMS = [
    ("EA", "Each"),
    ("PC", "Piece"),
    ("PR", "Pair"),
    ("SET", "Set"),
    ("PK", "Pack"),
    ("BX", "Box"),
    ("BDL", "Bundle"),
    ("ROLL", "Roll"),
    ("BAG", "Bag"),
    ("KG", "Kilogram"),
    ("MUND", "Mund (40 kg)"),
    ("TON", "Metric Ton"),
    ("G", "Gram"),
    ("L", "Litre"),
    ("ML", "Millilitre"),
    ("DRUM", "Drum"),
    ("M", "Metre"),
    ("FT", "Foot"),
    ("HR", "Hour"),
    ("DAY", "Day"),
    ("TRIP", "Trip"),
]


def seed_uoms() -> int:
    created_count = 0
    for code, title in UOMS:
        _, created = UOM.objects.update_or_create(
            code=code,
            defaults={"title": title, "status": STATUS_ACTIVE},
        )
        created_count += int(created)
    return created_count
