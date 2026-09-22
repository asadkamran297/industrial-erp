"""Bardana reporting reads (catalogue group E). Product ledger, party sack ledger, grinding bag lines."""

from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Max, Q, Sum, Value, When
from django.db.models.functions import Coalesce

from apps.core.constants import (
    INV_BARDANA_OWNERSHIP_CHOICES,
    PRD_LEDGER_PACKING_OUT,
    PRD_LEDGER_PRODUCTION_OUT,
    PRD_LEDGER_PURCHASE,
    PRD_LEDGER_PURCHASE_RETURN,
    PRD_LEDGER_SALE,
    PRD_LEDGER_SALE_RETURN,
    PRD_LEDGER_SOURCE_CHOICES,
    PRD_SPEC_FINISH_PACKING,
    PRD_SPEC_RAW_PACKING,
    STATUS_ACTIVE,
)
from apps.core.reporting import ZERO, money, weight
from apps.godowns.models import Godown
from apps.inventory.models import Supplier
from apps.production.models import GrindingOutput, GrindingVoucher

from .models import PartyBardanaLedger, ProductLedger, ProductNode

QTY = DecimalField(max_digits=14, decimal_places=3)
PACKING_SPECS = (PRD_SPEC_RAW_PACKING, PRD_SPEC_FINISH_PACKING)
SOURCE_LABELS = dict(PRD_LEDGER_SOURCE_CHOICES)
OWNERSHIP_LABELS = dict(INV_BARDANA_OWNERSHIP_CHOICES)


def _sum(expression, field=QTY, **kw):
    return Coalesce(Sum(expression, **kw), Value(Decimal("0")), output_field=field)


def bardana_item_options():
    return ProductNode.objects.filter(level=3, specification__in=PACKING_SPECS, status=STATUS_ACTIVE).order_by("name").values_list("pk", "name")


def godown_options():
    return Godown.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("pk", "name")


def party_options():
    return Supplier.objects.filter(status=STATUS_ACTIVE, bardana_ledger_entries__isnull=False).distinct().values_list("pk", "name")


def source_options():
    return PRD_LEDGER_SOURCE_CHOICES


# ---------------------------------------------------------------------------
# 29. Bardana Stock (Mill)
# ---------------------------------------------------------------------------

IN_SOURCES = (PRD_LEDGER_PURCHASE, PRD_LEDGER_SALE_RETURN)
OUT_SOURCES = (PRD_LEDGER_PACKING_OUT, PRD_LEDGER_PRODUCTION_OUT, PRD_LEDGER_SALE, PRD_LEDGER_PURCHASE_RETURN)


def bardana_stock(start, end, item=None, godown=None):
    entries = ProductLedger.objects.filter(product__specification__in=PACKING_SPECS)
    if item:
        entries = entries.filter(product_id=item)
    if godown:
        entries = entries.filter(godown_id=godown)
    keys = ("product_id", "product__name", "product__specification", "godown_id", "godown__name")
    opening = {
        (r["product_id"], r["godown_id"]): r["qty"] for r in entries.filter(entry_date__lt=start).values("product_id", "godown_id").annotate(qty=_sum("quantity"))
    }
    period = {
        (r["product_id"], r["godown_id"]): r for r in entries.filter(entry_date__range=(start, end)).values(*keys).annotate(
            purchased=_sum("quantity", filter=Q(source=PRD_LEDGER_PURCHASE, quantity__gt=0)),
            returned_in=_sum("quantity", filter=Q(source=PRD_LEDGER_SALE_RETURN, quantity__gt=0)),
            other_in=_sum("quantity", filter=Q(quantity__gt=0) & ~Q(source__in=(PRD_LEDGER_PURCHASE, PRD_LEDGER_SALE_RETURN))),
            packed=_sum("quantity", filter=Q(source__in=(PRD_LEDGER_PACKING_OUT, PRD_LEDGER_PRODUCTION_OUT), quantity__lt=0)),
            returned_out=_sum("quantity", filter=Q(source=PRD_LEDGER_PURCHASE_RETURN, quantity__lt=0)),
            other_out=_sum("quantity", filter=Q(quantity__lt=0) & ~Q(source__in=(PRD_LEDGER_PACKING_OUT, PRD_LEDGER_PRODUCTION_OUT, PRD_LEDGER_PURCHASE_RETURN))),
        )
    }
    names = dict(entries.values_list("product_id", "product__name").distinct())
    specs = dict(entries.values_list("product_id", "product__specification").distinct())
    godowns = dict(Godown.objects.values_list("pk", "name"))
    rows = []
    for key in sorted(set(opening) | set(period), key=lambda k: (names.get(k[0], ""), godowns.get(k[1], "") if k[1] else "")):
        p = period.get(key, {})
        open_qty = weight(opening.get(key))
        ins = weight(p.get("purchased")) + weight(p.get("returned_in")) + weight(p.get("other_in"))
        outs = weight(p.get("packed")) + weight(p.get("returned_out")) + weight(p.get("other_out"))
        rows.append({
            "item_id": key[0], "item": names.get(key[0], ""), "kind": "Raw sack" if specs.get(key[0]) == PRD_SPEC_RAW_PACKING else "Finished bag",
            "godown": godowns.get(key[1], "—") if key[1] else "—", "opening": open_qty, "purchased": weight(p.get("purchased")),
            "returned_in": weight(p.get("returned_in")), "other_in": weight(p.get("other_in")), "total_in": ins,
            "packed": weight(-(p.get("packed") or ZERO)), "returned_out": weight(-(p.get("returned_out") or ZERO)), "other_out": weight(-(p.get("other_out") or ZERO)),
            "total_out": weight(-outs), "closing": weight(open_qty + ins + outs),
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("opening", "purchased", "returned_in", "other_in", "total_in", "packed", "returned_out", "other_out", "total_out", "closing")}
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 30. Party Bardana Balances
# ---------------------------------------------------------------------------

def party_balances(as_of, party=None, ownership=""):
    entries = PartyBardanaLedger.objects.filter(entry_date__lte=as_of)
    if party:
        entries = entries.filter(party_id=party)
    if ownership:
        entries = entries.filter(ownership=ownership)
    grouped = (
        entries.values("party_id", "party__name", "bardana_item_id", "bardana_item__name", "ownership")
        .annotate(received=_sum("quantity", filter=Q(quantity__gt=0)), returned=_sum("quantity", filter=Q(quantity__lt=0)), balance=_sum("quantity"), last=Max("entry_date"), entries=Count("id"))
        .order_by("party__name", "bardana_item__name")
    )
    rows = [
        {
            "party_id": r["party_id"], "party": r["party__name"], "item_id": r["bardana_item_id"], "item": r["bardana_item__name"],
            "ownership": OWNERSHIP_LABELS.get(r["ownership"], r["ownership"] or "—"), "ownership_key": r["ownership"],
            "received": weight(r["received"]), "returned": weight(-r["returned"]), "held": weight(r["balance"]),
            "returnable": weight(r["balance"]) if r["ownership"] == "returnable" and r["balance"] > 0 else ZERO,
            "entries": r["entries"], "last_movement": r["last"],
        }
        for r in grouped
    ]
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("received", "returned", "held", "returnable")}
    totals["parties"] = len({r["party_id"] for r in rows})
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 31. Bardana Movement Register
# ---------------------------------------------------------------------------

