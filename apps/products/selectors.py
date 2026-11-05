"""Reads. Nothing here writes, so a screen can call any of it freely."""

from decimal import Decimal

from django.db.models import DecimalField, F, Max, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from apps.core.constants import (
    GL_STOCK_STORES,
    PRD_BUYABLE_SPECS,
    PRD_SPEC_STOCK_ACCOUNT,
    PRD_MOUND_RATE_SPECS,
    PRD_UNIT_BASE_WEIGHT,
    PRD_UNIT_KG,
    PRD_UNIT_MOUND,
    PRD_LEDGER_OPENING,
    PRD_LEDGER_PURCHASE,
    PRODUCTION_OPEN_STOCK_PACK_NAME,
    PRD_LEVEL_ITEM,
    PRD_LEVEL_SUB_GROUP,
    PRD_PACKABLE_SPECS,
    PRD_SPEC_FINISH_PACKING,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    PRD_STOCKED_SPECS,
    STATUS_ACTIVE,
)

from .models import PartyBardanaLedger, ProductClosingRate, ProductLedger, ProductNode, RawBardanaLink

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


def rate_per_stock_unit(specification, unit, rate):
    """List rate converted to the unit stock is counted in; wheat is quoted per maund but kept in kg."""
    rate = rate or Decimal("0")
    if specification in PRD_MOUND_RATE_SPECS and unit == PRD_UNIT_KG:
        return (rate / Decimal(PRD_UNIT_BASE_WEIGHT[PRD_UNIT_MOUND])).quantize(Decimal("0.0001"))
    return rate


def unit_rate_map() -> dict[int, Decimal]:
    """Current list rate per stock unit (kg for wheat), for valuing quantities."""
    from .models import ProductRate

    return {
        product_id: rate_per_stock_unit(specification, unit, rate)
        for product_id, specification, unit, rate in ProductRate.objects.filter(is_current=True)
        .order_by("product_id", "-effective_date")
        .values_list("product_id", "product__specification", "product__unit", "rate")
    }


def stock_as_of(product: ProductNode, on_date=None, godown=None) -> Decimal:
    """What was on hand at the close of ``on_date``.

    A grinding voucher is often written days later, and the operator needs the
    stock that existed then, not the stock that exists now.
    """
    entries = ProductLedger.objects.filter(product=product)
    if on_date is not None:
        entries = entries.filter(entry_date__lte=on_date)
    if godown is not None:
        entries = entries.filter(godown=godown)
    return entries.aggregate(total=stock_expression_flat())["total"]


def stock_expression_flat():
    """The signed sum, addressed straight at the ledger rather than across a FK."""
    return Coalesce(Sum("quantity"), Value(Decimal("0")), output_field=QUANTITY_FIELD)


def stock_map_as_of(on_date=None, godown=None) -> dict[int, Decimal]:
    """``{product_id: stock}`` for every stocked item in one query.

    The entry screen needs a stock figure beside every option in three
    dropdowns; one grouped query beats one query per row.
    """
    entries = ProductLedger.objects.all()
    if on_date is not None:
        entries = entries.filter(entry_date__lte=on_date)
    if godown is not None:
        entries = entries.filter(godown=godown)
    rows = entries.values("product_id").annotate(total=stock_expression_flat())
    return {row["product_id"]: row["total"] for row in rows}


def received_bardana_item(wheat_item: ProductNode, on_date=None):
    """The sack this wheat was last actually received in.

    Falls back to the master link, and to nothing, so the caller always has one
    call to make rather than three.
    """
    entries = ProductLedger.objects.filter(product=wheat_item, bardana_item__isnull=False)
    if on_date is not None:
        entries = entries.filter(entry_date__lte=on_date)
    latest = entries.order_by("-entry_date", "-id").values_list("bardana_item_id", flat=True).first()
    if latest:
        return ProductNode.objects.filter(pk=latest).first()
    link = getattr(wheat_item, "raw_bardana_link", None)
    return link.bardana_item if link else None


def open_stock_packing_item():
    """The "packed in nothing" row loose output points at."""
    return ProductNode.objects.filter(
        specification=PRD_SPEC_FINISH_PACKING,
        name__iexact=PRODUCTION_OPEN_STOCK_PACK_NAME,
    ).first()


