from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import InventoryClass

INVENTORY_CLASSES = [
    ("PKG-THR", "Packing — Thread, Tags & Labels"),
    ("MRO-MILL", "Spares — Milling Machinery"),
    ("MRO-SIEVE", "Spares — Sieves & Sifter Cloth"),
    ("MRO-ROLL", "Spares — Roller Mill"),
    ("MRO-BELT", "Spares — Belts, Bearings & Pulleys"),
    ("MRO-ELC", "Spares — Electrical & Motors"),
    ("MRO-WKS", "Workshop — Tools & Welding"),
    ("CS-LUB", "Consumables — Lubricants & Grease"),
    ("CS-FUEL", "Consumables — Fuel"),
    ("CS-LAB", "Consumables — Laboratory & Testing"),
    ("CS-CLN", "Consumables — Cleaning & Pest Control"),
    ("CS-PPE", "Consumables — Safety & PPE"),
    ("CS-OFF", "Consumables — Office & Stationery"),
    ("FA-MCH", "Fixed Assets — Plant & Machinery"),
    ("FA-VEH", "Fixed Assets — Vehicles"),
    ("FA-BLD", "Fixed Assets — Buildings & Silos"),
    ("SVC-MNT", "Services — Repair & Maintenance"),
    ("SVC-TRN", "Services — Transport & Freight"),
]


def seed_inventory_classes() -> int:
    created_count = 0
    for code, title in INVENTORY_CLASSES:
        _, created = InventoryClass.objects.update_or_create(
            class_code=code,
            defaults={"title": title, "status": STATUS_ACTIVE},
        )
        created_count += int(created)
    return created_count
