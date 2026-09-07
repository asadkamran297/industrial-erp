"""WG-62, the mill's own sample run, and the products it needed.

The wheat and the sacks are opened into stock first: a grinding voucher that
consumed stock nobody had would leave the ledger negative on the day the module
was installed, and every stock screen would open on a number that needs
explaining.

Re-runnable: the voucher is matched on its number, so seeding twice leaves one.
"""

from datetime import date, time
from decimal import Decimal

from apps.core.constants import (
    PRD_LEDGER_OPENING,
    PRD_LEVEL_ITEM,
    PRD_SPEC_BYPRODUCT,
    PRD_SPEC_FINISH_ITEM,
    PRD_UNIT_KG,
    PRD_UNIT_PIECE,
    STATUS_ACTIVE,
)
from apps.godowns.models import Godown
from apps.products.models import FinishBardanaLink, ProductLedger, ProductNode

from .. import services
from ..models import GrindingVoucher

VOUCHER_NO = "WG-0062"
VOUCHER_DATE = date(2026, 8, 31)

# The sample run's products that the base product seed does not carry.
# (code, name, specification, unit, unit weight, bag code)
EXTRA_ITEMS = (
    ("02-01-003", "Atta Zafaran 15 kg", PRD_SPEC_FINISH_ITEM, PRD_UNIT_PIECE, 15, "03-02-003"),
    ("02-01-004", "Atta Diamond 20 kg", PRD_SPEC_FINISH_ITEM, PRD_UNIT_PIECE, 20, "03-02-004"),
    ("02-04-001", "Fine Diamond 80 kg", PRD_SPEC_FINISH_ITEM, PRD_UNIT_PIECE, 80, "03-02-008"),
)

# (product code, quantity, pack code)
OUTPUT_LINES = (
    ("02-01-003", Decimal("1752"), "03-02-003"),
    ("02-01-004", Decimal("320"), "03-02-004"),
    ("02-03-012", Decimal("1218"), "03-02-007"),
    # Loose maida: weighed out in kg, into no sack at all.
    ("02-03-013", Decimal("28200"), None),
    ("02-04-001", Decimal("244"), "03-02-008"),
    ("02-06-002", Decimal("104"), "03-02-011"),
)

WHEAT_CODE = "01-01-001"
BAG_CODE = "03-01-001"
DISPOSAL_WHEAT = Decimal("254166")
DISPOSAL_BAGS = Decimal("5000")


def _node(code: str) -> ProductNode | None:
    return ProductNode.objects.filter(complete_code=code).first()


def _ensure_extra_items() -> int:
    created = 0
    for code, name, specification, unit, unit_weight, bag_code in EXTRA_ITEMS:
        group_segment, sub_segment, item_segment = code.split("-")
        parent = _node(f"{group_segment}-{sub_segment}")
        if parent is None:
            continue
        node, made = ProductNode.objects.get_or_create(
            complete_code=code,
            defaults={
                "parent": parent,
                "level": PRD_LEVEL_ITEM,
                "code_segment": item_segment,
                "name": name,
                "specification": specification,
                "unit": unit,
                "unit_weight": unit_weight,
                "status": STATUS_ACTIVE,
                "starting_date": VOUCHER_DATE,
            },
        )
        created += int(made)
        bag = _node(bag_code)
        if bag:
            _, linked = FinishBardanaLink.objects.get_or_create(finish_item=node, defaults={"bag_item": bag})
            created += int(linked)
    return created


def _open_stock(product: ProductNode, quantity: Decimal, godown: Godown) -> int:
    """Enough on hand the day before the run for the run to be possible."""
    if product is None:
        return 0
    existing = ProductLedger.objects.filter(product=product, source=PRD_LEDGER_OPENING).first()
    if existing:
        return 0
    ProductLedger.objects.create(
        product=product,
        entry_date=VOUCHER_DATE,
        source=PRD_LEDGER_OPENING,
        reference="OPENING",
        quantity=quantity,
        remarks="Seeded opening for the sample grinding run",
        godown=godown,
        # Wheat received in this sack, so grinding defaults to it rather than
        # re-deriving one from the item master.
        bardana_item=_node(BAG_CODE) if product.complete_code == WHEAT_CODE else None,
    )
    return 1


def seed_grinding() -> int:
    created = _ensure_extra_items()

    godown = Godown.objects.filter(code="MG").first() or Godown.objects.first()
    wheat, bag = _node(WHEAT_CODE), _node(BAG_CODE)
    if godown is None or wheat is None or bag is None:
        # Nothing to grind and nowhere to grind it: the product or godown seed
        # has not run yet.
        return created

    # The standard the sample run is measured against.
    if not wheat.standard_yield_percent:
        wheat.standard_yield_percent = Decimal("98.00")
        wheat.save(update_fields=["standard_yield_percent", "updated_at"])

    created += _open_stock(wheat, DISPOSAL_WHEAT, godown)
    created += _open_stock(bag, DISPOSAL_BAGS, godown)
    for _, quantity, pack_code in OUTPUT_LINES:
        if pack_code:
            created += _open_stock(_node(pack_code), quantity, godown)

    if GrindingVoucher.all_objects.filter(voucher_no=VOUCHER_NO).exists():
        return created

    voucher = GrindingVoucher(
        seq_num=62,
        voucher_no=VOUCHER_NO,
        date=VOUCHER_DATE,
        production_from=time(10, 49),
        production_to=time(10, 49),
        wheat_item=wheat,
        disposal_wheat=DISPOSAL_WHEAT,
        bag_item=bag,
        disposal_bag_qty=DISPOSAL_BAGS,
        godown=godown,
        issue_area="Main Godown",
        description="Seeded sample run.",
    )
    lines = []
    for product_code, quantity, pack_code in OUTPUT_LINES:
        product = _node(product_code)
        if product is None:
            continue
        pack = _node(pack_code) if pack_code else None
        lines.append(
            {
                "product": product,
                "quantity": quantity,
                "unit_weight": product.effective_unit_weight,
                "pack_product": pack,
                "pack_qty": quantity if pack else Decimal("0"),
            }
        )
    services.save_grinding_voucher(voucher, lines)
    return created + 1
