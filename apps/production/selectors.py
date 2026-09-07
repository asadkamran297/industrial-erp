"""Reads. Nothing here writes, so a screen can call any of it freely."""

from decimal import Decimal

from django.db.models import DecimalField, F, QuerySet, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from apps.products import selectors as product_selectors

from .models import GrindingOutput, GrindingVoucher, ProductConversion

WEIGHT_FIELD = DecimalField(max_digits=18, decimal_places=3)
ZERO = Decimal("0")


def _sum(expression):
    return Coalesce(Sum(expression), Value(ZERO), output_field=WEIGHT_FIELD)


# ---------------------------------------------------------------------------
# Grinding
# ---------------------------------------------------------------------------
def grinding_vouchers() -> QuerySet[GrindingVoucher]:
    return GrindingVoucher.objects.select_related("wheat_item", "bag_item", "godown", "prepared_by")


def grinding_with_bags() -> QuerySet[GrindingVoucher]:
    """The list screen: every column it shows, in one query.

    Output bags are summed in the database rather than walked per row, because
    the list is paged at fifty and fifty extra queries is the difference between
    a screen and a wait.
    """
    return grinding_vouchers().annotate(output_bags=_sum("outputs__quantity")).order_by("-date", "-seq_num")


def grinding_detail(pk) -> GrindingVoucher | None:
    return (
        grinding_vouchers()
        .prefetch_related("outputs__product", "outputs__pack_product")
        .filter(pk=pk)
        .first()
    )


def conversions() -> QuerySet[ProductConversion]:
    return ProductConversion.objects.select_related("source_product", "godown", "prepared_by")


def conversion_detail(pk) -> ProductConversion | None:
    return (
        conversions()
        .prefetch_related("outputs__product", "outputs__pack_product")
        .filter(pk=pk)
        .first()
    )


# ---------------------------------------------------------------------------
# Pickers for the entry screen
# ---------------------------------------------------------------------------
def wheat_options():
    return product_selectors.wheat_items().order_by("complete_code")


def bag_options():
    return product_selectors.raw_packing_items().order_by("complete_code")


def output_options():
    """Finish items and by-products only. Raw and packing never appear here."""
    return product_selectors.packable_items().order_by("complete_code")


def pack_options():
    return product_selectors.finish_packing_items().order_by("complete_code")


def product_payload(on_date=None, godown=None) -> list[dict]:
    """What the entry grid needs to fill a line the moment a product is picked:
    its unit weight, its default bag, and its stock as at the voucher's date."""
    stock = product_selectors.stock_map_as_of(on_date, godown)
    rows = []
    for product in output_options().select_related("finish_bardana_link__bag_item"):
        link = getattr(product, "finish_bardana_link", None)
        rows.append(
            {
                "id": product.pk,
                "name": str(product),
                "unit": product.unit,
                "unit_weight": str(product.effective_unit_weight),
                "pack_product": link.bag_item_id if link else None,
                "pack_product_name": str(link.bag_item) if link else "",
                "stock": str(stock.get(product.pk, ZERO)),
            }
        )
    return rows


def wheat_payload(on_date=None, godown=None) -> list[dict]:
    """Wheat options carrying the stock that existed on the voucher's date, the
    sack that wheat was actually received in, and its standard yield."""
    stock = product_selectors.stock_map_as_of(on_date, godown)
    rows = []
    for wheat in wheat_options().select_related("raw_bardana_link__bardana_item"):
        bag = product_selectors.received_bardana_item(wheat, on_date)
        rows.append(
            {
                "id": wheat.pk,
                "name": str(wheat),
                "stock": str(stock.get(wheat.pk, ZERO)),
                "bag_item": bag.pk if bag else None,
                "bag_item_name": str(bag) if bag else "",
                "standard_yield": str(wheat.standard_yield_percent or ZERO),
            }
        )
    return rows


def pack_stock_payload(on_date=None, godown=None) -> dict[str, str]:
    stock = product_selectors.stock_map_as_of(on_date, godown)
    return {str(pk): str(value) for pk, value in stock.items()}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def daily_grinding(date_from=None, date_to=None, wheat_item=None, godown=None):
    # Not the bag-annotated queryset: its join to the output lines repeats the
    # header once per line, and anything summed over it counts the wheat as
    # many times as the run had products.
    queryset = grinding_vouchers()
    if date_from:
        queryset = queryset.filter(date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__lte=date_to)
    if wheat_item:
        queryset = queryset.filter(wheat_item_id=wheat_item)
    if godown:
        queryset = queryset.filter(godown_id=godown)
    return queryset.order_by("date", "seq_num")


