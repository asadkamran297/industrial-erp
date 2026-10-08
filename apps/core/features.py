"""General Settings feature switches: the one door every screen and service asks.

Stored as one JSON record in ``SystemConfiguration`` (key ``core.features``),
the same store the purchase form layouts use, so turning a feature off needs no
migration. A switched-off feature disappears from forms, lists, prints and
exports, and services save it as zero; documents already posted keep their
figures.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.configurations.models import SystemConfiguration

SETTING_KEY = "core.features"

PURCHASE_TAX = "purchase_tax"
SALES_TAX = "sales_tax"
PURCHASE_DISCOUNT = "purchase_discount"
SALES_DISCOUNT = "sales_discount"
PURCHASE_FREIGHT = "purchase_freight"
WHEAT_WITHHOLDING = "wheat_withholding"
WHEAT_BROKERAGE = "wheat_brokerage"
SERVICES = "services"


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    group: str
    default: bool = True


FEATURES: tuple[Feature, ...] = (
    Feature(PURCHASE_TAX, "Sales tax", "Purchase"),
    Feature(PURCHASE_DISCOUNT, "Discount", "Purchase"),
    Feature(PURCHASE_FREIGHT, "Freight", "Purchase"),
    Feature(WHEAT_WITHHOLDING, "Withholding tax", "Wheat"),
    Feature(WHEAT_BROKERAGE, "Brokerage", "Wheat"),
    Feature(SALES_TAX, "Sales tax", "Sales"),
    Feature(SALES_DISCOUNT, "Discount", "Sales"),
    Feature(SERVICES, "Services", "Items", default=False),
)
FEATURE_MAP = {feature.key: feature for feature in FEATURES}

ZERO = Decimal("0.00")


def current() -> dict:
    """``{key: on}`` for every feature, defaults filled in."""
    row = SystemConfiguration.objects.filter(key=SETTING_KEY).first()
    stored = row.value if row and isinstance(row.value, dict) else {}
    return {feature.key: bool(stored.get(feature.key, feature.default)) for feature in FEATURES}


def enabled(key: str, flags: dict | None = None) -> bool:
    return (flags or current())[key]


def zero_unless(key: str, value, flags: dict | None = None):
    """``value`` when the feature is on, else zero."""
    return value if enabled(key, flags) else ZERO


def save(on: set[str]) -> None:
    SystemConfiguration.objects.update_or_create(
        key=SETTING_KEY, defaults={"value": {feature.key: feature.key in on for feature in FEATURES}},
    )


def grouped(flags: dict | None = None) -> list[tuple[str, list[dict]]]:
    flags = flags or current()
    groups: dict[str, list[dict]] = {}
    for feature in FEATURES:
        groups.setdefault(feature.group, []).append({"key": feature.key, "label": feature.label, "on": flags[feature.key]})
    return list(groups.items())
