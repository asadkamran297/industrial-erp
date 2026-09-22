"""Owner-pack reads. Every figure comes off a ledger or a posted document; nothing here writes."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import (
    Case, Count, DecimalField, Exists, F, OuterRef, Sum, Value, When,
)
from django.db.models.functions import Coalesce

from apps.core.constants import (
    PRD_LEDGER_OPENING,
    PRD_LEDGER_PRODUCTION_IN,
    PRD_LEDGER_PURCHASE,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
    PRD_UNIT_BASE_WEIGHT,
    STATUS_ACTIVE,
    STATUS_POSTED,
    YES,
)
from apps.core.reporting import ZERO, money, weight
from apps.finance.models import AccountVoucherLine, ChartOfAccount
from apps.finance.services import DEBIT_NATURE_TYPES, cash_bank_account_codes
from apps.inventory.models import (
    Customer, POSDetail, POSMaster, PurchaseInvoice, PurchaseInvoiceLine, Supplier,
)
from apps.production.models import GrindingOutput, GrindingVoucher
from apps.products.models import ProductLedger, ProductRate

MONEY = DecimalField(max_digits=18, decimal_places=2)
KG = DecimalField(max_digits=18, decimal_places=3)
AGING_BUCKETS = (("b0", "0-30", 0, 30), ("b1", "31-60", 31, 60), ("b2", "61-90", 61, 90), ("b3", "90+", 91, None))


def _sum(expression, field=MONEY):
    return Coalesce(Sum(expression), Value(Decimal("0")), output_field=field)


def _unit_kg(prefix=""):
    """Kg in one ledger unit: fixed by the unit where the unit fixes it, else the item's own weight."""
    return Case(
        *[When(**{f"{prefix}unit": unit}, then=Value(Decimal(kg))) for unit, kg in PRD_UNIT_BASE_WEIGHT.items()],
        default=F(f"{prefix}unit_weight"),
        output_field=KG,
    )


# ---------------------------------------------------------------------------
# Ledger balances as of a day
# ---------------------------------------------------------------------------

def _codes_balance_as_of(codes, day, debit_natured=True):
    """Opening plus every voucher line up to ``day`` for a set of account codes, on the natural side."""
    codes = set(codes)
    if not codes:
        return ZERO
    opening = ChartOfAccount.objects.filter(code__in=codes).aggregate(total=_sum("opening_balance"))["total"]
    moved = AccountVoucherLine.objects.filter(account_no__in=codes, voucher_date__lte=day).aggregate(
        debit=_sum("debit_amount"), credit=_sum("credit_amount"),
    )
    net = moved["debit"] - moved["credit"]
    return money(opening + (net if debit_natured else -net))


def _party_codes(parties, name_attr):
    """``{party_id: account code}`` matched the way ``finance.services._party_balances`` matches."""
    names = {getattr(party, name_attr): party.pk for party in parties}
    rows = ChartOfAccount.objects.filter(title__in=names.keys(), is_group=False).values_list("title", "code")
    return {names[title]: code for title, code in rows if title in names}


def _party_balances_as_of(parties, name_attr, day):
    """Signed on the natural side: what a customer owes, what is owed to a supplier."""
    codes = _party_codes(parties, name_attr)
    natures = dict(ChartOfAccount.objects.filter(code__in=codes.values()).values_list("code", "account_type"))
    openings = dict(ChartOfAccount.objects.filter(code__in=codes.values()).values_list("code", "opening_balance"))
    moved = {
        row["account_no"]: (row["debit"], row["credit"])
        for row in AccountVoucherLine.objects.filter(account_no__in=codes.values(), voucher_date__lte=day)
        .values("account_no").annotate(debit=_sum("debit_amount"), credit=_sum("credit_amount"))
    }
    result = {}
    for party in parties:
        code = codes.get(party.pk)
        if not code:
            result[party.pk] = money(party.opening_balance)
            continue
        debit, credit = moved.get(code, (ZERO, ZERO))
        net = debit - credit
        signed = net if natures.get(code) in DEBIT_NATURE_TYPES else -net
        result[party.pk] = money((openings.get(code) or ZERO) + signed)
    return result


