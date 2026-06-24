from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import UOM


# International System of Units (SI) + common trade units of measure.
UOMS = [
    # Count
    ("EA", "Each"),
    ("PC", "Piece"),
    ("PR", "Pair"),
    ("DZ", "Dozen"),
    ("SET", "Set"),
    ("PK", "Pack"),
    ("BX", "Box"),
    ("CTN", "Carton"),
    ("DOS", "Dose"),
    ("AMP", "Ampoule"),
    ("VIAL", "Vial"),
    ("TAB", "Tablet"),
    ("CAP", "Capsule"),
    ("STRIP", "Strip"),
    ("ROLL", "Roll"),
    ("UNIT", "Unit"),
    # Mass / weight
    ("MG", "Milligram"),
    ("G", "Gram"),
    ("KG", "Kilogram"),
    ("TON", "Metric Ton"),
    ("LB", "Pound"),
    ("OZ", "Ounce"),
    # Volume
    ("ML", "Millilitre"),
    ("L", "Litre"),
    ("CC", "Cubic Centimetre"),
    ("M3", "Cubic Metre"),
    ("GAL", "Gallon"),
    # Length
    ("MM", "Millimetre"),
    ("CM", "Centimetre"),
    ("M", "Metre"),
    ("KM", "Kilometre"),
    ("IN", "Inch"),
    ("FT", "Foot"),
    ("YD", "Yard"),
    # Area
    ("M2", "Square Metre"),
    ("FT2", "Square Foot"),
    # Time
    ("HR", "Hour"),
    ("DAY", "Day"),
    ("MON", "Month"),
    # Misc
    ("PCT", "Percent"),
    ("BTL", "Bottle"),
    ("TUBE", "Tube"),
    ("BAG", "Bag"),
    ("SACHET", "Sachet"),
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
