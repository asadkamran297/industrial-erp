"""Demo grinding runs over the wheat the demo purchases brought in.

Each run goes through ``save_grinding_voucher`` so the product ledger moves the
way it does from the screen: wheat and sacks out of the godown, atta, maida,
fine, suji and bran in.

Re-runnable: a run is matched on its number, so seeding twice leaves one.
"""

from datetime import time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core.constants import GODOWN_TYPE_MILL
from apps.godowns.models import Godown
from apps.products.models import ProductNode

from .. import services
from ..models import GrindingVoucher

WHEAT_CODES = ("01-01-001", "01-01-002", "01-02-001")
BAG_FOR_WHEAT = {"01-01-001": "03-01-001", "01-01-002": "03-01-002", "01-02-001": "03-01-003"}

# (product, share of the disposal wheat that comes out as this product, bag)
OUTPUT_MIX = (
    ("02-01-003", Decimal("0.28"), "03-02-003"),
    ("02-01-044", Decimal("0.12"), "03-02-002"),
    ("02-01-004", Decimal("0.10"), "03-02-004"),
    ("02-03-012", Decimal("0.14"), "03-02-007"),
    ("02-03-013", Decimal("0.04"), None),
    ("02-04-001", Decimal("0.08"), "03-02-008"),
    ("02-05-001", Decimal("0.02"), "03-02-007"),
    ("02-06-001", Decimal("0.16"), "03-02-009"),
    ("02-06-002", Decimal("0.03"), "03-02-011"),
    ("02-07-001", Decimal("0.01"), None),
)

SHIFTS = ((time(6, 0), time(14, 0)), (time(14, 0), time(22, 0)), (time(8, 0), time(20, 0)))
DISPOSAL_STEPS = (Decimal("48000"), Decimal("60000"), Decimal("72000"), Decimal("54000"), Decimal("66000"))


def _node(code: str) -> ProductNode | None:
    return ProductNode.objects.filter(complete_code=code).first()


def seed_grinding(count: int = 50, *, user=None) -> int:
    godown = Godown.objects.filter(godown_type=GODOWN_TYPE_MILL).first() or Godown.objects.first()
    wheats = [w for w in (_node(code) for code in WHEAT_CODES) if w is not None]
    if godown is None or not wheats:
        return 0

    for wheat in wheats:
        if not wheat.standard_yield_percent:
            wheat.standard_yield_percent = Decimal("98.00")
            wheat.save(update_fields=["standard_yield_percent", "updated_at"])

    today = timezone.localdate()
    created = 0
    for index in range(1, count + 1):
        voucher_no = f"WG-{index:04d}"
        if GrindingVoucher.all_objects.filter(voucher_no=voucher_no).exists():
            continue

        wheat = wheats[(index - 1) % len(wheats)]
        bag = _node(BAG_FOR_WHEAT[wheat.complete_code])
        disposal = DISPOSAL_STEPS[(index - 1) % len(DISPOSAL_STEPS)]
        shift_from, shift_to = SHIFTS[(index - 1) % len(SHIFTS)]
        run_date = today - timedelta(days=count - index)

        voucher = GrindingVoucher(
            seq_num=index,
            voucher_no=voucher_no,
            date=run_date,
            production_from=shift_from,
            production_to=shift_to,
            wheat_item=wheat,
            disposal_wheat=disposal,
            bag_item=bag,
            disposal_bag_qty=(disposal / Decimal("100")).quantize(Decimal("1")),
            godown=godown,
            issue_area=godown.name,
            description=f"Shift {((index - 1) % len(SHIFTS)) + 1}",
        )
        lines = []
        for product_code, share, pack_code in OUTPUT_MIX:
            product = _node(product_code)
            if product is None:
                continue
            unit_weight = product.effective_unit_weight or Decimal("1")
            quantity = (disposal * share / unit_weight).quantize(Decimal("1"))
            if quantity <= 0:
                continue
            pack = _node(pack_code) if pack_code else None
            lines.append({
                "product": product,
                "quantity": quantity,
                "unit_weight": unit_weight,
                "pack_product": pack,
                "pack_qty": quantity if pack else Decimal("0"),
            })
        services.save_grinding_voucher(voucher, lines, user=user)
        created += 1
    return created
