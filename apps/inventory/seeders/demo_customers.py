"""Demo customers.

Master data seeded by ``seed`` stays minimal on purpose; this is the trading
book used to exercise the sales screens.
"""

from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import Customer

FIRST_NAMES = [
    "Ahsan", "Bilal", "Chaudhry", "Danish", "Ehsan", "Faisal", "Ghulam", "Hamza",
    "Imran", "Junaid", "Kamran", "Latif", "Mubashir", "Nadeem", "Owais", "Parvez",
    "Qasim", "Rashid", "Saleem", "Tariq", "Usman", "Waqar", "Yasir", "Zubair",
    "Adeel",
]
LAST_NAMES = [
    "Traders", "Enterprises", "Trading Co", "& Sons", "Brothers", "Corporation",
    "Distributors", "Agencies", "Impex", "Associates",
]
CITIES = ["Lahore", "Karachi", "Faisalabad", "Multan", "Rawalpindi", "Sialkot", "Peshawar", "Quetta"]
AREAS = [
    "Main Boulevard", "Industrial Estate", "Bazar Road", "Cantt Area", "Model Town",
    "Civil Lines", "Gulberg", "Saddar", "University Road", "Ring Road",
]


def seed_demo_customers(count: int = 50) -> int:
    """Create ``count`` trading customers on top of the default cash customer."""
    created_count = 0
    cities = {city.title: city for city in City.objects.all()}

    for index in range(1, count + 1):
        code = f"CUST{index:03d}"
        name = f"{FIRST_NAMES[(index - 1) % len(FIRST_NAMES)]} {LAST_NAMES[(index - 1) % len(LAST_NAMES)]}"
        city_name = CITIES[(index - 1) % len(CITIES)]
        # Keyed on the email, not the code: the first sale to a customer creates
        # their receivable in the chart of accounts and rewrites customer_code
        # to that chart code, so the code is not a stable key to reseed against.
        customer, created = Customer.objects.get_or_create(
            customer_email=f"{code.lower()}@example.test",
            defaults={
                "customer_code": code,
                "customer_name": name,
                "customer_address": f"{index} {AREAS[(index - 1) % len(AREAS)]}, {city_name}",
                "customer_cell_no": f"+92-300-{4000000 + index}",
                "ntn_number": f"{1000000 + index}-{index % 10}",
                "sale_tax_num": f"32-77-{5000 + index}",
                "city": cities.get(city_name),
                "status": STATUS_ACTIVE,
            },
        )
        created_count += int(created)

    return created_count
