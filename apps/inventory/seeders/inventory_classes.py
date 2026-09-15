from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import InventoryClass

INVENTORY_CLASSES = [
    ("RM-MET", "Raw Materials — Metals & Alloys"),
    ("RM-CHM", "Raw Materials — Chemicals"),
    ("RM-POL", "Raw Materials — Polymers & Plastics"),
    ("RM-TEX", "Raw Materials — Textiles & Fibres"),
    ("RM-WOD", "Raw Materials — Wood & Timber"),
    ("RM-AGR", "Raw Materials — Agricultural & Natural"),
    ("SFG-SUB", "Semi-finished — Sub-assemblies"),
    ("SFG-WIP", "Semi-finished — Work in Progress"),
    ("SFG-FAB", "Semi-finished — Fabricated Parts"),
    ("FG-MFG", "Finished Goods — Manufactured"),
    ("FG-TRD", "Finished Goods — Trading / Merchandise"),
    ("FG-PKG", "Finished Goods — Packaged Products"),
    ("CS-OFF", "Consumables — Office Supplies"),
    ("CS-PKG", "Consumables — Packaging Materials"),
    ("CS-LAB", "Consumables — Laboratory Supplies"),
    ("CS-CLN", "Consumables — Cleaning & Janitorial"),
    ("CS-PPE", "Consumables — Personal Protective Equipment"),
    ("CS-MED", "Consumables — Medical & Healthcare"),
    ("CS-FUL", "Consumables — Fuel & Lubricants"),
    ("MRO-SP",  "MRO — Spare Parts & Components"),
    ("MRO-ELC", "MRO — Electrical & Electronic"),
    ("MRO-MCH", "MRO — Mechanical & Hydraulic"),
    ("MRO-INS", "MRO — Instruments & Gauges"),
    ("MRO-FAC", "MRO — Facilities & Civil"),
    ("MRO-SAF", "MRO — Safety & Fire Protection"),
    ("FA-MCH",  "Fixed Assets — Machinery & Equipment"),
    ("FA-VEH",  "Fixed Assets — Vehicles & Transport"),
    ("FA-IT",   "Fixed Assets — IT & Communication"),
    ("FA-FRN",  "Fixed Assets — Furniture & Fixtures"),
    ("FA-BLD",  "Fixed Assets — Buildings & Infrastructure"),
    ("IT-HW",  "IT — Hardware & Peripherals"),
    ("IT-SW",  "IT — Software & Licenses"),
    ("IT-NET", "IT — Networking & Cables"),
    ("FB-DRY", "Food & Beverage — Dry Goods"),
    ("FB-FRS", "Food & Beverage — Fresh & Perishable"),
    ("FB-BEV", "Food & Beverage — Beverages"),
    ("PH-DRG", "Pharmaceutical — Drugs & Medicines"),
    ("PH-SUR", "Pharmaceutical — Surgical Items"),
    ("PH-DIA", "Pharmaceutical — Diagnostics"),
    ("CC-STR", "Construction — Structural Materials"),
    ("CC-FIN", "Construction — Finishing Materials"),
    ("CC-PLM", "Construction — Plumbing & Sanitary"),
    ("CC-ELC", "Construction — Electrical Fittings"),
    ("SVC-CON", "Services — Consultancy & Professional"),
    ("SVC-MNT", "Services — Maintenance & Repair"),
    ("SVC-TRN", "Services — Training & Development"),
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
