"""The mill's own tree, its bag sizes, and the links between them.

Re-runnable: everything is matched on its code or its name, so seeding twice
changes nothing the second time.
"""

from django.utils import timezone

from apps.core.constants import (
    PRD_LEVEL_GROUP,
    PRD_LEVEL_ITEM,
    PRD_LEVEL_SUB_GROUP,
    PRD_SPEC_BYPRODUCT,
    PRD_SPEC_FINISH_ITEM,
    PRD_SPEC_FINISH_PACKING,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    PRD_UNIT_KG,
    PRD_UNIT_PIECE,
    STATUS_ACTIVE,
)
from apps.products.models import FinishBardanaLink, ProductNode, RawBardanaLink

# (segment, name)
GROUPS = (
    ("01", "Raw"),
    ("02", "Finish"),
    ("03", "Packing"),
    ("04", "Services"),
    ("05", "Wages"),
)

# (group segment, sub segment, name)
SUB_GROUPS = (
    ("01", "01", "Wheat Private"),
    ("01", "02", "Wheat Government"),
    ("02", "01", "Atta"),
    ("02", "02", "S.Fine"),
    ("02", "03", "Maida"),
    ("02", "04", "Fine"),
    ("02", "05", "Suji"),
    ("02", "06", "Bran"),
    ("02", "07", "Refraction"),
    ("03", "01", "Wheat Bardana"),
    ("03", "02", "Finish Bardana"),
)

# (complete code, name, specification, unit, unit weight)
ITEMS = (
    ("01-01-001", "Wheat Pvt - P", PRD_SPEC_RAW_ITEM, PRD_UNIT_KG, 1),
    ("01-01-002", "Wheat Pvt - J", PRD_SPEC_RAW_ITEM, PRD_UNIT_KG, 1),
    ("01-02-001", "Wheat Govt - P", PRD_SPEC_RAW_ITEM, PRD_UNIT_KG, 1),
    ("01-02-002", "Wheat Govt - J", PRD_SPEC_RAW_ITEM, PRD_UNIT_KG, 1),
    ("02-01-002", "Atta Jugnoo 15 kg", PRD_SPEC_FINISH_ITEM, PRD_UNIT_PIECE, 15),
    ("02-01-044", "Atta Sherdil 10 kg", PRD_SPEC_FINISH_ITEM, PRD_UNIT_PIECE, 10),
    ("02-03-012", "Maida Zafaran 50 kg", PRD_SPEC_FINISH_ITEM, PRD_UNIT_PIECE, 50),
    ("02-03-013", "Maida Zafaran 01 kg", PRD_SPEC_FINISH_ITEM, PRD_UNIT_KG, 1),
    ("02-06-002", "Bran 20 kg", PRD_SPEC_BYPRODUCT, PRD_UNIT_PIECE, 20),
    ("03-01-001", "Poly-B (Wheat Pvt)", PRD_SPEC_RAW_PACKING, PRD_UNIT_PIECE, 0),
    ("03-01-002", "Jute-B (Wheat Pvt)", PRD_SPEC_RAW_PACKING, PRD_UNIT_PIECE, 0),
    ("03-01-003", "Poly-B (Wheat Govt)", PRD_SPEC_RAW_PACKING, PRD_UNIT_PIECE, 0),
    ("03-01-004", "Jute-B (Wheat Govt)", PRD_SPEC_RAW_PACKING, PRD_UNIT_PIECE, 0),
    # The bags the mill packs into. "Open Stock without Bardana" is a real row
    # so that a loose sale still points at something.
    ("03-02-001", "(5KG)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-002", "16X21 (10Kg)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-003", "17X26 (15 Kg)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-004", "18X28.5 (20 KG)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-005", "20X30 (25 KG)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-006", "22X37 (40 KG)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-007", "22X41 (50 Kg)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-008", "27X46 (80 KG)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-009", "27X48 (B-49 KG)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-010", "22X38 (B-20 KG)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-011", "25X39 (Bran-M-20KG)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-012", "27x45 (B-27 kg)", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
    ("03-02-013", "Open Stock without Bardana", PRD_SPEC_FINISH_PACKING, PRD_UNIT_PIECE, 0),
)

# wheat item code -> the sack it arrives in
RAW_BARDANA = (
    ("01-01-001", "03-01-001"),
    ("01-01-002", "03-01-002"),
    ("01-02-001", "03-01-003"),
    ("01-02-002", "03-01-004"),
)

# finished product code -> the bag it is packed in
FINISH_BARDANA = (
    ("02-01-044", "03-02-002"),
    ("02-01-002", "03-02-003"),
    ("02-03-012", "03-02-007"),
    ("02-03-013", "03-02-013"),
)


def _node(code: str) -> ProductNode | None:
    return ProductNode.objects.filter(complete_code=code).first()


def seed_products() -> int:
    created = 0
    today = timezone.localdate()

    for segment, name in GROUPS:
        _, made = ProductNode.objects.get_or_create(
            complete_code=segment,
            defaults={"parent": None, "level": PRD_LEVEL_GROUP, "code_segment": segment, "name": name},
        )
        created += int(made)

    for group_segment, sub_segment, name in SUB_GROUPS:
        parent = _node(group_segment)
        if parent is None:
            continue
        _, made = ProductNode.objects.get_or_create(
            complete_code=f"{group_segment}-{sub_segment}",
            defaults={
                "parent": parent,
                "level": PRD_LEVEL_SUB_GROUP,
                "code_segment": sub_segment,
                "name": name,
            },
        )
        created += int(made)

    for code, name, specification, unit, unit_weight in ITEMS:
        group_segment, sub_segment, item_segment = code.split("-")
        parent = _node(f"{group_segment}-{sub_segment}")
        if parent is None:
            continue
        _, made = ProductNode.objects.get_or_create(
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
                "starting_date": today,
            },
        )
        created += int(made)

    for wheat_code, bardana_code in RAW_BARDANA:
        wheat, bardana = _node(wheat_code), _node(bardana_code)
        if wheat and bardana:
            _, made = RawBardanaLink.objects.get_or_create(
                wheat_item=wheat, defaults={"bardana_item": bardana}
            )
            created += int(made)

    for finish_code, bag_code in FINISH_BARDANA:
        finish, bag = _node(finish_code), _node(bag_code)
        if finish and bag:
            _, made = FinishBardanaLink.objects.get_or_create(
                finish_item=finish, defaults={"bag_item": bag}
            )
            created += int(made)

    return created
