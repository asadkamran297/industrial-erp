"""Reads. Nothing here writes, so a screen can call any of it freely."""

from decimal import Decimal

from django.db.models import DecimalField, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from apps.core.constants import (
    PRD_BUYABLE_SPECS,
    PRD_LEVEL_ITEM,
    PRD_LEVEL_SUB_GROUP,
    PRD_PACKABLE_SPECS,
    PRD_SPEC_FINISH_PACKING,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    PRD_STOCKED_SPECS,
    STATUS_ACTIVE,
)

from .models import ProductLedger, ProductNode

QUANTITY_FIELD = DecimalField(max_digits=14, decimal_places=3)


def stock_expression():
    """Signed ledger sum. In is positive, out negative, so one SUM is enough."""
    return Coalesce(Sum("ledger_entries__quantity"), Value(Decimal("0")), output_field=QUANTITY_FIELD)


def product_queryset() -> QuerySet[ProductNode]:
    return ProductNode.objects.select_related("parent", "parent__parent")


def items(**filters) -> QuerySet[ProductNode]:
    return product_queryset().filter(level=PRD_LEVEL_ITEM, **filters)


def active_items(**filters) -> QuerySet[ProductNode]:
    return items(status=STATUS_ACTIVE, **filters)


def items_with_stock() -> QuerySet[ProductNode]:
    """Items annotated with ``stock``, which is never stored on the row.

    The order is restated because the GROUP BY the annotation adds drops the
    model's own ordering, and an unordered list cannot be paged consistently.
    """
    return items().annotate(stock=stock_expression()).order_by("complete_code")


def buyable_items() -> QuerySet[ProductNode]:
    return active_items(specification__in=PRD_BUYABLE_SPECS)


def wheat_items() -> QuerySet[ProductNode]:
    return active_items(specification=PRD_SPEC_RAW_ITEM)


def raw_packing_items() -> QuerySet[ProductNode]:
    return active_items(specification=PRD_SPEC_RAW_PACKING)


def finish_packing_items() -> QuerySet[ProductNode]:
    return active_items(specification=PRD_SPEC_FINISH_PACKING)


def stocked_items() -> QuerySet[ProductNode]:
    """Items the ledger counts. A service or wage item never appears here."""
    return active_items(specification__in=PRD_STOCKED_SPECS)


def packable_items() -> QuerySet[ProductNode]:
    """What comes off the grinding floor and so needs a bag chosen for it."""
    return active_items(specification__in=PRD_PACKABLE_SPECS)


def sub_groups() -> QuerySet[ProductNode]:
    """The only level a new item may be parented to."""
    return product_queryset().filter(level=PRD_LEVEL_SUB_GROUP).order_by("complete_code")


def product_stock(product: ProductNode) -> Decimal:
    row = ProductLedger.objects.filter(product=product).aggregate(total=stock_expression_flat())
    return row["total"] or Decimal("0")


def stock_expression_flat():
    return Coalesce(Sum("quantity"), Value(Decimal("0")), output_field=QUANTITY_FIELD)


def stock_by_product() -> dict[int, Decimal]:
    """One query for the whole list screen rather than one query per row."""
    rows = ProductLedger.objects.values("product_id").annotate(total=stock_expression_flat())
    return {row["product_id"]: row["total"] or Decimal("0") for row in rows}


def tree_rows(queryset: QuerySet[ProductNode]) -> list[ProductNode]:
    """The matching items, each preceded by the headings it sits under.

    The list is read as a tree: a filtered item that lost its heading would
    leave the reader with a code and no idea which part of the mill it belongs
    to. Headings are pulled in for the matches actually shown, so an empty
    heading never appears.
    """
    matches = list(queryset)
    heading_ids = set()
    for item in matches:
        node = item.parent
        while node is not None:
            heading_ids.add(node.pk)
            node = node.parent
    headings = product_queryset().filter(pk__in=heading_ids)
    rows = sorted([*headings, *matches], key=lambda node: node.display_code)
    return rows


def search_products(queryset: QuerySet[ProductNode], term: str) -> QuerySet[ProductNode]:
    term = (term or "").strip()
    if not term:
        return queryset
    return queryset.filter(
        Q(name__icontains=term) | Q(complete_code__icontains=term) | Q(quick_code__icontains=term)
    )


def next_code_segment(parent: ProductNode | None, level: int) -> str:
    """The next free segment under a parent, zero-padded to the level's width.

    Gaps left by closed products are not reused: a code that has been used is
    spent, and reissuing it would make two different products share a code in
    the same set of books.
    """
    from apps.core.constants import PRD_SEGMENT_WIDTHS

    width = PRD_SEGMENT_WIDTHS[level]
    siblings = ProductNode.all_objects.filter(parent=parent, level=level)
    used = [int(value) for value in siblings.values_list("code_segment", flat=True) if value.isdigit()]
    return str(max(used) + 1 if used else 1).zfill(width)


def ledger_rows(product: ProductNode) -> list[dict]:
    """A product's movements oldest first, with the balance rolled up."""
    balance = Decimal("0")
    rows = []
    for entry in ProductLedger.objects.filter(product=product).order_by("entry_date", "id"):
        balance += entry.quantity
        rows.append({"entry": entry, "balance": balance})
    return rows


def current_rate_map() -> dict[int, Decimal]:
    from .models import ProductRate

    return {
        row.product_id: row.rate
        for row in ProductRate.objects.filter(is_current=True).order_by("product_id", "-effective_date")
    }