def cash_bank_closing(day, codes=None):
    return _codes_balance_as_of(codes if codes is not None else cash_bank_account_codes(), day, debit_natured=True)


def receivables_total(day):
    parties = list(Customer.objects.filter(status=STATUS_ACTIVE).only("pk", "customer_name", "opening_balance"))
    return money(sum(_party_balances_as_of(parties, "customer_name", day).values(), ZERO))


def payables_total(day):
    parties = list(Supplier.objects.filter(status=STATUS_ACTIVE).only("pk", "name", "opening_balance"))
    return money(sum(_party_balances_as_of(parties, "name", day).values(), ZERO))


# ---------------------------------------------------------------------------
# Wheat, grinding, sales in a date range
# ---------------------------------------------------------------------------

def wheat_lines(start, end):
    return PurchaseInvoiceLine.objects.filter(
        invoice__status=STATUS_POSTED,
        invoice__invoice_date__range=(start, end),
        product__specification=PRD_SPEC_RAW_ITEM,
    )


def wheat_purchased(start, end):
    row = wheat_lines(start, end).aggregate(
        kg=_sum(Coalesce("credit_weight", "quantity"), KG),
        amount=_sum("amount"),
        slips=Count("invoice", distinct=True),
    )
    return {"kg": weight(row["kg"]), "amount": money(row["amount"]), "slips": row["slips"]}


def grinding(start, end):
    row = GrindingVoucher.objects.filter(date__range=(start, end)).aggregate(
        wheat=_sum("disposal_wheat", KG), output=_sum("total_output_kg", KG), vouchers=Count("id"),
    )
    return {"wheat_kg": weight(row["wheat"]), "output_kg": weight(row["output"]), "vouchers": row["vouchers"]}


def production_by_product(start, end):
    rows = (
        GrindingOutput.objects.filter(voucher__date__range=(start, end))
        .values("product__name", "product__parent__name")
        .annotate(kg=_sum(F("quantity") * F("unit_weight"), KG), units=_sum("quantity", KG))
        .order_by("-kg")
    )
    return [
        {"product": row["product__name"], "family": row["product__parent__name"], "kg": weight(row["kg"]), "units": weight(row["units"])}
        for row in rows
    ]


def sales(start, end):
    invoices = POSMaster.objects.filter(posted=YES, sale_date__range=(start, end))
    row = invoices.aggregate(
        count=Count("id"), net=_sum("net_amount"), paid=_sum("total_paid"), discount=_sum("discount_amount"),
    )
    bags = POSDetail.objects.filter(
        pos_master__posted=YES, pos_master__sale_date__range=(start, end), product__isnull=False,
    ).aggregate(bags=_sum("quantity", KG))["bags"]
    return {
        "invoices": row["count"], "net": money(row["net"]), "paid": money(row["paid"]),
        "discount": money(row["discount"]), "bags": weight(bags),
    }


def wheat_stock_kg(day):
    row = ProductLedger.objects.filter(
        product__specification=PRD_SPEC_RAW_ITEM, entry_date__lte=day,
    ).aggregate(kg=_sum(F("quantity") * _unit_kg("product__"), KG))
    return weight(row["kg"])


def wheat_stock_days(day, window=30):
    """Closing wheat divided by the average daily grinding over the last ``window`` days."""
    stock = wheat_stock_kg(day)
    ground = grinding(day - timedelta(days=window - 1), day)["wheat_kg"]
    per_day = ground / window if ground else ZERO
    days = (stock / per_day).quantize(Decimal("0.1")) if per_day else None
    return {"stock_kg": stock, "per_day_kg": weight(per_day), "days": days}


