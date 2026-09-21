"""Reads. Nothing here writes."""

from collections import defaultdict
from decimal import Decimal

from django.db.models import QuerySet

from apps.core.constants import STATUS_ACTIVE

from .models import Godown


def godowns() -> QuerySet[Godown]:
    return Godown.objects.all()


def active_godowns() -> QuerySet[Godown]:
    return godowns().filter(status=STATUS_ACTIVE)


def default_godown() -> Godown | None:
    """What a new document opens on when the operator has not chosen yet."""
    return active_godowns().first()


def stock_by_godown(godown_ids) -> dict[int, list[dict]]:
    """Per-godown product balances from the product ledger, one query for the page."""
    from apps.products.models import ProductLedger
    from apps.products.selectors import stock_expression_flat

    rows = (
        ProductLedger.objects.filter(godown_id__in=list(godown_ids))
        .values("godown_id", "product__name", "product__unit")
        .annotate(total=stock_expression_flat())
        .order_by("product__name")
    )
    result: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        if (row["total"] or Decimal("0")) == 0:
            continue
        result[row["godown_id"]].append(
            {"name": row["product__name"], "unit": row["product__unit"], "quantity": row["total"]}
        )
    return result


def stock_totals(lines: list[dict]) -> list[dict]:
    """One figure per unit, so wheat kg and bardana pieces never add together."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for line in lines:
        totals[line["unit"] or ""] += line["quantity"]
    return [{"unit": unit, "quantity": total} for unit, total in totals.items() if total]


def godown_stock_lines(godown: Godown) -> list[dict]:
    """Per-product position in one godown: balance plus how much came in and went out."""
    from django.db.models import Case, DecimalField, F, Sum, Value, When

    from apps.products.models import ProductLedger

    qty = DecimalField(max_digits=14, decimal_places=3)
    rows = (
        ProductLedger.objects.filter(godown=godown)
        .values("product_id", "product__complete_code", "product__name", "product__unit")
        .annotate(
            total_in=Sum(Case(When(quantity__gt=0, then=F("quantity")), default=Value(Decimal("0")), output_field=qty)),
            total_out=Sum(Case(When(quantity__lt=0, then=-F("quantity")), default=Value(Decimal("0")), output_field=qty)),
            balance=Sum("quantity"),
        )
        .order_by("product__complete_code")
    )
    return [
        {
            "product_id": row["product_id"],
            "code": row["product__complete_code"],
            "name": row["product__name"],
            "unit": row["product__unit"],
            "total_in": row["total_in"] or Decimal("0"),
            "total_out": row["total_out"] or Decimal("0"),
            "quantity": row["balance"] or Decimal("0"),
        }
        for row in rows
    ]


def godown_movements(godown: Godown, limit: int = 200):
    from apps.products.models import ProductLedger

    return (
        ProductLedger.objects.filter(godown=godown)
        .select_related("product")
        .order_by("-entry_date", "-id")[:limit]
    )