def movement_register(start, end, party=None, source="", item=None, book=""):
    rows = []
    if book in ("", "party"):
        party_rows = PartyBardanaLedger.objects.filter(entry_date__range=(start, end)).select_related("party", "bardana_item", "godown")
        if party:
            party_rows = party_rows.filter(party_id=party)
        if source:
            party_rows = party_rows.filter(source=source)
        if item:
            party_rows = party_rows.filter(bardana_item_id=item)
        for e in party_rows:
            rows.append({
                "pk": e.pk, "date": e.entry_date, "book": "Party", "party_id": e.party_id, "party": e.party.name, "item": e.bardana_item.name,
                "source": SOURCE_LABELS.get(e.source, e.source), "reference": e.reference, "qty_in": weight(e.quantity) if e.quantity > 0 else ZERO,
                "qty_out": weight(-e.quantity) if e.quantity < 0 else ZERO, "ownership": OWNERSHIP_LABELS.get(e.ownership, e.ownership or "—"),
                "godown": e.godown.name if e.godown_id else "—", "remarks": e.remarks,
            })
    if book in ("", "mill") and not party:
        mill_rows = ProductLedger.objects.filter(entry_date__range=(start, end), product__specification__in=PACKING_SPECS).select_related("product", "godown")
        if source:
            mill_rows = mill_rows.filter(source=source)
        if item:
            mill_rows = mill_rows.filter(product_id=item)
        for e in mill_rows:
            rows.append({
                "pk": e.pk, "date": e.entry_date, "book": "Mill", "party_id": None, "party": "Mill stock", "item": e.product.name,
                "source": SOURCE_LABELS.get(e.source, e.source), "reference": e.reference, "qty_in": weight(e.quantity) if e.quantity > 0 else ZERO,
                "qty_out": weight(-e.quantity) if e.quantity < 0 else ZERO, "ownership": "Mill's own", "godown": e.godown.name if e.godown_id else "—", "remarks": e.remarks,
            })
    rows.sort(key=lambda r: (r["date"], r["pk"]), reverse=True)
    totals = {"qty_in": sum((r["qty_in"] for r in rows), ZERO), "qty_out": sum((r["qty_out"] for r in rows), ZERO), "entries": len(rows)}
    totals["net"] = totals["qty_in"] - totals["qty_out"]
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 32. Packing Consumption
# ---------------------------------------------------------------------------

def packing_consumption(start, end, product=None):
    outputs = GrindingOutput.objects.filter(voucher__date__range=(start, end)).select_related("voucher", "product", "pack_product")
    if product:
        outputs = outputs.filter(product_id=product)
    rows = []
    for o in outputs.order_by("-voucher__date", "-voucher__seq_num", "line_number"):
        bags_out = o.quantity
        bags_used = o.pack_qty
        rows.append({
            "pk": o.voucher_id, "number": o.voucher.voucher_no, "date": o.voucher.date, "product_id": o.product_id, "product": o.product.name,
            "pack": o.pack_product.name if o.pack_product_id else "—", "output_units": weight(bags_out), "output_kg": weight(bags_out * o.unit_weight),
            "bags_used": weight(bags_used), "variance": weight(bags_used - bags_out), "variance_pct": ((bags_used - bags_out) / bags_out * 100).quantize(Decimal("0.01")) if bags_out else None,
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("output_units", "output_kg", "bags_used", "variance")}
    totals["lines"] = len(rows)
    totals["variance_pct"] = (totals["variance"] / totals["output_units"] * 100).quantize(Decimal("0.01")) if totals["output_units"] else None
    return {"rows": rows, "totals": totals}


def output_product_options():
    return ProductNode.objects.filter(grinding_outputs__isnull=False).distinct().order_by("name").values_list("pk", "name")