def grinding_totals(queryset) -> dict:
    """Totals for whatever the screen is showing.

    Re-addressed at the plain table by primary key rather than aggregated over
    the caller's queryset: the list screen's rows carry a join to the output
    lines, and summing header columns across that join multiplies them.
    """
    return GrindingVoucher.objects.filter(pk__in=queryset.values("pk")).aggregate(
        disposal_wheat=_sum("disposal_wheat"),
        disposal_bags=_sum("disposal_bag_qty"),
        output_kg=_sum("total_output_kg"),
    )


def yield_by_day(date_from=None, date_to=None):
    """Yield per day, weighted by wheat rather than averaged over vouchers.

    Two runs on one day are not two equal opinions about the day's yield: a
    500-tonne run and a 5-tonne run get the weight their wheat gives them.
    """
    queryset = daily_grinding(date_from, date_to)
    rows = (
        queryset.values("date")
        .annotate(wheat=_sum("disposal_wheat"), output=_sum("total_output_kg"))
        .order_by("date")
    )
    return [_with_yield(row, "date") for row in rows]


def yield_by_month(date_from=None, date_to=None):
    queryset = daily_grinding(date_from, date_to)
    rows = (
        queryset.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(wheat=_sum("disposal_wheat"), output=_sum("total_output_kg"))
        .order_by("month")
    )
    return [_with_yield(row, "month") for row in rows]


def _with_yield(row: dict, key: str) -> dict:
    wheat, output = row["wheat"] or ZERO, row["output"] or ZERO
    percent = (output / wheat * Decimal("100")).quantize(Decimal("0.001")) if wheat else ZERO
    shortage = wheat - output
    return {
        "period": row[key],
        "wheat": wheat,
        "output": output,
        "yield_percent": percent,
        "shortage_kg": shortage,
        "shortage_percent": (shortage / wheat * Decimal("100")).quantize(Decimal("0.001")) if wheat else ZERO,
    }


def period_average_yield(date_from=None, date_to=None) -> dict:
    totals = grinding_totals(daily_grinding(date_from, date_to))
    return _with_yield({"wheat": totals["disposal_wheat"], "output": totals["output_kg"]}, "wheat") | {
        "period": None,
    }


def production_summary(date_from=None, date_to=None, godown=None):
    """Output by product for a date range -- the rows the parta statement reads.

    Grouped by the product's sub-group as well, because that is the mill's own
    category: Atta, Maida, Fine, Suji, Bran, Refraction are sub-groups of the
    product tree, not a separate list that could disagree with it.
    """
    queryset = GrindingOutput.objects.filter(voucher__deleted_at__isnull=True)
    if date_from:
        queryset = queryset.filter(voucher__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(voucher__date__lte=date_to)
    if godown:
        queryset = queryset.filter(voucher__godown_id=godown)

    rows = (
        queryset.values(
            "product_id",
            "product__name",
            "product__complete_code",
            category=F("product__parent__name"),
        )
        # The aliases cannot be called "quantity" and "unit_weight": an alias
        # shadows the column of the same name, and the weight expression would
        # then be multiplying its own aggregate.
        .annotate(
            total_qty=_sum("quantity"),
            # Weight is multiplied per row and then summed; the snapshot on the
            # line is what makes this safe to read months later.
            total_weight=Coalesce(
                Sum(F("quantity") * F("unit_weight"), output_field=WEIGHT_FIELD),
                Value(ZERO),
                output_field=WEIGHT_FIELD,
            ),
        )
        .order_by("category", "product__complete_code")
    )
    return list(rows)


def summary_by_category(rows) -> list[dict]:
    """Fold the product rows up to their category, for the report's top block."""
    buckets: dict[str, dict] = {}
    for row in rows:
        name = row["category"] or "Uncategorised"
        bucket = buckets.setdefault(name, {"category": name, "total_qty": ZERO, "total_weight": ZERO})
        bucket["total_qty"] += row["total_qty"] or ZERO
        bucket["total_weight"] += row["total_weight"] or ZERO
    return sorted(buckets.values(), key=lambda item: item["category"])
