"""Stock reporting reads (catalogue group G). Product ledger for mill goods, item ledger for stores."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Max, Q, Sum, Value, When
from django.db.models.functions import Coalesce

from apps.core.constants import (
    PRD_LEDGER_SOURCE_CHOICES,
    PRD_SPEC_FINISH_PACKING,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    PRD_UNIT_BASE_WEIGHT,
    STATUS_ACTIVE,
    STATUS_POSTED,
)
from apps.core.reporting import ZERO, money, mund, weight
from apps.godowns.models import Godown
from apps.products.models import ProductLedger, ProductNode, ProductRate

from .models import InventoryClass, InventoryItem, ItemLedger, ManualTransaction, Stock

QTY = DecimalField(max_digits=18, decimal_places=3)
MONEY = DecimalField(max_digits=18, decimal_places=2)
SOURCE_LABELS = dict(PRD_LEDGER_SOURCE_CHOICES)
PACKING = (PRD_SPEC_RAW_PACKING, PRD_SPEC_FINISH_PACKING)


def _sum(expression, field=QTY, **kw):
    return Coalesce(Sum(expression, **kw), Value(Decimal("0")), output_field=field)


def _unit_kg(prefix="product__"):
    return Case(
        *[When(**{f"{prefix}unit": unit}, then=Value(Decimal(kg))) for unit, kg in PRD_UNIT_BASE_WEIGHT.items()],
        default=F(f"{prefix}unit_weight"), output_field=QTY,
    )


def godown_options():
    return Godown.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("pk", "name")


def product_options():
    return ProductNode.objects.filter(level=3, ledger_entries__isnull=False).distinct().order_by("name").values_list("pk", "name")


def family_options():
    return ProductNode.objects.filter(level=2, status=STATUS_ACTIVE).order_by("name").values_list("pk", "name")


def class_options():
    return InventoryClass.objects.filter(status=STATUS_ACTIVE).order_by("title").values_list("pk", "title")


def _family_label(spec, parent):
    if spec == PRD_SPEC_RAW_ITEM:
        return "Wheat"
    if spec in PACKING:
        return "Bardana"
    return parent or "Products"


# ---------------------------------------------------------------------------
# 41. Mill Product Stock
# ---------------------------------------------------------------------------

def mill_stock(start, end, product=None, godown=None, family=None):
    entries = ProductLedger.objects.all()
    if product:
        entries = entries.filter(product_id=product)
    if godown:
        entries = entries.filter(godown_id=godown)
    if family:
        entries = entries.filter(product__parent_id=family)
    keys = ("product_id", "godown_id")
    opening = {(r["product_id"], r["godown_id"]): r["q"] for r in entries.filter(entry_date__lt=start).values(*keys).annotate(q=_sum("quantity"))}
    moved = {
        (r["product_id"], r["godown_id"]): r for r in entries.filter(entry_date__range=(start, end)).values(*keys)
        .annotate(qin=_sum("quantity", filter=Q(quantity__gt=0)), qout=_sum("quantity", filter=Q(quantity__lt=0)))
    }
    products = {p.pk: p for p in ProductNode.objects.filter(pk__in={k[0] for k in set(opening) | set(moved)}).select_related("parent")}
    godowns = dict(Godown.objects.values_list("pk", "name"))
    rates = {r.product_id: r.rate for r in ProductRate.objects.filter(is_current=True)}
    rows = []
    for key in sorted(set(opening) | set(moved), key=lambda k: (products[k[0]].complete_code, godowns.get(k[1], "") if k[1] else "")):
        p = products[key[0]]
        m = moved.get(key, {})
        open_q = weight(opening.get(key))
        qin, qout = weight(m.get("qin")), weight(-(m.get("qout") or ZERO))
        closing = weight(open_q + qin - qout)
        unit_kg = p.effective_unit_weight
        rate = rates.get(p.pk, ZERO)
        rows.append({
            "product_id": p.pk, "product": p.name, "family": _family_label(p.specification, p.parent.name if p.parent_id else ""), "unit": p.get_unit_display() if p.unit else "",
            "godown": godowns.get(key[1], "—") if key[1] else "—", "opening": open_q, "qty_in": qin, "qty_out": qout, "closing": closing,
            "closing_kg": weight(closing * unit_kg), "closing_mund": mund(closing * unit_kg), "rate": money(rate), "value": money(closing * rate),
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("opening", "qty_in", "qty_out", "closing", "closing_kg", "closing_mund", "value")}
    families = defaultdict(lambda: {"closing_kg": ZERO, "value": ZERO})
    for r in rows:
        families[r["family"]]["closing_kg"] += r["closing_kg"]
        families[r["family"]]["value"] += r["value"]
    return {"rows": rows, "totals": totals, "families": dict(families)}


# ---------------------------------------------------------------------------
# 42. Stores Stock
# ---------------------------------------------------------------------------

def _stores_movements(start, end, item_class=None):
    ledger = ItemLedger.objects.filter(status=STATUS_ACTIVE)
    if item_class:
        ledger = ledger.filter(inventory_item__item_class_id=item_class)
    delta = F("new_quantity") - F("old_quantity")
    opening = {r["inventory_item_id"]: r["q"] for r in ledger.filter(transaction_date__lt=start).values("inventory_item_id").annotate(q=_sum(delta))}
    moved = {
        r["inventory_item_id"]: r for r in ledger.filter(transaction_date__range=(start, end)).values("inventory_item_id")
        .annotate(qin=_sum(delta, filter=Q(new_quantity__gt=F("old_quantity"))), qout=_sum(delta, filter=Q(new_quantity__lt=F("old_quantity"))))
    }
    last = dict(ledger.values_list("inventory_item_id").annotate(last=Max("transaction_date")).values_list("inventory_item_id", "last"))
    return opening, moved, last


def stores_stock(start, end, item_class=None, below_zero_only=False):
    opening, moved, last = _stores_movements(start, end, item_class)
    stocks = Stock.objects.filter(status=STATUS_ACTIVE).select_related("inventory_item__item_class", "inventory_item__uom")
    if item_class:
        stocks = stocks.filter(inventory_item__item_class_id=item_class)
    rows = []
    for s in stocks.order_by("item_name"):
        iid = s.inventory_item_id
        m = moved.get(iid, {})
        open_q = weight(opening.get(iid))
        qin, qout = weight(m.get("qin")), weight(-(m.get("qout") or ZERO))
        closing = weight(open_q + qin - qout)
        if not (open_q or qin or qout or s.current_quantity):
            continue
        last_move = last.get(iid)
        rows.append({
            "item_id": iid, "code": s.item_code, "item": s.item_name, "category": s.inventory_item.item_class.title if s.inventory_item.item_class_id else "",
            "uom": s.inventory_item.uom.title if s.inventory_item.uom_id else "", "opening": open_q, "qty_in": qin, "qty_out": qout, "closing": closing,
            "on_hand": weight(s.current_quantity), "rate": money(s.current_price), "value": money(closing * (s.current_price or ZERO)),
            "last_movement": last_move, "idle_days": (end - last_move).days if last_move else None, "negative": closing < 0,
        })
    if below_zero_only:
        rows = [r for r in rows if r["negative"]]
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("opening", "qty_in", "qty_out", "closing", "on_hand", "value")}
    totals["items"] = len(rows)
    totals["negative"] = sum(1 for r in rows if r["negative"])
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 44. Stock Ageing / Slow Moving
# ---------------------------------------------------------------------------

def slow_moving(as_of, book="", item_class=None):
    rows = []
    if book in ("", "stores"):
        last = dict(ItemLedger.objects.filter(transaction_date__lte=as_of).values_list("inventory_item_id").annotate(last=Max("transaction_date")).values_list("inventory_item_id", "last"))
        stocks = Stock.objects.filter(status=STATUS_ACTIVE, current_quantity__gt=0).select_related("inventory_item__item_class")
        if item_class:
            stocks = stocks.filter(inventory_item__item_class_id=item_class)
        for s in stocks:
            moved = last.get(s.inventory_item_id)
            idle = (as_of - moved).days if moved else None
            rows.append({
                "book": "Stores", "item_id": s.inventory_item_id, "item": s.item_name, "category": s.inventory_item.item_class.title if s.inventory_item.item_class_id else "",
                "on_hand": weight(s.current_quantity), "rate": money(s.current_price), "value": money(s.current_quantity * (s.current_price or ZERO)),
                "last_movement": moved, "idle_days": idle, "bucket": _age_bucket(idle),
            })
    if book in ("", "mill") and not item_class:
        stock = {r["product_id"]: r for r in ProductLedger.objects.filter(entry_date__lte=as_of).values("product_id").annotate(q=_sum("quantity"), last=Max("entry_date"), last_out=Max("entry_date", filter=Q(quantity__lt=0)))}
        rates = {r.product_id: r.rate for r in ProductRate.objects.filter(is_current=True)}
        for p in ProductNode.objects.filter(pk__in=[k for k, v in stock.items() if v["q"] > 0]).select_related("parent"):
            s = stock[p.pk]
            moved = s["last_out"] or s["last"]
            idle = (as_of - moved).days if moved else None
            rows.append({
                "book": "Mill", "item_id": p.pk, "item": p.name, "category": _family_label(p.specification, p.parent.name if p.parent_id else ""),
                "on_hand": weight(s["q"]), "rate": money(rates.get(p.pk)), "value": money(s["q"] * rates.get(p.pk, ZERO)),
                "last_movement": moved, "idle_days": idle, "bucket": _age_bucket(idle),
            })
    rows = [r for r in rows if r["idle_days"] is None or r["idle_days"] >= 30]
    rows.sort(key=lambda r: -(r["idle_days"] or 10**6))
    totals = {"value": sum((r["value"] for r in rows), ZERO), "items": len(rows)}
    for key in ("30-59", "60-89", "90+"):
        totals[key] = sum((r["value"] for r in rows if r["bucket"] == key), ZERO)
    return {"rows": rows, "totals": totals}


def _age_bucket(idle):
    if idle is None:
        return "never"
    if idle < 30:
        return "<30"
    if idle < 60:
        return "30-59"
    if idle < 90:
        return "60-89"
    return "90+"


# ---------------------------------------------------------------------------
# 45. Stock Adjustment Register
# ---------------------------------------------------------------------------

def adjustment_register(start, end, item=None, user=None):
    qs = ManualTransaction.objects.filter(created_at__date__range=(start, end)).select_related("inventory_item", "supplier", "created_by")
    if item:
        qs = qs.filter(inventory_item_id=item)
    if user:
        qs = qs.filter(created_by_id=user)
    rows = [
        {
            "pk": m.pk, "date": m.created_at.date(), "transaction": m.transaction_id, "item_id": m.inventory_item_id, "item": m.item_name, "code": m.item_code,
            "qty": weight(m.qty), "qty_in": weight(m.qty) if m.qty > 0 else ZERO, "qty_out": weight(-m.qty) if m.qty < 0 else ZERO, "rate": money(m.price),
            "value": money(m.qty * m.price), "reason": m.descr, "supplier": m.supplier.name if m.supplier_id else "",
            "user": (m.created_by.get_full_name() or m.created_by.username) if m.created_by_id else "", "status": m.status, "status_label": m.get_status_display(),
        }
        for m in qs.order_by("-created_at")
    ]
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("qty_in", "qty_out", "value")}
    totals["entries"] = len(rows)
    return {"rows": rows, "totals": totals}


def adjusting_user_options():
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(pk__in=ManualTransaction.objects.values("created_by_id")).order_by("username")
    return [(u.pk, u.get_full_name() or u.username) for u in users]


def adjusted_item_options():
    return InventoryItem.objects.filter(pk__in=ManualTransaction.objects.values("inventory_item_id")).order_by("item_name").values_list("pk", "item_name")


# ---------------------------------------------------------------------------
# 46. Godown-wise Stock
# ---------------------------------------------------------------------------

def godown_stock(as_of):
    grouped = (
        ProductLedger.objects.filter(entry_date__lte=as_of).values("godown_id", "godown__name", "product__specification", "product__parent__name")
        .annotate(qty=_sum("quantity"), kg=_sum(F("quantity") * _unit_kg()))
    )
    rates = {r.product_id: r.rate for r in ProductRate.objects.filter(is_current=True)}
    values = {
        (r["godown_id"], r["product_id"]): r["qty"] for r in ProductLedger.objects.filter(entry_date__lte=as_of).values("godown_id", "product_id").annotate(qty=_sum("quantity"))
    }
    per_godown = defaultdict(lambda: {"wheat_kg": ZERO, "bardana": ZERO, "products_kg": ZERO, "families": defaultdict(Decimal), "value": ZERO})
    for r in grouped:
        g = per_godown[(r["godown_id"], r["godown__name"] or "—")]
        spec = r["product__specification"]
        if spec == PRD_SPEC_RAW_ITEM:
            g["wheat_kg"] += r["kg"]
        elif spec in PACKING:
            g["bardana"] += r["qty"]
        else:
            g["products_kg"] += r["kg"]
            g["families"][r["product__parent__name"] or "Products"] += r["kg"]
    names = dict(Godown.objects.values_list("pk", "name"))
    for (gid, pid), qty in values.items():
        per_godown[(gid, names.get(gid, "—") if gid else "—")]["value"] += qty * rates.get(pid, ZERO)
    rows = [
        {
            "godown_id": gid, "godown": name, "wheat_kg": weight(g["wheat_kg"]), "wheat_mund": mund(g["wheat_kg"]), "empty_bags": weight(g["bardana"]),
            "products_kg": weight(g["products_kg"]), "families": ", ".join(f"{k} {v:,.0f}" for k, v in sorted(g["families"].items(), key=lambda x: -x[1])),
            "value": money(g["value"]),
        }
        for (gid, name), g in per_godown.items()
    ]
    rows.sort(key=lambda r: r["godown"])
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("wheat_kg", "wheat_mund", "empty_bags", "products_kg", "value")}
    stores_value = Stock.objects.filter(status=STATUS_ACTIVE).aggregate(v=Coalesce(Sum(F("current_quantity") * F("current_price")), Value(Decimal("0")), output_field=MONEY))["v"]
    totals["stores_value"] = money(stores_value)
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 47. Wheat Stock in Days
# ---------------------------------------------------------------------------

def wheat_days_trend(as_of, days=30, window=30):
    """Day-wise wheat stock and days-of-cover: one opening aggregate, one daily ledger sum, one daily grinding sum."""
    from apps.production.models import GrindingVoucher

    first = as_of - timedelta(days=days - 1)
    wheat = ProductLedger.objects.filter(product__specification=PRD_SPEC_RAW_ITEM)
    opening = wheat.filter(entry_date__lt=first).aggregate(kg=_sum(F("quantity") * _unit_kg()))["kg"]
    daily = {r["entry_date"]: r["kg"] for r in wheat.filter(entry_date__range=(first, as_of)).values("entry_date").annotate(kg=_sum(F("quantity") * _unit_kg()))}
    ground = {r["date"]: r["kg"] for r in GrindingVoucher.objects.filter(date__range=(first - timedelta(days=window), as_of)).values("date").annotate(kg=_sum("disposal_wheat"))}
    rows = []
    stock = opening
    for back in range(days - 1, -1, -1):
        day = as_of - timedelta(days=back)
        stock += daily.get(day, ZERO)
        recent = sum((ground.get(day - timedelta(days=i), ZERO) for i in range(window)), ZERO)
        per_day = recent / window if recent else ZERO
        rows.append({
            "date": day, "stock_kg": weight(stock), "stock_mund": mund(stock), "ground_kg": weight(ground.get(day)), "per_day_kg": weight(per_day),
            "days": (stock / per_day).quantize(Decimal("0.1")) if per_day else None,
        })
    return {"rows": rows, "totals": {}, "latest": rows[-1], "first": rows[0]}
