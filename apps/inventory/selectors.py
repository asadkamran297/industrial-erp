"""Sales reporting reads. Posted sale invoices and returns, product ledger rates; nothing here writes."""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce

from apps.core.constants import (
    PAY_MODE_CARD,
    PAY_MODE_CASH,
    PAY_MODE_CREDIT,
    PAY_MODE_ONLINE,
    PRD_LEVEL_SUB_GROUP,
    PRD_UNIT_BASE_WEIGHT,
    STATUS_ACTIVE,
    VOUCHER_TYPE_RECEIPT,
    YES,
)
from apps.core.reporting import ZERO, group_by, money, period_label, weight
from apps.finance.models import AccountVoucherLine, ChartOfAccount
from apps.products.models import ProductNode, ProductRate

from .models import Customer, POSDetail, POSMaster, POSReturnDetail, POSReturnMaster

MONEY = DecimalField(max_digits=18, decimal_places=2)
QTY = DecimalField(max_digits=18, decimal_places=3)


def _sum(expression, field=MONEY):
    return Coalesce(Sum(expression), Value(Decimal("0")), output_field=field)


def _unit_kg(prefix="product__"):
    return Case(
        *[When(**{f"{prefix}unit": unit}, then=Value(Decimal(kg))) for unit, kg in PRD_UNIT_BASE_WEIGHT.items()],
        default=F(f"{prefix}unit_weight"),
        output_field=QTY,
    )


def _pay(mode):
    return _sum(Case(When(pay_mode=mode, then=F("net_amount")), default=Value(Decimal("0")), output_field=MONEY))


def posted_sales(start, end, customer=None, pay_mode="", status=""):
    sales = POSMaster.objects.filter(posted=YES, sale_date__range=(start, end))
    if customer:
        sales = sales.filter(customer_id=customer)
    if pay_mode:
        sales = sales.filter(pay_mode=pay_mode)
    if status:
        sales = sales.filter(status=status)
    return sales


def product_lines(start, end, **filters):
    lines = POSDetail.objects.filter(pos_master__posted=YES, pos_master__sale_date__range=(start, end), product__isnull=False)
    return lines.filter(**filters) if filters else lines


def customer_options():
    return Customer.objects.filter(status=STATUS_ACTIVE).values_list("pk", "customer_name")


def product_options():
    return ProductNode.objects.filter(level=3, status=STATUS_ACTIVE, sale_lines__isnull=False).distinct().order_by("name").values_list("pk", "name")


def family_options():
    return ProductNode.objects.filter(level=PRD_LEVEL_SUB_GROUP, status=STATUS_ACTIVE).order_by("name").values_list("pk", "name")


# ---------------------------------------------------------------------------
# 6. Sales Register
# ---------------------------------------------------------------------------

def sales_register(start, end, customer=None, product=None, pay_mode="", status=""):
    sales = posted_sales(start, end, customer, pay_mode, status).select_related("customer", "posted_by")
    if product:
        sales = sales.filter(items__product_id=product).distinct()
    sales = sales.prefetch_related("items__product").order_by("-sale_date", "-id")
    rows = []
    for sale in sales:
        items = list(sale.items.all())
        bags = sum((item.quantity for item in items if item.product_id), ZERO)
        kg = sum((item.quantity * item.product.effective_unit_weight for item in items if item.product_id), ZERO)
        names = [item.item_name for item in items]
        rows.append({
            "pk": sale.pk,
            "number": sale.sale_num,
            "date": sale.sale_date,
            "customer_id": sale.customer_id,
            "customer": sale.customer.customer_name if sale.customer_id else "Walk-in",
            "products": ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else ""),
            "lines": len(items),
            "bags": weight(bags),
            "kg": weight(kg),
            "gross": money(sale.total_amount),
            "discount": money(sale.discount_amount),
            "tax": money(sale.tax_amount),
            "net": money(sale.net_amount),
            "paid": money(sale.total_paid),
            "balance": money(sale.balance),
            "pay_mode": sale.get_pay_mode_display(),
            "pay_mode_key": sale.pay_mode,
            "status": sale.status,
            "status_label": sale.get_status_display(),
            "user": (sale.posted_by.get_full_name() or sale.posted_by.username) if sale.posted_by_id else "",
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("bags", "kg", "gross", "discount", "tax", "net", "paid", "balance")}
    totals["invoices"] = len(rows)
    totals["cash"] = sum((row["net"] for row in rows if row["pay_mode_key"] == PAY_MODE_CASH), ZERO)
    totals["credit"] = sum((row["net"] for row in rows if row["pay_mode_key"] == PAY_MODE_CREDIT), ZERO)
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 7. Sales Summary (day / week / month)
# ---------------------------------------------------------------------------