def cash_movement(start, end, codes=None):
    codes = codes if codes is not None else cash_bank_account_codes()
    row = AccountVoucherLine.objects.filter(account_no__in=codes, voucher_date__range=(start, end)).aggregate(
        cash_in=_sum("debit_amount"), cash_out=_sum("credit_amount"),
    )
    return {"cash_in": money(row["cash_in"]), "cash_out": money(row["cash_out"])}


# ---------------------------------------------------------------------------
# Report 1 — Daily Position
# ---------------------------------------------------------------------------

def daily_position(day):
    wheat = wheat_purchased(day, day)
    ground = grinding(day, day)
    sold = sales(day, day)
    stock = wheat_stock_days(day)
    codes = cash_bank_account_codes()
    return {
        "day": day,
        "wheat": wheat,
        "grinding": ground,
        "production": production_by_product(day, day),
        "sales": sold,
        "cash": cash_movement(day, day, codes),
        "cash_closing": cash_bank_closing(day, codes),
        "receivables": receivables_total(day),
        "payables": payables_total(day),
        "wheat_stock": stock,
    }


# ---------------------------------------------------------------------------
# Report 2 — Month at a Glance
# ---------------------------------------------------------------------------

def month_glance(start, end):
    """Day-wise rows for the range with a running closing cash."""
    purchase = {
        row["invoice__invoice_date"]: row
        for row in wheat_lines(start, end).values("invoice__invoice_date")
        .annotate(kg=_sum(Coalesce("credit_weight", "quantity"), KG), amount=_sum("amount"))
    }
    ground = {
        row["date"]: row
        for row in GrindingVoucher.objects.filter(date__range=(start, end)).values("date")
        .annotate(wheat=_sum("disposal_wheat", KG), output=_sum("total_output_kg", KG))
    }
    sold = {
        row["sale_date"]: row
        for row in POSMaster.objects.filter(posted=YES, sale_date__range=(start, end)).values("sale_date")
        .annotate(net=_sum("net_amount"), paid=_sum("total_paid"))
    }
    codes = cash_bank_account_codes()
    cash = {
        row["voucher_date"]: row
        for row in AccountVoucherLine.objects.filter(account_no__in=codes, voucher_date__range=(start, end))
        .values("voucher_date").annotate(cash_in=_sum("debit_amount"), cash_out=_sum("credit_amount"))
    }
    balance = cash_bank_closing(start - timedelta(days=1), codes)
    opening_cash = balance
    rows = []
    day = start
    while day <= end:
        p, g, s, c = purchase.get(day, {}), ground.get(day, {}), sold.get(day, {}), cash.get(day, {})
        cash_in, cash_out = money(c.get("cash_in")), money(c.get("cash_out"))
        balance = money(balance + cash_in - cash_out)
        rows.append({
            "date": day,
            "purchase_kg": weight(p.get("kg")),
            "purchase_amount": money(p.get("amount")),
            "grinding_kg": weight(g.get("wheat")),
            "production_kg": weight(g.get("output")),
            "sales": money(s.get("net")),
            "cash_in": cash_in,
            "cash_out": cash_out,
            "closing_cash": balance,
        })
        day += timedelta(days=1)
    totals = {
        key: sum((row[key] for row in rows), ZERO)
        for key in ("purchase_kg", "purchase_amount", "grinding_kg", "production_kg", "sales", "cash_in", "cash_out")
    }
    totals["opening_cash"] = opening_cash
    totals["closing_cash"] = balance
    return {"rows": rows, "totals": totals}


def month_glance_totals(start, end):
    """The same four totals for a comparison period, in one query each."""
    wheat = wheat_purchased(start, end)
    ground = grinding(start, end)
    sold = sales(start, end)
    cash = cash_movement(start, end)
    return {
        "purchase_kg": wheat["kg"], "purchase_amount": wheat["amount"], "grinding_kg": ground["wheat_kg"],
        "production_kg": ground["output_kg"], "sales": sold["net"], "cash_in": cash["cash_in"], "cash_out": cash["cash_out"],
    }


