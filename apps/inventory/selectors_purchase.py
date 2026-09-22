"""Purchase reporting reads (catalogue group C). Posted invoices, orders and returns; nothing here writes."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.core.constants import (
    INV_ORDER_OPEN_STATUSES,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    STATUS_ACTIVE,
    STATUS_POSTED,
    YES,
)
from apps.core.reporting import ZERO, group_by, money, mund, period_label, weight
from apps.finance.models import ChartOfAccount
from apps.products.models import PartyBardanaLedger

from .models import (
    InventoryClass, InventoryItem, PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrder, PurchaseReturnMaster, Supplier,
)

MONEY = DecimalField(max_digits=18, decimal_places=2)
QTY = DecimalField(max_digits=18, decimal_places=3)


def _sum(expression, field=MONEY):
    return Coalesce(Sum(expression), Value(Decimal("0")), output_field=field)


def _pct(part, whole):
    return (Decimal(part or 0) / Decimal(whole) * 100).quantize(Decimal("0.01")) if whole else None


def posted_invoices(start, end, supplier=None):
    invoices = PurchaseInvoice.objects.filter(status=STATUS_POSTED, invoice_date__range=(start, end))
    return invoices.filter(supplier_id=supplier) if supplier else invoices


def wheat_lines(start, end, supplier=None):
    lines = PurchaseInvoiceLine.objects.filter(
        invoice__status=STATUS_POSTED, invoice__invoice_date__range=(start, end), product__specification=PRD_SPEC_RAW_ITEM,
    )
    return lines.filter(invoice__supplier_id=supplier) if supplier else lines


def supplier_options():
    return Supplier.objects.filter(status=STATUS_ACTIVE).values_list("pk", "name")


def wheat_supplier_options():
    return Supplier.objects.filter(status=STATUS_ACTIVE, purchaseinvoice__items__product__specification=PRD_SPEC_RAW_ITEM).distinct().values_list("pk", "name")


def broker_options():
    return ChartOfAccount.objects.filter(broker_purchase_invoices__isnull=False).distinct().order_by("title").values_list("pk", "title")


def vehicle_options():
    return [(v, v) for v in PurchaseInvoice.objects.exclude(vehicle_no="").order_by("vehicle_no").values_list("vehicle_no", flat=True).distinct()]


def class_options():
    return InventoryClass.objects.filter(status=STATUS_ACTIVE).order_by("title").values_list("pk", "title")


def item_options():
    return InventoryItem.objects.filter(status=STATUS_ACTIVE, purchaseinvoiceline__isnull=False).distinct().order_by("item_name").values_list("pk", "item_name")


WEIGHT_SOURCE_CHOICES = (("party", "Party weight"), ("mill", "Mill weight"))


def _weight_source(line):
    if line.selected_weight is None:
        return ""
    if line.mill_weight is not None and line.selected_weight == line.mill_weight:
        return "Mill"
    if line.party_weight is not None and line.selected_weight == line.party_weight:
        return "Party"
    return ""


# ---------------------------------------------------------------------------
# 14. Wheat Purchase Register
# ---------------------------------------------------------------------------

def _slip_row(line):
    inv = line.invoice
    credit = line.credit_weight or ZERO
    return {
        "pk": inv.pk,
        "number": inv.invoice_num,
        "date": inv.invoice_date,
        "supplier_id": inv.supplier_id,
        "supplier": inv.supplier.name,
        "vehicle": inv.vehicle_no,
        "broker": inv.broker.title if inv.broker_id else "",
        "product": line.product.name,
        "party_weight": weight(line.party_weight) if line.party_weight is not None else None,
        "mill_weight": weight(line.mill_weight) if line.mill_weight is not None else None,
        "selected_weight": weight(line.selected_weight) if line.selected_weight is not None else None,
        "weight_source": _weight_source(line),
        "katla": weight(line.katla) if line.katla is not None else None,
        "impurities": weight(line.khoot) if line.khoot is not None else None,
        "moisture": weight(line.moisture) if line.moisture is not None else None,
        "sack_deduction": weight(line.sack_weight_deduction) if line.sack_weight_deduction is not None else None,
        "credit_kg": weight(credit),
        "credit_mund": mund(credit),
        "rate_per_mund": money(line.rate_per_mund) if line.rate_per_mund is not None else money(line.rate * 40),
        "goods_amount": money(line.amount),
        "freight": money(inv.freight_amount),
        "freight_payer": "Mill" if inv.freight_paid_by_mill else "Supplier",
        "brokerage": money(inv.brokerage_amount),
        "brokerage_bearer": "Supplier" if inv.brokerage_borne_by_supplier else "Mill",
        "wht": money(inv.withholding_amount),
        "net_payable": money(inv.supplier_payable_amount),
        "paid": money(inv.paid_amount),
        "balance": money(inv.balance_amount),
        "status": inv.status,
        "status_label": inv.get_status_display(),
    }


def wheat_register(start, end, supplier=None, vehicle="", broker=None, weight_source="", status=""):
    lines = wheat_lines(start, end, supplier).select_related("invoice__supplier", "invoice__broker", "product")
    if vehicle:
        lines = lines.filter(invoice__vehicle_no=vehicle)
    if broker:
        lines = lines.filter(invoice__broker_id=broker)
    if status:
        lines = PurchaseInvoiceLine.objects.filter(
            invoice__status=status, invoice__invoice_date__range=(start, end), product__specification=PRD_SPEC_RAW_ITEM,
        ).select_related("invoice__supplier", "invoice__broker", "product")
        if supplier:
            lines = lines.filter(invoice__supplier_id=supplier)
    rows = [_slip_row(line) for line in lines.order_by("-invoice__invoice_date", "-invoice_id")]
    if weight_source:
        rows = [row for row in rows if row["weight_source"].lower() == weight_source]
    totals = {key: sum((row[key] or ZERO for row in rows), ZERO) for key in ("credit_kg", "credit_mund", "goods_amount", "freight", "brokerage", "wht", "net_payable", "paid", "balance")}
    totals["slips"] = len(rows)
    totals["rate_per_mund"] = money(totals["goods_amount"] / totals["credit_mund"]) if totals["credit_mund"] else ZERO
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 15. Purchase Summary
# ---------------------------------------------------------------------------

def purchase_summary(start, end, group, supplier=None):
    by_line = {
        row["period"]: row for row in wheat_lines(start, end, supplier).annotate(period=group_by("invoice__invoice_date", group)).values("period")
        .annotate(kg=_sum("credit_weight", QTY), goods=_sum("amount"), slips=Count("invoice", distinct=True))
    }
    by_inv = {
        row["period"]: row for row in posted_invoices(start, end, supplier).filter(pk__in=wheat_lines(start, end, supplier).values("invoice_id"))
        .annotate(period=group_by("invoice_date", group)).values("period")
        .annotate(freight=_sum("freight_amount"), brokerage=_sum("brokerage_amount"), wht=_sum("withholding_amount"), total=_sum("total_amount"), paid=_sum("paid_amount"))
    }
    rows = []
    for key in sorted(by_line):
        l, i = by_line[key], by_inv.get(key, {})
        kg = weight(l["kg"])
        goods = money(l["goods"])
        rows.append({
            "period": key, "label": period_label(key, group), "slips": l["slips"], "kg": kg, "mund": mund(kg),
            "avg_rate": money(goods / mund(kg)) if kg else ZERO, "amount": goods,
            "freight": money(i.get("freight")), "brokerage": money(i.get("brokerage")), "wht": money(i.get("wht")),
            "total": money(i.get("total")), "paid": money(i.get("paid")), "balance": money((i.get("total") or ZERO) - (i.get("paid") or ZERO)),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("kg", "mund", "amount", "freight", "brokerage", "wht", "total", "paid", "balance")}
    totals["slips"] = sum(row["slips"] for row in rows)
    totals["avg_rate"] = money(totals["amount"] / totals["mund"]) if totals["mund"] else ZERO
    return {"rows": rows, "totals": totals}


def purchase_totals(start, end):
    row = wheat_lines(start, end).aggregate(kg=_sum("credit_weight", QTY), goods=_sum("amount"), slips=Count("invoice", distinct=True))
    kg = weight(row["kg"])
    return {"slips": row["slips"], "kg": kg, "mund": mund(kg), "amount": money(row["goods"]), "avg_rate": money(row["goods"] / mund(kg)) if kg else ZERO}


# ---------------------------------------------------------------------------
# 16. Arhti-wise Purchase
# ---------------------------------------------------------------------------

def sacks_held_by_party():
    return {row["party_id"]: row["qty"] for row in PartyBardanaLedger.objects.values("party_id").annotate(qty=_sum("quantity", QTY))}


def supplier_purchases(start, end, supplier=None):
    lines = (
        wheat_lines(start, end, supplier).values("invoice__supplier_id", "invoice__supplier__name")
        .annotate(
            slips=Count("invoice", distinct=True), kg=_sum("credit_weight", QTY), goods=_sum("amount"),
            impurities=_sum("khoot", QTY), moisture=_sum("moisture", QTY), weighed=_sum("selected_weight", QTY),
        ).order_by("-goods")
    )
    invoices = {
        row["supplier_id"]: row for row in posted_invoices(start, end, supplier).filter(pk__in=wheat_lines(start, end, supplier).values("invoice_id"))
        .values("supplier_id").annotate(total=_sum("total_amount"), paid=_sum("paid_amount"), wht=_sum("withholding_amount"))
    }
    sacks = sacks_held_by_party()
    rows = []
    for line in lines:
        sid = line["invoice__supplier_id"]
        inv = invoices.get(sid, {})
        kg = weight(line["kg"])
        goods = money(line["goods"])
        rows.append({
            "supplier_id": sid, "supplier": line["invoice__supplier__name"], "slips": line["slips"], "kg": kg, "mund": mund(kg),
            "avg_rate": money(goods / mund(kg)) if kg else ZERO, "amount": goods, "wht": money(inv.get("wht")),
            "paid": money(inv.get("paid")), "balance": money((inv.get("total") or ZERO) - (inv.get("paid") or ZERO)),
            "avg_impurities": _pct(line["impurities"], line["weighed"]), "avg_moisture": _pct(line["moisture"], line["weighed"]),
            "sacks_held": weight(sacks.get(sid)),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("kg", "mund", "amount", "wht", "paid", "balance", "sacks_held")}
    totals["slips"] = sum(row["slips"] for row in rows)
    totals["avg_rate"] = money(totals["amount"] / totals["mund"]) if totals["mund"] else ZERO
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 17. Wheat Quality
# ---------------------------------------------------------------------------

def wheat_quality(start, end, supplier=None, threshold=None):
    lines = wheat_lines(start, end, supplier).select_related("invoice__supplier", "product").order_by("-invoice__invoice_date", "-invoice_id")
    rows = []
    for line in lines:
        base = line.selected_weight or ZERO
        imp = _pct(line.khoot, base)
        moist = _pct(line.moisture, base)
        deductions = weight((line.katla or ZERO) + (line.khoot or ZERO) + (line.moisture or ZERO) + (line.sack_weight_deduction or ZERO))
        flagged = threshold is not None and ((imp or ZERO) > threshold or (moist or ZERO) > threshold)
        rows.append({
            "pk": line.invoice_id, "number": line.invoice.invoice_num, "date": line.invoice.invoice_date,
            "supplier_id": line.invoice.supplier_id, "supplier": line.invoice.supplier.name, "vehicle": line.invoice.vehicle_no,
            "weight": weight(base), "katla": weight(line.katla), "impurities_kg": weight(line.khoot), "impurities": imp,
            "moisture_kg": weight(line.moisture), "moisture": moist, "sack_deduction": weight(line.sack_weight_deduction),
            "deductions": deductions, "deduction_pct": _pct(deductions, base), "credit_kg": weight(line.credit_weight), "flagged": flagged,
        })
    by_supplier = defaultdict(lambda: {"weight": ZERO, "impurities_kg": ZERO, "moisture_kg": ZERO})
    for row in rows:
        s = by_supplier[row["supplier"]]
        for key in ("weight", "impurities_kg", "moisture_kg"):
            s[key] += row[key]
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("weight", "katla", "impurities_kg", "moisture_kg", "sack_deduction", "deductions", "credit_kg")}
    totals["impurities"] = _pct(totals["impurities_kg"], totals["weight"])
    totals["moisture"] = _pct(totals["moisture_kg"], totals["weight"])
    totals["deduction_pct"] = _pct(totals["deductions"], totals["weight"])
    totals["flagged"] = sum(1 for row in rows if row["flagged"])
    totals["slips"] = len(rows)
    averages = [
        {"supplier": name, "impurities": _pct(s["impurities_kg"], s["weight"]), "moisture": _pct(s["moisture_kg"], s["weight"])}
        for name, s in by_supplier.items()
    ]
    return {"rows": rows, "totals": totals, "averages": averages}


# ---------------------------------------------------------------------------
# 18. Rate Trend
# ---------------------------------------------------------------------------

def rate_trend(start, end, group):
    rows = []
    grouped = (
        wheat_lines(start, end).annotate(period=group_by("invoice__invoice_date", group)).values("period")
        .annotate(kg=_sum("credit_weight", QTY), goods=_sum("amount"), slips=Count("invoice", distinct=True),
                  min_rate=Min("rate_per_mund"), max_rate=Max("rate_per_mund"))
        .order_by("period")
    )
    for row in grouped:
        kg = weight(row["kg"])
        goods = money(row["goods"])
        rows.append({
            "period": row["period"], "label": period_label(row["period"], group), "slips": row["slips"], "mund": mund(kg), "kg": kg,
            "avg_rate": money(goods / mund(kg)) if kg else ZERO, "min_rate": money(row["min_rate"]) if row["min_rate"] is not None else None,
            "max_rate": money(row["max_rate"]) if row["max_rate"] is not None else None, "amount": goods,
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("mund", "kg", "amount")}
    totals["slips"] = sum(row["slips"] for row in rows)
    totals["avg_rate"] = money(totals["amount"] / totals["mund"]) if totals["mund"] else ZERO
    rates = [row["avg_rate"] for row in rows if row["avg_rate"]]
    totals["min_rate"] = min(rates) if rates else ZERO
    totals["max_rate"] = max(rates) if rates else ZERO
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 19. Freight & Brokerage
# ---------------------------------------------------------------------------

def freight_brokerage(start, end, supplier=None, broker=None):
    invoices = posted_invoices(start, end, supplier).filter(Q(freight_amount__gt=0) | Q(brokerage_amount__gt=0)).select_related("supplier", "broker")
    if broker:
        invoices = invoices.filter(broker_id=broker)
    kg_by_invoice = {
        row["invoice_id"]: row["kg"] for row in PurchaseInvoiceLine.objects.filter(invoice__in=invoices).values("invoice_id").annotate(kg=_sum("credit_weight", QTY))
    }
    rows = []
    for inv in invoices.order_by("-invoice_date", "-id"):
        rows.append({
            "pk": inv.pk, "number": inv.invoice_num, "date": inv.invoice_date, "supplier_id": inv.supplier_id, "supplier": inv.supplier.name,
            "vehicle": inv.vehicle_no, "broker": inv.broker.title if inv.broker_id else "", "credit_mund": mund(kg_by_invoice.get(inv.pk)),
            "freight": money(inv.freight_amount), "freight_payer": "Mill" if inv.freight_paid_by_mill else "Supplier",
            "freight_mill": money(inv.freight_amount) if inv.freight_paid_by_mill else ZERO,
            "freight_supplier": ZERO if inv.freight_paid_by_mill else money(inv.freight_amount),
            "brokerage_rate": money(inv.brokerage_rate_per_100kg), "brokerage": money(inv.brokerage_amount),
            "brokerage_bearer": "Supplier" if inv.brokerage_borne_by_supplier else "Mill",
            "brokerage_mill": ZERO if inv.brokerage_borne_by_supplier else money(inv.brokerage_amount),
            "brokerage_supplier": money(inv.brokerage_amount) if inv.brokerage_borne_by_supplier else ZERO,
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("credit_mund", "freight", "freight_mill", "freight_supplier", "brokerage", "brokerage_mill", "brokerage_supplier")}
    totals["invoices"] = len(rows)
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 20. WHT Register
# ---------------------------------------------------------------------------

def wht_register(start, end, supplier=None):
    invoices = posted_invoices(start, end, supplier).filter(withholding_amount__gt=0).select_related("supplier")
    kg_by_invoice = {
        row["invoice_id"]: row["kg"] for row in PurchaseInvoiceLine.objects.filter(invoice__in=invoices).values("invoice_id").annotate(kg=_sum("credit_weight", QTY))
    }
    rows = [
        {
            "pk": inv.pk, "number": inv.invoice_num, "date": inv.invoice_date, "month": f"{inv.invoice_date:%b %Y}",
            "supplier_id": inv.supplier_id, "supplier": inv.supplier.name, "ntn": inv.supplier.ntn_number, "cnic": inv.supplier.sale_tax_num,
            "credit_mund": mund(kg_by_invoice.get(inv.pk)), "goods_amount": money(inv.goods_amount), "rate": money(inv.withholding_rate_per_40kg),
            "wht": money(inv.withholding_amount),
        }
        for inv in invoices.order_by("-invoice_date", "-id")
    ]
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("credit_mund", "goods_amount", "wht")}
    totals["invoices"] = len(rows)
    by_month = defaultdict(lambda: ZERO)
    for row in rows:
        by_month[row["month"]] += row["wht"]
    return {"rows": rows, "totals": totals, "by_month": dict(by_month)}


# ---------------------------------------------------------------------------
# 21. Stores Purchase Register
# ---------------------------------------------------------------------------

def stores_register(start, end, supplier=None, item_class=None, item=None):
    lines = PurchaseInvoiceLine.objects.filter(
        invoice__status=STATUS_POSTED, invoice__invoice_date__range=(start, end), inventory_item__isnull=False,
    ).select_related("invoice__supplier", "invoice__purchase_order", "inventory_item__item_class", "uom")
    if supplier:
        lines = lines.filter(invoice__supplier_id=supplier)
    if item_class:
        lines = lines.filter(inventory_item__item_class_id=item_class)
    if item:
        lines = lines.filter(inventory_item_id=item)
    rows = []
    for line in lines.order_by("-invoice__invoice_date", "-invoice_id", "seq_num"):
        inv = line.invoice
        rows.append({
            "pk": inv.pk, "number": inv.invoice_num, "date": inv.invoice_date, "supplier_id": inv.supplier_id, "supplier": inv.supplier.name,
            "supplier_invoice": inv.supplier_invoice_num, "item_id": line.inventory_item_id, "item": line.inventory_item.item_name,
            "category": line.inventory_item.item_class.title if line.inventory_item.item_class_id else "", "uom": line.uom.title if line.uom_id else "",
            "qty": weight(line.quantity), "rate": money(line.rate), "amount": money(line.amount), "tax": money(line.tax_amount), "discount": money(line.discount_amount),
            "po_pk": inv.purchase_order_id, "po": inv.purchase_order.purchase_num if inv.purchase_order_id else "",
            "match": ("Against order" if line.purchase_order_item_id else "Direct"),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("qty", "amount", "tax", "discount")}
    totals["lines"] = len(rows)
    totals["invoices"] = len({row["pk"] for row in rows})
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 22. Purchase Orders — Pending / Fulfilment
# ---------------------------------------------------------------------------

def order_fulfilment(start, end, supplier=None, status="", as_of=None):
    orders = PurchaseOrder.objects.filter(purchase_date__range=(start, end)).select_related("supplier").prefetch_related("items")
    if supplier:
        orders = orders.filter(supplier_id=supplier)
    orders = orders.filter(status=status) if status else orders.exclude(status="draft")
    rows = []
    for po in orders.order_by("-purchase_date", "-id"):
        items = list(po.items.all())
        ordered = sum((i.quantity for i in items), ZERO)
        invoiced = sum((i.qty_invoiced or ZERO for i in items), ZERO)
        value = sum((i.quantity * i.rate for i in items), ZERO)
        pending = max(ordered - invoiced, ZERO)
        rows.append({
            "pk": po.pk, "number": po.purchase_num, "date": po.purchase_date, "expected": po.expected_date, "supplier_id": po.supplier_id,
            "supplier": po.supplier.name, "lines": len(items), "ordered": weight(ordered), "invoiced": weight(invoiced), "pending": weight(pending),
            "fulfilled_pct": _pct(invoiced, ordered), "value": money(value), "pending_value": money(value * pending / ordered) if ordered else ZERO,
            "age": (as_of - po.purchase_date).days if as_of else None, "overdue": bool(po.expected_date and as_of and pending and po.expected_date < as_of),
            "status": po.status, "status_label": po.get_status_display(),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("ordered", "invoiced", "pending", "value", "pending_value")}
    totals["orders"] = len(rows)
    totals["open"] = sum(1 for row in rows if row["status"] in INV_ORDER_OPEN_STATUSES)
    totals["overdue"] = sum(1 for row in rows if row["overdue"])
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 23. Purchase Returns
# ---------------------------------------------------------------------------

def purchase_returns(start, end, supplier=None, item=None):
    returns = PurchaseReturnMaster.objects.filter(posted=YES, return_date__range=(start, end)).select_related("supplier", "purchase_invoice").prefetch_related("items__inventory_item")
    if supplier:
        returns = returns.filter(supplier_id=supplier)
    if item:
        returns = returns.filter(items__inventory_item_id=item).distinct()
    rows = []
    for ret in returns.order_by("-return_date", "-id"):
        items = list(ret.items.all())
        names = [i.item_name for i in items]
        rows.append({
            "pk": ret.pk, "number": ret.return_num, "date": ret.return_date, "supplier_id": ret.supplier_id, "supplier": ret.supplier.name,
            "invoice_pk": ret.purchase_invoice_id, "invoice": ret.purchase_invoice.invoice_num, "invoice_date": ret.purchase_invoice.invoice_date,
            "items": ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else ""), "qty": weight(sum((i.quantity for i in items), ZERO)),
            "invoice_amount": money(ret.total_purchase_amount), "returned": money(ret.returned_amount), "adjusted": money(ret.adjusted_amount),
            "remarks": ret.remarks, "status": ret.status, "status_label": ret.get_status_display(),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("qty", "invoice_amount", "returned", "adjusted")}
    totals["returns"] = len(rows)
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 24. Supplier Payment Status
# ---------------------------------------------------------------------------

def supplier_payment_status(as_of, kind=""):
    from apps.portal.selectors import _party_balances_as_of, supplier_kind_flags

    suppliers = Supplier.objects.filter(status=STATUS_ACTIVE).annotate(**supplier_kind_flags())
    if kind:
        suppliers = suppliers.filter(**{f"is_{kind}": True})
    suppliers = list(suppliers)
    ids = [s.pk for s in suppliers]
    balances = _party_balances_as_of(suppliers, "name", as_of)
    invoiced = {
        row["supplier_id"]: row for row in PurchaseInvoice.objects.filter(status=STATUS_POSTED, invoice_date__lte=as_of, supplier_id__in=ids)
        .values("supplier_id").annotate(total=_sum("total_amount"), paid=_sum("paid_amount"), count=Count("id"), last=Max("invoice_date"))
    }
    unpaid = defaultdict(list)
    for sid, day, due, total, paid in PurchaseInvoice.objects.filter(status=STATUS_POSTED, invoice_date__lte=as_of, supplier_id__in=ids).order_by("invoice_date").values_list("supplier_id", "invoice_date", "due_date", "total_amount", "paid_amount"):
        if (total or ZERO) - (paid or ZERO) > 0:
            unpaid[sid].append((day, due))
    rows = []
    for s in suppliers:
        balance = balances.get(s.pk, ZERO)
        inv = invoiced.get(s.pk, {})
        if balance <= 0 and not inv:
            continue
        open_docs = unpaid.get(s.pk, [])
        due_soon = sum(1 for _d, due in open_docs if due and as_of <= due <= as_of + timedelta(days=7))
        rows.append({
            "supplier_id": s.pk, "supplier": s.name, "kind": ", ".join(label for key, label in (("arhti", "Arhti"), ("bardana", "Bardana"), ("stores", "Stores")) if getattr(s, f"is_{key}")),
            "invoices": inv.get("count", 0), "invoiced": money(inv.get("total")), "paid": money(inv.get("paid")), "balance": balance,
            "oldest_unpaid": open_docs[0][0] if open_docs else None, "days_outstanding": (as_of - open_docs[0][0]).days if open_docs else None,
            "due_in_7": due_soon, "last_invoice": inv.get("last"),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("invoiced", "paid", "balance")}
    totals["suppliers"] = len(rows)
    totals["due_in_7"] = sum(row["due_in_7"] for row in rows)
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# Group D — Weighbridge (read off the wheat slip weights; the mill has no separate weighbridge record)
# ---------------------------------------------------------------------------

def _weigh_row(line):
    inv = line.invoice
    party = line.party_weight
    mill = line.mill_weight
    diff = (mill - party) if (mill is not None and party is not None) else None
    rate = line.rate_per_mund if line.rate_per_mund is not None else (line.rate * 40)
    return {
        "pk": inv.pk, "number": inv.invoice_num, "date": inv.invoice_date, "time": inv.posted_at, "vehicle": inv.vehicle_no or "—",
        "supplier_id": inv.supplier_id, "party": inv.supplier.name, "direction": "In", "product": line.product.name,
        "party_gross": weight(line.party_load_weight) if line.party_load_weight is not None else None,
        "party_tare": weight(line.party_tare_weight) if line.party_tare_weight is not None else None,
        "mill_gross": weight(line.mill_load_weight) if line.mill_load_weight is not None else None,
        "mill_tare": weight(line.mill_tare_weight) if line.mill_tare_weight is not None else None,
        "party_weight": weight(party) if party is not None else None,
        "mill_weight": weight(mill) if mill is not None else None,
        "difference": weight(diff) if diff is not None else None,
        "difference_pct": _pct(diff, party) if diff is not None and party else None,
        "selected_weight": weight(line.selected_weight) if line.selected_weight is not None else None,
        "weight_source": _weight_source(line),
        "katla": weight(line.katla) if line.katla is not None else None,
        "credit_kg": weight(line.credit_weight),
        "rate_per_mund": money(rate),
        "cost_impact": money(mund(diff) * rate) if diff is not None else ZERO,
        "posted_by": (inv.posted_by.get_full_name() or inv.posted_by.username) if inv.posted_by_id else "",
    }


def weighbridge_register(start, end, vehicle="", supplier=None, min_difference=None):
    lines = wheat_lines(start, end, supplier).select_related("invoice__supplier", "invoice__posted_by", "product")
    if vehicle:
        lines = lines.filter(invoice__vehicle_no=vehicle)
    rows = [_weigh_row(line) for line in lines.order_by("-invoice__invoice_date", "-invoice__posted_at", "-invoice_id")]
    if min_difference is not None:
        rows = [row for row in rows if row["difference"] is not None and abs(row["difference"]) >= min_difference]
    totals = {key: sum((row[key] or ZERO for row in rows), ZERO) for key in ("party_weight", "mill_weight", "difference", "credit_kg", "cost_impact")}
    totals["vehicles"] = len({row["vehicle"] for row in rows if row["vehicle"] != "—"})
    totals["slips"] = len(rows)
    with_diff = [row["difference"] for row in rows if row["difference"] is not None]
    totals["avg_difference"] = weight(sum(with_diff, ZERO) / len(with_diff)) if with_diff else ZERO
    return {"rows": rows, "totals": totals}


def vehicle_report(start, end, vehicle=""):
    rows_by_vehicle = defaultdict(lambda: {"trips": 0, "net": ZERO, "diff": ZERO, "diff_n": 0, "last": None, "parties": set()})
    for row in weighbridge_register(start, end, vehicle)["rows"]:
        v = rows_by_vehicle[row["vehicle"]]
        v["trips"] += 1
        v["net"] += row["credit_kg"]
        if row["difference"] is not None:
            v["diff"] += row["difference"]
            v["diff_n"] += 1
        v["last"] = max(v["last"], row["date"]) if v["last"] else row["date"]
        v["parties"].add(row["party"])
    rows = [
        {
            "vehicle": name, "trips": v["trips"], "net_kg": weight(v["net"]), "net_mund": mund(v["net"]),
            "avg_difference": weight(v["diff"] / v["diff_n"]) if v["diff_n"] else None, "parties": ", ".join(sorted(v["parties"])[:3]), "last_visit": v["last"],
        }
        for name, v in rows_by_vehicle.items()
    ]
    totals = {"trips": sum(r["trips"] for r in rows), "net_kg": sum((r["net_kg"] for r in rows), ZERO), "net_mund": sum((r["net_mund"] for r in rows), ZERO), "vehicles": len(rows)}
    return {"rows": rows, "totals": totals}


def gate_sheet(start, end):
    data = weighbridge_register(start, end)
    rows = sorted(data["rows"], key=lambda r: (r["date"], r["time"].isoformat() if r["time"] else "", r["pk"]))
    return {"rows": rows, "totals": data["totals"]}