def sales_summary(start, end, group, customer=None):
    sales = (
        posted_sales(start, end, customer).annotate(period=group_by("sale_date", group)).values("period")
        .annotate(
            invoices=Count("id"), gross=_sum("total_amount"), discount=_sum("discount_amount"), net=_sum("net_amount"),
            cash=_pay(PAY_MODE_CASH), credit=_pay(PAY_MODE_CREDIT), card=_pay(PAY_MODE_CARD), online=_pay(PAY_MODE_ONLINE),
        ).order_by("period")
    )
    lines = product_lines(start, end)
    if customer:
        lines = lines.filter(pos_master__customer_id=customer)
    qty = {
        row["period"]: row for row in lines.annotate(period=group_by("pos_master__sale_date", group)).values("period")
        .annotate(bags=_sum("quantity", QTY), kg=_sum(F("quantity") * _unit_kg(), QTY))
    }
    returns = POSReturnMaster.objects.filter(posted=YES, return_date__range=(start, end))
    if customer:
        returns = returns.filter(customer_id=customer)
    returned = {
        row["period"]: row["amount"] for row in returns.annotate(period=group_by("return_date", group)).values("period")
        .annotate(amount=_sum("returned_amount"))
    }
    rows = []
    for row in sales:
        key = row["period"]
        q = qty.get(key, {})
        net = money(row["net"])
        ret = money(returned.get(key))
        rows.append({
            "period": key.date() if hasattr(key, "date") else key,
            "label": period_label(key, group),
            "invoices": row["invoices"],
            "bags": weight(q.get("bags")),
            "kg": weight(q.get("kg")),
            "gross": money(row["gross"]),
            "discount": money(row["discount"]),
            "net": net,
            "cash": money(row["cash"]),
            "credit": money(row["credit"]),
            "card": money(row["card"]),
            "online": money(row["online"]),
            "returns": ret,
            "net_of_returns": money(net - ret),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("bags", "kg", "gross", "discount", "net", "cash", "credit", "card", "online", "returns", "net_of_returns")}
    totals["invoices"] = sum(row["invoices"] for row in rows)
    return {"rows": rows, "totals": totals}


def sales_totals(start, end):
    row = posted_sales(start, end).aggregate(invoices=Count("id"), net=_sum("net_amount"), cash=_pay(PAY_MODE_CASH), credit=_pay(PAY_MODE_CREDIT))
    bags = product_lines(start, end).aggregate(bags=_sum("quantity", QTY))["bags"]
    returns = POSReturnMaster.objects.filter(posted=YES, return_date__range=(start, end)).aggregate(amount=_sum("returned_amount"))["amount"]
    return {"invoices": row["invoices"], "net": money(row["net"]), "cash": money(row["cash"]), "credit": money(row["credit"]), "bags": weight(bags), "returns": money(returns)}


# ---------------------------------------------------------------------------
# 8. Party-wise Sales
# ---------------------------------------------------------------------------

def _customer_codes(customers):
    names = {c.customer_name: c.pk for c in customers}
    rows = ChartOfAccount.objects.filter(title__in=names.keys(), is_group=False).values_list("title", "code", "opening_balance")
    return {names[title]: (code, opening) for title, code, opening in rows}


def customer_sales(start, end, customer=None, city=None):
    customers = Customer.objects.filter(status=STATUS_ACTIVE).select_related("city")
    if customer:
        customers = customers.filter(pk=customer)
    if city:
        customers = customers.filter(city_id=city)
    customers = list(customers)
    ids = [c.pk for c in customers]
    sold = {
        row["customer_id"]: row for row in posted_sales(start, end).filter(customer_id__in=ids).values("customer_id")
        .annotate(invoices=Count("id"), net=_sum("net_amount"), paid=_sum("total_paid"))
    }
    last_sale = {}
    for cid, day in POSMaster.objects.filter(posted=YES, customer_id__in=ids).order_by("customer_id", "-sale_date").values_list("customer_id", "sale_date"):
        last_sale.setdefault(cid, day)
    bags = {
        row["pos_master__customer_id"]: row["bags"]
        for row in product_lines(start, end).filter(pos_master__customer_id__in=ids).values("pos_master__customer_id").annotate(bags=_sum("quantity", QTY))
    }
    returned = {
        row["customer_id"]: row["amount"]
        for row in POSReturnMaster.objects.filter(posted=YES, return_date__range=(start, end), customer_id__in=ids)
        .values("customer_id").annotate(amount=_sum("returned_amount"))
    }
    codes = _customer_codes(customers)
    code_to_customer = {code: cid for cid, (code, _o) in codes.items()}
    lines = AccountVoucherLine.objects.filter(account_no__in=code_to_customer.keys())
    received = {
        code_to_customer[row["account_no"]]: row["credit"]
        for row in lines.filter(voucher__voucher_type=VOUCHER_TYPE_RECEIPT, voucher_date__range=(start, end))
        .values("account_no").annotate(credit=_sum("credit_amount"))
    }
    closing = {
        code_to_customer[row["account_no"]]: row["debit"] - row["credit"]
        for row in lines.filter(voucher_date__lte=end).values("account_no").annotate(debit=_sum("debit_amount"), credit=_sum("credit_amount"))
    }
    rows = []
    for c in customers:
        s = sold.get(c.pk)
        if not s and c.pk not in returned and c.pk not in received:
            continue
        s = s or {}
        code, opening = codes.get(c.pk, (None, None))
        balance = money((opening or ZERO) + closing.get(c.pk, ZERO)) if code else money(c.opening_balance)
        rows.append({
            "customer_id": c.pk,
            "customer": c.customer_name,
            "city": c.city.title if c.city_id else "",
            "phone": c.customer_cell_no,
            "invoices": s.get("invoices", 0),
            "bags": weight(bags.get(c.pk)),
            "net": money(s.get("net")),
            "returns": money(returned.get(c.pk)),
            "received": money(received.get(c.pk)),
            "balance": balance,
            "credit_days": c.credit_period_days,
            "last_sale": last_sale.get(c.pk),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("bags", "net", "returns", "received", "balance")}
    totals["invoices"] = sum(row["invoices"] for row in rows)
    return {"rows": rows, "totals": totals}


def city_options():
    from apps.configurations.models import City

    return City.objects.filter(customer__isnull=False).distinct().order_by("title").values_list("pk", "title")


# ---------------------------------------------------------------------------
# 9. Product-wise Sales
# ---------------------------------------------------------------------------

def product_sales(start, end, family=None, product=None, customer=None):
    lines = product_lines(start, end)
    if family:
        lines = lines.filter(product__parent_id=family)
    if product:
        lines = lines.filter(product_id=product)
    if customer:
        lines = lines.filter(pos_master__customer_id=customer)
    grouped = (
        lines.values("product_id", "product__name", "product__parent__name", "product__parent_id")
        .annotate(bags=_sum("quantity", QTY), kg=_sum(F("quantity") * _unit_kg(), QTY), net=_sum("net_total"), invoices=Count("pos_master", distinct=True))
        .order_by("-net")
    )
    rows = [
        {
            "product_id": row["product_id"], "product": row["product__name"], "family": row["product__parent__name"], "family_id": row["product__parent_id"],
            "invoices": row["invoices"], "bags": weight(row["bags"]), "kg": weight(row["kg"]), "net": money(row["net"]),
            "avg_rate": money(row["net"] / row["bags"]) if row["bags"] else ZERO,
            "rate_per_kg": money(row["net"] / row["kg"]) if row["kg"] else ZERO,
        }
        for row in grouped
    ]
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("bags", "kg", "net")}
    totals["invoices"] = sum(row["invoices"] for row in rows)
    for row in rows:
        row["share"] = (row["net"] / totals["net"] * 100).quantize(Decimal("0.01")) if totals["net"] else ZERO
    families = defaultdict(lambda: {"net": ZERO, "bags": ZERO})
    for row in rows:
        families[row["family"]]["net"] += row["net"]
        families[row["family"]]["bags"] += row["bags"]
    return {"rows": rows, "totals": totals, "families": dict(families)}


# ---------------------------------------------------------------------------
# 10. Sale Rate History
# ---------------------------------------------------------------------------

def _list_rate_lookup(product_ids):
    """``{product_id: [(effective_date, rate), ...]}`` newest first."""
    lookup = defaultdict(list)
    for pid, day, rate in ProductRate.objects.filter(product_id__in=product_ids).order_by("product_id", "-effective_date", "-id").values_list("product_id", "effective_date", "rate"):
        lookup[pid].append((day, rate))
    return lookup


def rate_history(start, end, product=None, customer=None):
    lines = product_lines(start, end).select_related("pos_master__customer", "product")
    if product:
        lines = lines.filter(product_id=product)
    if customer:
        lines = lines.filter(pos_master__customer_id=customer)
    lines = list(lines.order_by("-pos_master__sale_date", "-pos_master_id"))
    list_rates = _list_rate_lookup({line.product_id for line in lines})
    rows = []
    for line in lines:
        day = line.pos_master.sale_date
        listed = next((rate for eff, rate in list_rates.get(line.product_id, []) if eff <= day), None)
        variance = money(line.price - listed) if listed is not None else None
        rows.append({
            "pk": line.pos_master_id,
            "date": day,
            "number": line.sale_num,
            "customer": line.pos_master.customer.customer_name if line.pos_master.customer_id else "Walk-in",
            "product_id": line.product_id,
            "product": line.product.name,
            "qty": weight(line.quantity),
            "billed": money(line.price),
            "list_rate": money(listed) if listed is not None else None,
            "variance": variance,
            "variance_pct": (variance / listed * 100).quantize(Decimal("0.01")) if listed else None,
            "net": money(line.net_total),
        })
    below = [row for row in rows if row["variance"] is not None and row["variance"] < 0]
    totals = {
        "lines": len(rows), "qty": sum((row["qty"] for row in rows), ZERO), "net": sum((row["net"] for row in rows), ZERO),
        "below_list": len(below), "given_away": money(sum((row["variance"] * row["qty"] for row in below), ZERO)),
    }
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 11. Sale Returns
# ---------------------------------------------------------------------------

def sale_returns(start, end, customer=None, product=None):
    returns = POSReturnMaster.objects.filter(posted=YES, return_date__range=(start, end)).select_related("customer", "pos_master")
    if customer:
        returns = returns.filter(customer_id=customer)
    if product:
        returns = returns.filter(items__product_id=product).distinct()
    returns = returns.prefetch_related("items__product").order_by("-return_date", "-id")
    rows = []
    for ret in returns:
        items = list(ret.items.all())
        names = [item.item_name for item in items]
        rows.append({
            "pk": ret.pk,
            "number": ret.return_num,
            "date": ret.return_date,
            "customer_id": ret.customer_id,
            "customer": ret.customer.customer_name if ret.customer_id else "Walk-in",
            "sale_pk": ret.pos_master_id,
            "sale_number": ret.sale_num,
            "sale_date": ret.pos_master.sale_date,
            "products": ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else ""),
            "qty": weight(sum((item.quantity for item in items), ZERO)),
            "kg": weight(sum((item.quantity * item.product.effective_unit_weight for item in items if item.product_id), ZERO)),
            "invoice_amount": money(ret.total_invoice_amount),
            "returned": money(ret.returned_amount),
            "adjusted": money(ret.adjusted_amount),
            "pay_mode": ret.get_pay_mode_display(),
            "status": ret.status,
            "status_label": ret.get_status_display(),
            "remarks": ret.remarks,
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("qty", "kg", "invoice_amount", "returned", "adjusted")}
    totals["returns"] = len(rows)
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 12. POS Cash Sales Day Sheet
# ---------------------------------------------------------------------------

def day_sheet(start, end, cashier=None):
    sales = posted_sales(start, end).exclude(pay_mode=PAY_MODE_CREDIT).select_related("customer", "posted_by")
    if cashier:
        sales = sales.filter(posted_by_id=cashier)
    rows = []
    for sale in sales.order_by("sale_date", "posted_at", "id"):
        rows.append({
            "pk": sale.pk,
            "number": sale.sale_num,
            "date": sale.sale_date,
            "time": sale.posted_at,
            "customer": sale.customer.customer_name if sale.customer_id else "Walk-in",
            "cashier_id": sale.posted_by_id,
            "cashier": (sale.posted_by.get_full_name() or sale.posted_by.username) if sale.posted_by_id else "",
            "gross": money(sale.total_amount),
            "discount": money(sale.discount_amount),
            "net": money(sale.net_amount),
            "cash": money(sale.net_amount) if sale.pay_mode == PAY_MODE_CASH else ZERO,
            "card": money(sale.net_amount) if sale.pay_mode == PAY_MODE_CARD else ZERO,
            "online": money(sale.net_amount) if sale.pay_mode == PAY_MODE_ONLINE else ZERO,
            "pay_mode": sale.get_pay_mode_display(),
        })
    totals = {key: sum((row[key] for row in rows), ZERO) for key in ("gross", "discount", "net", "cash", "card", "online")}
    totals["invoices"] = len(rows)
    return {"rows": rows, "totals": totals}


def cashier_options():
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(posted_sales_invoices__isnull=False).distinct().order_by("username")
    return [(u.pk, u.get_full_name() or u.username) for u in users]
