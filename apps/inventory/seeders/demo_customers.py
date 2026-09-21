"""Demo customers: the atta dealers, bakeries and depots the mill sells to."""

from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import Customer

CUSTOMERS = [
    ("Haji Karim Atta Dealer", "SGD", "Block 14, Sargodha"),
    ("Sheikh Brothers Flour Agency", "LHE", "Badami Bagh, Lahore"),
    ("Bismillah Karyana Store", "SGD", "Satellite Town, Sargodha"),
    ("Punjab Bakers", "LHE", "Main Market Gulberg, Lahore"),
    ("Al-Madina Naan Shop", "SGD", "Katchery Bazar, Sargodha"),
    ("Chaudhry Traders (Atta Wholesale)", "FSD", "Ghalla Mandi, Faisalabad"),
    ("Jugnoo Flour Distributors", "FSD", "Jhang Road, Faisalabad"),
    ("Gourmet Bakers & Sweets", "LHE", "Johar Town, Lahore"),
    ("Sunrise Bakery", "SGD", "University Road, Sargodha"),
    ("Metro Cash & Carry", "LHE", "Thokar Niaz Baig, Lahore"),
    ("Rehmat Karyana & General Store", "GJW", "Model Town, Gujranwala"),
    ("Shahi Tandoor", "SGD", "Mall Road, Sargodha"),
    ("Malik Flour Agency", "MUX", "Grain Market, Multan"),
    ("Data Bakers", "LHE", "Samanabad, Lahore"),
    ("Ittefaq Atta Depot", "SKT", "Kutchery Road, Sialkot"),
    ("Rana Feed Mills (Bran Buyer)", "SGD", "Lahore Road, Sargodha"),
    ("Sadiq Poultry Feeds (Bran Buyer)", "RWP", "Chakri Road, Rawalpindi"),
    ("Cakes & Bakes", "LHE", "DHA Phase 4, Lahore"),
    ("Khan Baba Restaurant", "PEW", "University Road, Peshawar"),
    ("Imtiaz Super Market", "KHI", "Gulshan-e-Iqbal, Karachi"),
    ("Aziz Karyana Merchant", "SGD", "Bhalwal Road, Sargodha"),
    ("Al-Fatah Departmental Store", "LHE", "Liberty Market, Lahore"),
    ("Noor Flour Agency", "HYD", "Latifabad, Hyderabad"),
    ("Mian Ji Sweets & Bakers", "GJW", "Satellite Town, Gujranwala"),
    ("Shan Tandoor & Naan", "FSD", "D-Ground, Faisalabad"),
    ("Pak Army CSD Store", "RWP", "Saddar, Rawalpindi"),
    ("Utility Stores Corporation — Sargodha", "SGD", "Block 5, Sargodha"),
    ("Ravi Feed Industries (Bran Buyer)", "LHE", "Sheikhupura Road, Lahore"),
    ("Hamid Atta Chakki", "SGD", "Bhera Road, Sargodha"),
    ("Kohinoor Bakers", "SGD", "Jail Road, Sargodha"),
    ("Pakwan Catering Services", "LHE", "Garden Town, Lahore"),
    ("Chishti Flour Agency", "MUX", "Bosan Road, Multan"),
    ("Green Valley Super Store", "ISB", "F-10 Markaz, Islamabad"),
    ("Bhatti Karyana Store", "SGD", "Jhal Chakian, Sargodha"),
    ("Layyah Atta Depot", "MUX", "Chowk Azam, Layyah"),
    ("Bundu Khan Restaurant", "LHE", "MM Alam Road, Lahore"),
    ("Sitara Dairy & Feed (Bran Buyer)", "FSD", "Sammundri Road, Faisalabad"),
    ("Jalal Sons", "LHE", "Main Boulevard, Lahore"),
    ("Sarwar Flour Agency", "SGD", "Shaheenabad, Sargodha"),
    ("Tayyab Bakers", "SKT", "Paris Road, Sialkot"),
]


def seed_demo_customers(count: int = 50) -> int:
    """Create up to ``count`` customers on top of the default cash customer."""
    created_count = 0
    cities = {city.code: city for city in City.objects.all()}

    for index, (name, city_code, address) in enumerate(CUSTOMERS[:count], start=1):
        code = f"CUST{index:03d}"
        _, created = Customer.objects.get_or_create(
            customer_name=name,
            defaults={
                "customer_code": code,
                "customer_address": address,
                "customer_cell_no": f"+92-300-{4000000 + index}",
                "ntn_number": f"{1000000 + index}-{index % 10}",
                "city": cities.get(city_code),
                "status": STATUS_ACTIVE,
            },
        )
        created_count += int(created)

    return created_count