# ---------------------------------------------------------------------------
# Report 3 — Profitability by Product
# ---------------------------------------------------------------------------

def product_cost_rates(as_of):
    """Weighted average inbound rate per product from the product ledger up to ``as_of``.

    Rows with no rate (a grinding receipt carries none) do not count; a product
    with no costed row falls back to its current list rate and says so.
    """
    costed = (
        ProductLedger.objects.filter(
            entry_date__lte=as_of, quantity__gt=0, rate__gt=0,
            source__in=(PRD_LEDGER_OPENING, PRD_LEDGER_PURCHASE, PRD_LEDGER_PRODUCTION_IN),
        )
        .values("product_id").annotate(value=_sum(F("quantity") * F("rate")), qty=_sum("quantity", KG))
    )
    rates = {row["product_id"]: (money(row["value"] / row["qty"]), "ledger") for row in costed if row["qty"]}
    for rate in ProductRate.objects.filter(is_current=True).order_by("product_id", "-effective_date"):
        rates.setdefault(rate.product_id, (money(rate.rate), "list"))
    return rates


def product_profit(start, end):
    lines = (
        POSDetail.objects.filter(pos_master__posted=YES, pos_master__sale_date__range=(start, end), product__isnull=False)
        .values("product_id", "product__name", "product__parent__name", "product__unit", "product__unit_weight")
        .annotate(qty=_sum("quantity", KG), net=_sum("net_total"), invoices=Count("pos_master", distinct=True))
        .order_by("-net")
    )
    rates = product_cost_rates(end)
    rows = []
    for line in lines:
        rate, source = rates.get(line["product_id"], (ZERO, ""))
        unit_kg = Decimal(PRD_UNIT_BASE_WEIGHT.get(line["product__unit"]) or line["product__unit_weight"] or 0)
        qty = weight(line["qty"])
        net = money(line["net"])
        cogs = money(qty * rate)
        margin = money(net - cogs)
        rows.append({
            "product_id": line["product_id"],
            "product": line["product__name"],
            "family": line["product__parent__name"] or "",
            "qty": qty,
            "kg": weight(qty * unit_kg),
            "net": net,
            "avg_rate": money(net / qty) if qty else ZERO,
            "cost_rate": rate,
            "cost_source": source,
            "cogs": cogs,
            "margin": margin,
            "margin_pct": (margin / net * 100).quantize(Decimal("0.01")) if net else ZERO,
            "invoices": line["invoices"],
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("qty", "kg", "net", "cogs", "margin")}
    totals["margin_pct"] = (totals["margin"] / totals["net"] * 100).quantize(Decimal("0.01")) if totals["net"] else ZERO
    total_net = totals["net"]
    for row in rows:
        row["share"] = (row["net"] / total_net * 100).quantize(Decimal("0.01")) if total_net else ZERO
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# Reports 4 & 5 — Aging
# ---------------------------------------------------------------------------

def _bucket(age_days):
    for key, _label, low, high in AGING_BUCKETS:
        if age_days >= low and (high is None or age_days <= high):
            return key
    return "b3"


def _age_documents(balance, documents, as_of):
    """Spread an outstanding balance over documents newest first (older ones are taken as settled)."""
    buckets = {key: ZERO for key, *_ in AGING_BUCKETS}
    remaining = balance
    oldest = None
    for doc_date, amount in documents:
        if remaining <= 0:
            break
        take = min(remaining, amount)
        buckets[_bucket((as_of - doc_date).days)] += take
        remaining -= take
        oldest = doc_date
    if remaining > 0:
        buckets["b3"] += remaining
    return {key: money(value) for key, value in buckets.items()}, oldest


def receivables_aging(as_of, customer_id=None, over_limit_only=False):
    customers = Customer.objects.filter(status=STATUS_ACTIVE).select_related("city")
    if customer_id:
        customers = customers.filter(pk=customer_id)
    customers = list(customers)
    balances = _party_balances_as_of(customers, "customer_name", as_of)
    documents = defaultdict(list)
    invoices = (
        POSMaster.objects.filter(posted=YES, sale_date__lte=as_of, customer_id__in=[c.pk for c in customers])
        .order_by("-sale_date", "-id").values_list("customer_id", "sale_date", "net_amount")
    )
    for cid, day, amount in invoices:
        documents[cid].append((day, amount))
    last_sale = {cid: docs[0][0] for cid, docs in documents.items()}
    rows = []
    for customer in customers:
        balance = balances.get(customer.pk, ZERO)
        if balance <= 0:
            continue
        buckets, oldest = _age_documents(balance, documents.get(customer.pk, []), as_of)
        limit = customer.credit_limit
        over = bool(limit is not None and balance > limit)
        if over_limit_only and not over:
            continue
        rows.append({
            "party_id": customer.pk,
            "party": customer.customer_name,
            "city": customer.city.title if customer.city else "",
            "phone": customer.customer_cell_no,
            "balance": balance,
            **buckets,
            "credit_limit": money(limit) if limit is not None else None,
            "over_limit": over,
            "over_by": money(balance - limit) if over else ZERO,
            "oldest": oldest,
            "last_sale": last_sale.get(customer.pk),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("balance", "b0", "b1", "b2", "b3", "over_by")}
    totals["over_limit"] = sum(1 for row in rows if row["over_limit"])
    return {"rows": rows, "totals": totals}


def supplier_kind_flags():
    """Which door each supplier trades through, read off what has actually been invoiced."""
    line = PurchaseInvoiceLine.objects.filter(invoice__supplier_id=OuterRef("pk"), invoice__status=STATUS_POSTED)
    return {
        "is_arhti": Exists(line.filter(product__specification=PRD_SPEC_RAW_ITEM)),
        "is_bardana": Exists(line.filter(product__specification=PRD_SPEC_RAW_PACKING)),
        "is_stores": Exists(line.filter(inventory_item__isnull=False)),
    }


SUPPLIER_KIND_CHOICES = (("arhti", "Arhti (wheat)"), ("bardana", "Bardana"), ("stores", "Stores"))


def payables_aging(as_of, supplier_id=None, kind=""):
    suppliers = Supplier.objects.filter(status=STATUS_ACTIVE).select_related("city").annotate(**supplier_kind_flags())
    if supplier_id:
        suppliers = suppliers.filter(pk=supplier_id)
    if kind in dict(SUPPLIER_KIND_CHOICES):
        suppliers = suppliers.filter(**{f"is_{kind}": True})
    suppliers = list(suppliers)
    balances = _party_balances_as_of(suppliers, "name", as_of)
    documents = defaultdict(list)
    invoices = (
        PurchaseInvoice.objects.filter(status=STATUS_POSTED, invoice_date__lte=as_of, supplier_id__in=[s.pk for s in suppliers])
        .order_by("-invoice_date", "-id").values_list("supplier_id", "invoice_date", "total_amount")
    )
    for sid, day, amount in invoices:
        documents[sid].append((day, amount))
    rows = []
    for supplier in suppliers:
        balance = balances.get(supplier.pk, ZERO)
        if balance <= 0:
            continue
        buckets, oldest = _age_documents(balance, documents.get(supplier.pk, []), as_of)
        kinds = [label for key, label in SUPPLIER_KIND_CHOICES if getattr(supplier, f"is_{key}")]
        rows.append({
            "party_id": supplier.pk,
            "party": supplier.name,
            "kind": ", ".join(kinds),
            "city": supplier.city.title if supplier.city else "",
            "phone": supplier.tel1,
            "balance": balance,
            **buckets,
            "oldest": oldest,
            "last_invoice": documents[supplier.pk][0][0] if documents.get(supplier.pk) else None,
            "invoices": len(documents.get(supplier.pk, [])),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("balance", "b0", "b1", "b2", "b3")}
    return {"rows": rows, "totals": totals}
