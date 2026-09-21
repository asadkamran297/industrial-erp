from decimal import Decimal

from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import InventoryClass, InventoryItem, UOM


ITEMS = [
    ("Bag Stitching Thread Cone 2 kg", "PKG-THR", "PC", 950),
    ("Bag Closer Needle DR-H30", "PKG-THR", "PC", 120),
    ("Printed Brand Label Roll 1000", "PKG-THR", "ROLL", 1400),
    ("Roller Mill Roll 250x1000 Fluted", "MRO-ROLL", "PR", 185000),
    ("Roller Mill Roll 250x1000 Smooth", "MRO-ROLL", "PR", 165000),
    ("Roll Feeder Gate Assembly", "MRO-ROLL", "EA", 28000),
    ("Roller Mill Scraper Blade", "MRO-ROLL", "EA", 4200),
    ("Sifter Cloth Nylon 9XX", "MRO-SIEVE", "M", 2800),
    ("Sifter Cloth Nylon 10XX", "MRO-SIEVE", "M", 2950),
    ("Sifter Cloth Nylon 12XX", "MRO-SIEVE", "M", 3100),
    ("Sifter Frame Wooden 640x640", "MRO-SIEVE", "EA", 6500),
    ("Purifier Sieve 30 Mesh", "MRO-SIEVE", "EA", 3800),
    ("Sieve Cleaner Cotton Pad", "MRO-SIEVE", "PK", 850),
    ("Bran Finisher Beater Bar", "MRO-MILL", "EA", 5600),
    ("Pneumatic Cyclone Airlock Rotor", "MRO-MILL", "EA", 32000),
    ("Bucket Elevator Cup Steel 6 in", "MRO-MILL", "EA", 240),
    ("Elevator Belt 6 in Rubber", "MRO-MILL", "M", 1850),
    ("Screw Conveyor Flight 200 mm", "MRO-MILL", "EA", 12000),
    ("Dampener Water Nozzle", "MRO-MILL", "EA", 1800),
    ("Destoner Deck Screen", "MRO-MILL", "EA", 9500),
    ("Magnet Separator Plate", "MRO-MILL", "EA", 7200),
    ("V-Belt B-85", "MRO-BELT", "EA", 780),
    ("V-Belt B-110", "MRO-BELT", "EA", 920),
    ("V-Belt C-120", "MRO-BELT", "EA", 1450),
    ("Ball Bearing 6208 ZZ", "MRO-BELT", "EA", 650),
    ("Ball Bearing 6310", "MRO-BELT", "EA", 1900),
    ("Pillow Block Bearing UCP 208", "MRO-BELT", "EA", 1650),
    ("Cast Iron Pulley 12 in B-Groove", "MRO-BELT", "EA", 4800),
    ("Electric Motor 30 HP 1440 rpm", "MRO-ELC", "EA", 185000),
    ("Electric Motor 10 HP 1440 rpm", "MRO-ELC", "EA", 68000),
    ("Motor Starter DOL 30 HP", "MRO-ELC", "EA", 22000),
    ("Contactor 65A 3-Pole", "MRO-ELC", "EA", 6500),
    ("MCB 63A Triple Pole", "MRO-ELC", "EA", 3200),
    ("Cable 4-Core 16 mm", "MRO-ELC", "M", 1450),
    ("LED Flood Light 100 W", "MRO-ELC", "EA", 4200),
    ("Welding Electrode E6013 3.2 mm 5 kg", "MRO-WKS", "PK", 1250),
    ("Grinding Disc 7 in", "MRO-WKS", "EA", 180),
    ("Cutting Disc 4 in", "MRO-WKS", "EA", 45),
    ("MS Flat Bar 2x1/4 in 20 ft", "MRO-WKS", "EA", 3800),
    ("Gear Oil EP-90 20 L", "CS-LUB", "DRUM", 14500),
    ("Bearing Grease MP-3 15 kg", "CS-LUB", "DRUM", 9800),
    ("Compressor Oil 20 L", "CS-LUB", "DRUM", 12500),
    ("Hydraulic Oil 68 20 L", "CS-LUB", "DRUM", 13200),
    ("Diesel HSD", "CS-FUEL", "L", 305),
    ("Petrol", "CS-FUEL", "L", 290),
    ("Moisture Meter Calibration Sample", "CS-LAB", "PK", 2500),
    ("Gluten Washing Solution 1 L", "CS-LAB", "L", 1800),
    ("Filter Paper Whatman No.1 100 pcs", "CS-LAB", "BX", 1450),
    ("Petri Dish Glass 90 mm", "CS-LAB", "PC", 120),
    ("Lab Sieve 212 micron", "CS-LAB", "EA", 6800),
    ("Aluminium Phosphide Fumigation Tablets 1 kg", "CS-CLN", "PK", 3200),
    ("Insecticide Spray 5 L", "CS-CLN", "L", 2400),
    ("Rodent Bait Station", "CS-CLN", "EA", 850),
    ("Floor Broom Coconut", "CS-CLN", "EA", 180),
    ("Detergent Powder 3 kg", "CS-CLN", "PK", 1450),
    ("Dust Mask N95", "CS-PPE", "BX", 1200),
    ("Ear Plugs Foam", "CS-PPE", "PR", 40),
    ("Safety Shoes Steel Toe", "CS-PPE", "PR", 2800),
    ("Cotton Gloves", "CS-PPE", "PR", 60),
    ("Safety Helmet", "CS-PPE", "EA", 350),
    ("Gate Pass Book 100 Leaves", "CS-OFF", "EA", 220),
    ("Weighbridge Slip Roll", "CS-OFF", "ROLL", 380),
    ("A4 Paper 80 GSM Ream", "CS-OFF", "PK", 850),
    ("Ball Point Pen Box 50", "CS-OFF", "BX", 380),
    ("Register 200 Pages", "CS-OFF", "EA", 260),
]


def seed_items() -> int:
    uom_cache = {u.code: u for u in UOM.objects.all()}
    class_cache = {c.class_code: c for c in InventoryClass.objects.all()}
    created_count = 0
    for item_name, class_code, uom_code, price in ITEMS:
        uom = uom_cache.get(uom_code)
        item_class = class_cache.get(class_code)
        if not uom or not item_class:
            continue
        _, created = InventoryItem.objects.get_or_create(
            item_name=item_name,
            defaults={
                "uom": uom,
                "item_class": item_class,
                "price": Decimal(str(price)),
                "status": STATUS_ACTIVE,
                "imported": "L",
                "inventory": "I",
            },
        )
        created_count += int(created)
    return created_count
