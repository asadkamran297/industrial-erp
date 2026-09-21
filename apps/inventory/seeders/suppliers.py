from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import Supplier

SUPPLIERS = [
    ("SUP001", "M. Din & Co (Arhti)", "SGD", "Ghalla Mandi, Sargodha", "048-3712345", "mdin.arhti@gmail.com", "1234567-1"),
    ("SUP002", "Haji Rafique Grain Traders", "FSD", "Ghalla Mandi, Jaranwala", "041-4312890", "rafique.grains@gmail.com", "2345678-2"),
    ("SUP003", "Chaudhry Nazir Commission Shop", "SGD", "Bhalwal Grain Market", "048-6642345", "", "3456789-3"),
    ("SUP004", "Malik Wheat Suppliers", "MUX", "Grain Market, Khanewal Road, Multan", "061-4512340", "malikwheat@gmail.com", "4567890-4"),
    ("SUP005", "Ashraf Sons Beopar (Sahiwal)", "LHE", "Ghalla Mandi, Sahiwal", "040-4512345", "ashrafsons.sahiwal@gmail.com", "5678901-5"),
    ("SUP006", "Okara Grain Merchants", "LHE", "Grain Market, Okara", "044-2512890", "okaragrain@gmail.com", "6789012-6"),
    ("SUP007", "Rana Brothers Arhti", "GJW", "Ghalla Mandi, Hafizabad", "0547-523456", "", "7890123-7"),
    ("SUP008", "Bahawalpur Wheat Depot", "MUX", "Ghalla Mandi, Bahawalpur", "062-2884567", "bwp.wheat@gmail.com", "8901234-8"),
    ("SUP009", "Punjab Food Department — Sargodha", "SGD", "District Food Controller Office, Sargodha", "048-9230123", "dfc.sargodha@food.punjab.gov.pk", "9012345-9"),
    ("SUP010", "PASSCO Regional Office Lahore", "LHE", "Muslim Town, Lahore", "042-99230456", "lahore@passco.gov.pk", "0123456-0"),
    ("SUP011", "Layyah Growers Association", "MUX", "Chowk Azam, Layyah", "0606-412345", "", "1122334-4"),
    ("SUP012", "Khushab Kisan Arhti", "SGD", "Ghalla Mandi, Jauharabad", "0454-723456", "", "2233445-5"),
    ("SUP013", "Ravi Bardana Traders", "LHE", "Badami Bagh, Lahore", "042-37123456", "ravibardana@gmail.com", "3344556-6"),
    ("SUP014", "Al-Karam Polypropylene Bags", "FSD", "Sitiana Road, Faisalabad", "041-2612345", "sales@alkarambags.pk", "4455667-7"),
    ("SUP015", "Faisalabad Jute Mills", "FSD", "Jhang Road, Faisalabad", "041-2412345", "info@fsdjute.pk", "5566778-8"),
    ("SUP016", "Sitara Packaging (Woven Sacks)", "FSD", "Khurrianwala, Faisalabad", "041-4512345", "sacks@sitarapack.pk", "6677889-9"),
    ("SUP017", "Buhler Pakistan (Roller Mill Spares)", "LHE", "Gulberg III, Lahore", "042-35761234", "spares@buhler.pk", "7788990-0"),
    ("SUP018", "Milltec Engineering Works", "GJW", "GT Road, Gujranwala", "055-3812345", "milltec.gjw@gmail.com", "8899001-1"),
    ("SUP019", "Roller Grinding Service Co", "LHE", "Sheikhupura Road, Lahore", "042-37912345", "", "9900112-2"),
    ("SUP020", "National Sieve Cloth Traders", "LHE", "Brandreth Road, Lahore", "042-37631234", "sievecloth@gmail.com", "1234509-8"),
    ("SUP021", "Bilal Electric (Motors)", "LHE", "Hall Road, Lahore", "042-37312345", "bilalelectric@gmail.com", "2345610-9"),
    ("SUP022", "SKF Bearing House", "LHE", "McLeod Road, Lahore", "042-36312345", "skfhouse@gmail.com", "3456721-0"),
    ("SUP023", "Fenner V-Belt Distributors", "GJW", "Sialkot Bypass, Gujranwala", "055-4212345", "", "4567832-1"),
    ("SUP024", "Shell Lubricants — Punjab Agency", "LHE", "Ferozepur Road, Lahore", "042-35112345", "lubes@shellagency.pk", "5678943-2"),
    ("SUP025", "PSO Petrol Pump Mill Road", "SGD", "Mill Road, Sargodha", "048-3223456", "", "6789054-3"),
    ("SUP026", "Ittehad Lab Chemicals", "LHE", "Anarkali, Lahore", "042-37212345", "ittehadlab@gmail.com", "7890165-4"),
    ("SUP027", "Pak Fumigation Services", "FSD", "Peoples Colony, Faisalabad", "041-8512345", "pakfumigation@gmail.com", "8901276-5"),
    ("SUP028", "Punjab Safety Store", "LHE", "Nila Gumbad, Lahore", "042-37112345", "", "9012387-6"),
    ("SUP029", "Sargodha Stationers", "SGD", "Katchery Bazar, Sargodha", "048-3712000", "", "0123498-7"),
    ("SUP030", "Goods Transport Co (Wheat Carriage)", "SGD", "Truck Adda, Sargodha", "048-3745678", "", "1234560-0"),
]

WHEAT_SUPPLIER_CODES = tuple(f"SUP{n:03d}" for n in range(1, 13))
BARDANA_SUPPLIER_CODES = ("SUP013", "SUP014", "SUP015", "SUP016")
STORES_SUPPLIER_CODES = tuple(f"SUP{n:03d}" for n in range(17, 30))


def seed_suppliers() -> int:
    cities = {city.code: city for city in City.objects.all()}
    created_count = 0
    for code, name, city_code, addr1, tel1, email, ntn in SUPPLIERS:
        _, created = Supplier.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "addr1": addr1,
                "city": cities.get(city_code),
                "tel1": tel1,
                "email": email,
                "ntn_number": ntn,
                "status": STATUS_ACTIVE,
            },
        )
        created_count += int(created)
    return created_count
