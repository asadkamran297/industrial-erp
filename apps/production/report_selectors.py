"""Production reporting reads (catalogue group F). Grinding and conversion vouchers, product ledger rates."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.core.constants import (
    PRD_LEDGER_PURCHASE,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    PRD_SPEC_SERVICE_ITEM,
    PRD_SPEC_WAGE_ITEM,
    STATUS_ACTIVE,
)
from apps.core.reporting import GROUP_MONTH, ZERO, group_by, money, mund, period_label, weight
from apps.finance.models import AccountVoucherLine
from apps.godowns.models import Godown
from apps.products.models import ProductAccountLink, ProductLedger, ProductNode

from .models import GrindingOutput, GrindingVoucher, ProductConversion, ProductConversionLine

QTY = DecimalField(max_digits=16, decimal_places=3)
MONEY = DecimalField(max_digits=18, decimal_places=2)


def _sum(expression, field=QTY, **kw):
    return Coalesce(Sum(expression, **kw), Value(Decimal("0")), output_field=field)


def _pct(part, whole):
    return (Decimal(part or 0) / Decimal(whole) * 100).quantize(Decimal("0.01")) if whole else None


def godown_options():
    return Godown.objects.filter(status=STATUS_ACTIVE).order_by("name").values_list("pk", "name")


def preparer_options():
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(prepared_grinding_vouchers__isnull=False).distinct().order_by("username")
    return [(u.pk, u.get_full_name() or u.username) for u in users]


def output_product_options():
    return ProductNode.objects.filter(grinding_outputs__isnull=False).distinct().order_by("name").values_list("pk", "name")


def vouchers(start, end, godown=None, prepared_by=None):
    qs = GrindingVoucher.objects.filter(date__range=(start, end)).select_related("wheat_item", "godown", "prepared_by")
    if godown:
        qs = qs.filter(godown_id=godown)
    if prepared_by:
        qs = qs.filter(prepared_by_id=prepared_by)
    return qs


def outputs_by_voucher(voucher_ids):
    grouped = defaultdict(list)
    for o in GrindingOutput.objects.filter(voucher_id__in=voucher_ids).select_related("product").order_by("voucher_id", "line_number"):
        grouped[o.voucher_id].append(o)
    return grouped


def wheat_rate_per_kg(end):
    """Weighted average purchase rate per kg of wheat taken into the ledger up to ``end``."""
    row = ProductLedger.objects.filter(product__specification=PRD_SPEC_RAW_ITEM, source=PRD_LEDGER_PURCHASE, quantity__gt=0, rate__gt=0, entry_date__lte=end).aggregate(
        value=_sum(F("quantity") * F("rate"), MONEY), qty=_sum("quantity"),
    )
    return money(row["value"] / row["qty"]) if row["qty"] else ZERO


def bardana_rate_per_bag(end):
    row = ProductLedger.objects.filter(product__specification=PRD_SPEC_RAW_PACKING, source=PRD_LEDGER_PURCHASE, quantity__gt=0, rate__gt=0, entry_date__lte=end).aggregate(
        value=_sum(F("quantity") * F("rate"), MONEY), qty=_sum("quantity"),
    )
    return money(row["value"] / row["qty"]) if row["qty"] else ZERO


# ---------------------------------------------------------------------------
# 33. Grinding Register
# ---------------------------------------------------------------------------

def grinding_register(start, end, godown=None, prepared_by=None):
    qs = list(vouchers(start, end, godown, prepared_by).order_by("-date", "-seq_num"))
    outputs = outputs_by_voucher([v.pk for v in qs])
    rows = []
    for v in qs:
        lines = outputs.get(v.pk, [])
        per_product = ", ".join(f"{o.product.name} {o.quantity * o.unit_weight:,.0f}" for o in lines)
        rows.append({
            "pk": v.pk, "number": v.voucher_no, "date": v.date, "shift": f"{v.production_from:%H:%M}–{v.production_to:%H:%M}",
            "wheat": v.wheat_item.name, "godown": v.godown.name, "wheat_kg": weight(v.disposal_wheat), "wheat_mund": mund(v.disposal_wheat),
            "bags_issued": weight(v.disposal_bag_qty), "outputs": per_product, "output_kg": weight(v.total_output_kg),
            "yield_pct": v.yield_percent, "standard_pct": v.standard_yield_percent, "shortage_kg": weight(v.shortage_kg), "shortage_pct": v.shortage_percent,
            "below": bool(v.standard_yield_percent and v.yield_percent < v.standard_yield_percent),
            "prepared_by": (v.prepared_by.get_full_name() or v.prepared_by.username) if v.prepared_by_id else "",
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("wheat_kg", "wheat_mund", "bags_issued", "output_kg", "shortage_kg")}
    totals["vouchers"] = len(rows)
    totals["yield_pct"] = _pct(totals["output_kg"], totals["wheat_kg"]) or ZERO
    totals["shortage_pct"] = _pct(totals["shortage_kg"], totals["wheat_kg"]) or ZERO
    totals["below"] = sum(1 for r in rows if r["below"])
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 34. Daily Grinding (day-wise, downtime flagged)
# ---------------------------------------------------------------------------

def daily_grinding(start, end, godown=None):
    qs = vouchers(start, end, godown)
    by_day = {
        r["date"]: r for r in qs.values("date").annotate(runs=Count("id"), wheat=_sum("disposal_wheat"), output=_sum("total_output_kg"), shortage=_sum("shortage_kg"))
    }
    per_product = defaultdict(dict)
    for r in GrindingOutput.objects.filter(voucher__in=qs).values("voucher__date", "product__name").annotate(kg=_sum(F("quantity") * F("unit_weight"))):
        per_product[r["voucher__date"]][r["product__name"]] = r["kg"]
    products = sorted({name for d in per_product.values() for name in d})
    rows = []
    day = start
    while day <= end:
        r = by_day.get(day, {})
        wheat = weight(r.get("wheat"))
        output = weight(r.get("output"))
        rows.append({
            "date": day, "day": f"{day:%a}", "runs": r.get("runs", 0), "wheat_kg": wheat, "wheat_mund": mund(wheat), "output_kg": output,
            "yield_pct": _pct(output, wheat), "shortage_kg": weight(r.get("shortage")), "downtime": not r.get("runs"),
            "products": {name: weight(per_product.get(day, {}).get(name)) for name in products},
            "outputs": ", ".join(f"{name} {per_product[day][name]:,.0f}" for name in per_product.get(day, {})),
        })
        day += timedelta(days=1)
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("wheat_kg", "wheat_mund", "output_kg", "shortage_kg")}
    totals["runs"] = sum(r["runs"] for r in rows)
    totals["days"] = len(rows)
    totals["downtime_days"] = sum(1 for r in rows if r["downtime"])
    totals["yield_pct"] = _pct(totals["output_kg"], totals["wheat_kg"])
    return {"rows": rows, "totals": totals, "products": products}


# ---------------------------------------------------------------------------
# 35. Yield Trend
# ---------------------------------------------------------------------------

def yield_trend(start, end, group, window=7):
    grouped = (
        GrindingVoucher.objects.filter(date__range=(start, end)).annotate(period=group_by("date", group)).values("period")
        .annotate(runs=Count("id"), wheat=_sum("disposal_wheat"), output=_sum("total_output_kg"), standard=Coalesce(Sum(F("standard_yield_percent") * F("disposal_wheat")), Value(Decimal("0")), output_field=QTY))
        .order_by("period")
    )
    rows = []
    history = []
    for r in grouped:
        wheat, output = weight(r["wheat"]), weight(r["output"])
        y = _pct(output, wheat)
        standard = (r["standard"] / wheat).quantize(Decimal("0.01")) if wheat else None
        history.append((output, wheat))
        recent = history[-window:]
        moving = _pct(sum(o for o, _ in recent), sum(w for _, w in recent))
        rows.append({
            "period": r["period"], "label": period_label(r["period"], group), "runs": r["runs"], "wheat_kg": wheat, "output_kg": output,
            "yield_pct": y, "standard_pct": standard, "variance_pct": (y - standard).quantize(Decimal("0.01")) if y is not None and standard is not None else None,
            "moving_avg": moving, "below": bool(y is not None and standard is not None and y < standard),
        })
    days = (
        GrindingVoucher.objects.filter(date__range=(start, end)).values("date").annotate(wheat=_sum("disposal_wheat"), output=_sum("total_output_kg"))
    )
    day_yields = [(d["date"], _pct(d["output"], d["wheat"])) for d in days if d["wheat"]]
    best = max(day_yields, key=lambda x: x[1]) if day_yields else None
    worst = min(day_yields, key=lambda x: x[1]) if day_yields else None
    totals = {"wheat_kg": sum((r["wheat_kg"] for r in rows), ZERO), "output_kg": sum((r["output_kg"] for r in rows), ZERO), "runs": sum(r["runs"] for r in rows)}
    totals["yield_pct"] = _pct(totals["output_kg"], totals["wheat_kg"])
    return {"rows": rows, "totals": totals, "best": best, "worst": worst}


# ---------------------------------------------------------------------------
# 36. Product Output Mix
# ---------------------------------------------------------------------------

def output_mix(start, end, godown=None):
    qs = vouchers(start, end, godown)
    wheat = qs.aggregate(kg=_sum("disposal_wheat"))["kg"]
    grouped = (
        GrindingOutput.objects.filter(voucher__in=qs).values("product_id", "product__name", "product__parent__name", "product__standard_yield_percent", "product__specification")
        .annotate(kg=_sum(F("quantity") * F("unit_weight")), units=_sum("quantity"), runs=Count("voucher", distinct=True)).order_by("-kg")
    )
    total_kg = sum((r["kg"] for r in grouped), ZERO)
    rows = []
    for r in grouped:
        share = _pct(r["kg"], total_kg)
        of_wheat = _pct(r["kg"], wheat)
        target = r["product__standard_yield_percent"] or None
        rows.append({
            "product_id": r["product_id"], "product": r["product__name"], "family": r["product__parent__name"] or "", "runs": r["runs"],
            "units": weight(r["units"]), "kg": weight(r["kg"]), "share_pct": share, "of_wheat_pct": of_wheat, "target_pct": target,
            "variance_pct": (of_wheat - target).quantize(Decimal("0.01")) if of_wheat is not None and target else None,
        })
    totals = {"units": sum((r["units"] for r in rows), ZERO), "kg": weight(total_kg), "wheat_kg": weight(wheat), "share_pct": Decimal("100.00") if rows else ZERO, "of_wheat_pct": _pct(total_kg, wheat)}
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 37. Shortage / Refraction
# ---------------------------------------------------------------------------

def shortage_report(start, end, threshold=None):
    rate = wheat_rate_per_kg(end)
    rows = []
    for v in vouchers(start, end).order_by("-date", "-seq_num"):
        standard_shortage = (v.disposal_wheat * (100 - v.standard_yield_percent) / 100).quantize(Decimal("0.001")) if v.standard_yield_percent else ZERO
        excess = weight(v.shortage_kg - standard_shortage)
        if threshold is not None and v.shortage_percent < threshold:
            continue
        rows.append({
            "pk": v.pk, "number": v.voucher_no, "date": v.date, "wheat": v.wheat_item.name, "wheat_kg": weight(v.disposal_wheat), "output_kg": weight(v.total_output_kg),
            "shortage_kg": weight(v.shortage_kg), "shortage_pct": v.shortage_percent, "standard_shortage_kg": standard_shortage, "excess_kg": excess,
            "beyond": excess > 0, "cost": money(v.shortage_kg * rate), "excess_cost": money(max(excess, ZERO) * rate),
            "prepared_by": (v.prepared_by.get_full_name() or v.prepared_by.username) if v.prepared_by_id else "",
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("wheat_kg", "output_kg", "shortage_kg", "standard_shortage_kg", "excess_kg", "cost", "excess_cost")}
    totals["shortage_pct"] = _pct(totals["shortage_kg"], totals["wheat_kg"])
    totals["vouchers"] = len(rows)
    totals["beyond"] = sum(1 for r in rows if r["beyond"])
    totals["rate"] = rate
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 38. Product Conversion Register
# ---------------------------------------------------------------------------

def conversion_register(start, end, product=None, godown=None):
    qs = ProductConversion.objects.filter(date__range=(start, end)).select_related("source_product", "godown", "prepared_by")
    if godown:
        qs = qs.filter(godown_id=godown)
    if product:
        qs = qs.filter(Q(source_product_id=product) | Q(outputs__product_id=product)).distinct()
    lines = defaultdict(list)
    for line in ProductConversionLine.objects.filter(conversion__in=qs).select_related("product").order_by("conversion_id", "line_number"):
        lines[line.conversion_id].append(line)
    rows = []
    for c in qs.order_by("-date", "-seq_num"):
        outs = lines.get(c.pk, [])
        source_kg = weight(c.source_quantity * c.source_unit_weight)
        rows.append({
            "pk": c.pk, "number": c.voucher_no, "date": c.date, "from_product": c.source_product.name, "from_units": weight(c.source_quantity), "from_kg": source_kg,
            "to_products": ", ".join(f"{o.product.name} {o.quantity:,.0f}" for o in outs), "to_units": weight(sum((o.quantity for o in outs), ZERO)),
            "to_kg": weight(c.total_output_kg), "variance_kg": weight(c.total_output_kg - source_kg), "godown": c.godown.name if c.godown_id else "—",
            "prepared_by": (c.prepared_by.get_full_name() or c.prepared_by.username) if c.prepared_by_id else "",
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("from_units", "from_kg", "to_units", "to_kg", "variance_kg")}
    totals["conversions"] = len(rows)
    return {"rows": rows, "totals": totals}


def conversion_product_options():
    return ProductNode.objects.filter(Q(conversion_sources__isnull=False) | Q(conversion_outputs__isnull=False)).distinct().order_by("name").values_list("pk", "name")


# ---------------------------------------------------------------------------
# 39. Production Cost per Bag
# ---------------------------------------------------------------------------

def direct_expense_codes():
    return list(ProductAccountLink.objects.filter(product__specification__in=(PRD_SPEC_SERVICE_ITEM, PRD_SPEC_WAGE_ITEM)).values_list("purchase_account__code", flat=True))


def cost_per_bag(start, end):
    qs = vouchers(start, end)
    wheat_kg = qs.aggregate(kg=_sum("disposal_wheat"))["kg"]
    wheat_rate = wheat_rate_per_kg(end)
    bag_rate = bardana_rate_per_bag(end)
    codes = direct_expense_codes()
    expenses = AccountVoucherLine.objects.filter(account_no__in=codes, voucher_date__range=(start, end)).aggregate(
        amount=Coalesce(Sum(F("debit_amount") - F("credit_amount")), Value(Decimal("0")), output_field=MONEY),
    )["amount"] if codes else ZERO
    grouped = (
        GrindingOutput.objects.filter(voucher__in=qs).values("product_id", "product__name", "product__parent__name")
        .annotate(units=_sum("quantity"), kg=_sum(F("quantity") * F("unit_weight")), bags=_sum("pack_qty")).order_by("-kg")
    )
    total_out = sum((r["kg"] for r in grouped), ZERO)
    wheat_cost = money(wheat_kg * wheat_rate)
    rows = []
    for r in grouped:
        share = (r["kg"] / total_out) if total_out else ZERO
        w = money(wheat_cost * share)
        b = money(r["bags"] * bag_rate)
        e = money(expenses * share)
        total = money(w + b + e)
        units = weight(r["units"])
        rows.append({
            "product_id": r["product_id"], "product": r["product__name"], "family": r["product__parent__name"] or "", "units": units, "kg": weight(r["kg"]),
            "share_pct": (share * 100).quantize(Decimal("0.01")), "wheat_cost": w, "bardana_cost": b, "expense_cost": e, "total_cost": total,
            "cost_per_bag": money(total / units) if units else ZERO, "cost_per_kg": money(total / r["kg"]) if r["kg"] else ZERO,
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("units", "kg", "wheat_cost", "bardana_cost", "expense_cost", "total_cost")}
    totals["cost_per_bag"] = money(totals["total_cost"] / totals["units"]) if totals["units"] else ZERO
    totals["cost_per_kg"] = money(totals["total_cost"] / totals["kg"]) if totals["kg"] else ZERO
    totals.update({"wheat_kg": weight(wheat_kg), "wheat_rate": wheat_rate, "bag_rate": bag_rate, "expenses": money(expenses), "expense_accounts": len(codes)})
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 40. Production Summary (period-wise consolidated)
# ---------------------------------------------------------------------------

def production_summary(start, end, group=GROUP_MONTH, godown=None):
    qs = vouchers(start, end, godown)
    by_period = {
        r["period"]: r for r in qs.annotate(period=group_by("date", group)).values("period")
        .annotate(runs=Count("id"), days=Count("date", distinct=True), wheat=_sum("disposal_wheat"), bags=_sum("disposal_bag_qty"), output=_sum("total_output_kg"), shortage=_sum("shortage_kg"))
    }
    per_family = defaultdict(lambda: defaultdict(Decimal))
    for r in GrindingOutput.objects.filter(voucher__in=qs).annotate(period=group_by("voucher__date", group)).values("period", "product__parent__name").annotate(kg=_sum(F("quantity") * F("unit_weight"))):
        per_family[r["period"]][r["product__parent__name"] or "—"] += r["kg"]
    rows = []
    for key in sorted(by_period):
        r = by_period[key]
        wheat, output = weight(r["wheat"]), weight(r["output"])
        rows.append({
            "period": key, "label": period_label(key, group), "runs": r["runs"], "days": r["days"], "wheat_kg": wheat, "wheat_mund": mund(wheat),
            "bags_issued": weight(r["bags"]), "output_kg": output, "yield_pct": _pct(output, wheat), "shortage_kg": weight(r["shortage"]),
            "shortage_pct": _pct(r["shortage"], wheat), "per_day_kg": weight(wheat / r["days"]) if r["days"] else ZERO,
            "families": ", ".join(f"{name} {kg:,.0f}" for name, kg in sorted(per_family.get(key, {}).items(), key=lambda x: -x[1])),
        })
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("wheat_kg", "wheat_mund", "bags_issued", "output_kg", "shortage_kg")}
    totals["runs"] = sum(r["runs"] for r in rows)
    totals["days"] = sum(r["days"] for r in rows)
    totals["yield_pct"] = _pct(totals["output_kg"], totals["wheat_kg"])
    totals["shortage_pct"] = _pct(totals["shortage_kg"], totals["wheat_kg"])
    return {"rows": rows, "totals": totals}