def party_bardana_balance_queryset() -> QuerySet:
    """One row per party and sack with in, out and balance."""
    return (
        PartyBardanaLedger.objects
        .values("party_id", "party__name", "bardana_item_id", "bardana_item__name", "bardana_item__complete_code")
        .annotate(
            qty_in=Coalesce(Sum("quantity", filter=Q(quantity__gt=0)), Value(Decimal("0")), output_field=QUANTITY_FIELD),
            qty_out=Coalesce(Sum("quantity", filter=Q(quantity__lt=0)), Value(Decimal("0")), output_field=QUANTITY_FIELD),
            balance=Coalesce(Sum("quantity"), Value(Decimal("0")), output_field=QUANTITY_FIELD),
            last_date=Max("entry_date"),
        )
        .order_by("party__name", "bardana_item__complete_code")
    )


def raw_bardana_map() -> dict[int, int]:
    """wheat item id -> linked bardana item id."""
    return dict(RawBardanaLink.objects.values_list("wheat_item_id", "bardana_item_id"))


def average_purchase_rates(on_date) -> dict[int, Decimal]:
    """Weighted rate of every costed opening and purchase up to ``on_date``."""
    rows = (
        ProductLedger.objects.filter(
            entry_date__lte=on_date, quantity__gt=0, rate__gt=0,
            source__in=(PRD_LEDGER_OPENING, PRD_LEDGER_PURCHASE),
        )
        .values("product_id")
        .annotate(
            value=Coalesce(Sum(F("quantity") * F("rate")), Value(Decimal("0")), output_field=DecimalField(max_digits=20, decimal_places=5)),
            qty=Coalesce(Sum("quantity"), Value(Decimal("0")), output_field=QUANTITY_FIELD),
        )
        .order_by()
    )
    return {
        row["product_id"]: (row["value"] / row["qty"]).quantize(Decimal("0.01"))
        for row in rows if row["qty"]
    }


def closing_rate_map(on_date) -> dict[int, tuple[Decimal, bool]]:
    """``{product_id: (rate, saved)}`` used to value stock at the close of ``on_date``.

    A rate saved for that exact date wins; otherwise average purchase rate,
    then the last saved closing rate, then the current list rate.
    """
    saved = dict(ProductClosingRate.objects.filter(as_of=on_date).values_list("product_id", "rate"))
    earlier = {}
    for product_id, rate in ProductClosingRate.objects.filter(as_of__lt=on_date).order_by("-as_of").values_list("product_id", "rate"):
        earlier.setdefault(product_id, rate)
    averages = average_purchase_rates(on_date)
    listed = unit_rate_map()
    rates = {}
    for product_id in set(saved) | set(earlier) | set(averages) | set(listed):
        if product_id in saved:
            rates[product_id] = (saved[product_id], True)
        else:
            rate = averages.get(product_id) or earlier.get(product_id) or listed.get(product_id) or Decimal("0")
            rates[product_id] = (rate, False)
    return rates


def closing_stock(on_date) -> list[dict]:
    """Every stocked item with its quantity, rate and value at the close of ``on_date``."""
    quantities = stock_map_as_of(on_date)
    rates = closing_rate_map(on_date)
    rows = []
    for product in stocked_items().order_by("complete_code"):
        quantity = quantities.get(product.pk) or Decimal("0")
        rate, saved = rates.get(product.pk, (Decimal("0"), False))
        rows.append({
            "product": product,
            "quantity": quantity,
            "rate": rate,
            "saved": saved,
            "value": (quantity * rate).quantize(Decimal("0.01")),
        })
    return rows


def closing_stock_value(on_date) -> Decimal:
    return sum((row["value"] for row in closing_stock(on_date)), Decimal("0.00"))


def closing_stock_by_account(on_date) -> dict[str, Decimal]:
    """Closing stock value per stock account bucket (wheat, finished, packing)."""
    totals = {}
    for row in closing_stock(on_date):
        bucket = PRD_SPEC_STOCK_ACCOUNT.get(row["product"].specification, GL_STOCK_STORES)
        totals[bucket] = totals.get(bucket, Decimal("0.00")) + row["value"]
    return totals
