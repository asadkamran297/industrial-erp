"""Setup / master reads (catalogue group J): party directory, product master, chart of accounts, user access."""

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch

from apps.access_control.models import RolePermission, UserAssignment
from apps.core.constants import (
    FIN_COA_ACCOUNT_TYPE_CHOICES,
    PRD_LEVEL_ITEM,
    PRD_SPECIFICATION_CHOICES,
    PRD_UNIT_CHOICES,
    RECORD_STATUS_CHOICES,
    STATUS_ACTIVE,
)
from apps.core.reporting import ZERO, money, weight
from apps.finance.models import ChartOfAccount
from apps.finance.services import account_balances
from apps.inventory.models import Customer, Supplier
from apps.products.models import ProductNode, ProductRate

from .selectors import _party_balances_as_of, _party_codes

KIND_SUPPLIER = "supplier"
KIND_CUSTOMER = "customer"
KIND_CHOICES = ((KIND_SUPPLIER, "Suppliers"), (KIND_CUSTOMER, "Customers"))
STATUS_LABELS = dict(RECORD_STATUS_CHOICES)
ACCOUNT_TYPE_LABELS = dict(FIN_COA_ACCOUNT_TYPE_CHOICES)
SPEC_LABELS = dict(PRD_SPECIFICATION_CHOICES)
UNIT_LABELS = dict(PRD_UNIT_CHOICES)
INDENT = " "


def city_options():
    from apps.configurations.models import City

    return City.objects.filter(status=STATUS_ACTIVE).order_by("title").values_list("pk", "title")


def status_options():
    return RECORD_STATUS_CHOICES


# ---------------------------------------------------------------------------
# 68. Supplier / Customer Directory
# ---------------------------------------------------------------------------

def _party_rows(kind, parties, name_attr, day):
    balances = _party_balances_as_of(parties, name_attr, day)
    codes = _party_codes(parties, name_attr)
    rows = []
    for party in parties:
        balance = balances.get(party.pk, ZERO)
        limit = party.credit_limit
        is_supplier = kind == KIND_SUPPLIER
        rows.append({
            "pk": party.pk, "supplier_id": party.pk if is_supplier else None, "customer_id": None if is_supplier else party.pk,
            "kind": "Supplier" if is_supplier else "Customer", "code": (party.code if is_supplier else party.customer_code) or "",
            "name": getattr(party, name_attr), "city": party.city.title if party.city_id else "",
            "contact": (party.tel1 or party.tel2) if is_supplier else party.customer_cell_no,
            "email": party.email if is_supplier else party.customer_email, "ntn": party.ntn_number,
            "account": codes.get(party.pk, ""), "opening": money(party.opening_balance), "credit_limit": money(limit) if limit is not None else None,
            "credit_days": party.credit_period_days, "balance": balance,
            "over_limit": bool(limit is not None and limit and balance > limit),
            "status": party.status, "status_label": STATUS_LABELS.get(party.status, party.status),
        })
    return rows


def party_directory(day, kind="", city=None, status=""):
    rows = []
    if kind in ("", KIND_SUPPLIER):
        qs = Supplier.objects.select_related("city").order_by("name")
        if city:
            qs = qs.filter(city_id=city)
        if status:
            qs = qs.filter(status=status)
        rows += _party_rows(KIND_SUPPLIER, list(qs), "name", day)
    if kind in ("", KIND_CUSTOMER):
        qs = Customer.objects.select_related("city").order_by("customer_name")
        if city:
            qs = qs.filter(city_id=city)
        if status:
            qs = qs.filter(status=status)
        rows += _party_rows(KIND_CUSTOMER, list(qs), "customer_name", day)
    totals = {
        "balance": sum((r["balance"] for r in rows), ZERO),
        "credit_limit": sum((r["credit_limit"] or ZERO for r in rows), ZERO),
        "opening": sum((r["opening"] for r in rows), ZERO),
        "parties": len(rows),
        "suppliers": sum(1 for r in rows if r["supplier_id"]),
        "customers": sum(1 for r in rows if r["customer_id"]),
        "active": sum(1 for r in rows if r["status"] == STATUS_ACTIVE),
        "over_limit": sum(1 for r in rows if r["over_limit"]),
        "receivable": sum((r["balance"] for r in rows if r["customer_id"]), ZERO),
        "payable": sum((r["balance"] for r in rows if r["supplier_id"]), ZERO),
    }
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 69. Product Master with Rates
# ---------------------------------------------------------------------------

def product_category_options():
    return ProductNode.objects.filter(level=1).order_by("complete_code").values_list("pk", "name")


def specification_options():
    return PRD_SPECIFICATION_CHOICES


def product_master(category=None, specification="", status=""):
    products = ProductNode.objects.filter(level=PRD_LEVEL_ITEM).select_related("parent__parent").order_by("complete_code")
    if category:
        products = products.filter(parent__parent_id=category)
    if specification:
        products = products.filter(specification=specification)
    if status:
        products = products.filter(status=status)
    history = defaultdict(list)
    for rate in ProductRate.objects.filter(product__in=products).order_by("product_id", "-effective_date", "-pk"):
        history[rate.product_id].append(rate)
    rows = []
    for p in products:
        rates = history.get(p.pk, [])
        current = next((r for r in rates if r.is_current), rates[0] if rates else None)
        previous = next((r for r in rates if current and (r.effective_date, r.pk) < (current.effective_date, current.pk)), None)
        sub = p.parent if p.parent_id else None
        rows.append({
            "pk": p.pk, "code": p.complete_code, "category": sub.parent.name if sub and sub.parent_id else "", "sub_group": sub.name if sub else "",
            "product": p.name, "specification": SPEC_LABELS.get(p.specification, p.specification), "unit": UNIT_LABELS.get(p.unit, p.unit),
            "unit_kg": weight(p.effective_unit_weight), "rate": money(current.rate) if current else None,
            "rate_date": current.effective_date if current else None, "previous_rate": money(previous.rate) if previous else None,
            "rate_change": money(current.rate - previous.rate) if current and previous else None,
            "yield_pct": p.standard_yield_percent, "starting_date": p.starting_date,
            "status": p.status, "status_label": STATUS_LABELS.get(p.status, p.status),
        })
    totals = {
        "products": len(rows),
        "active": sum(1 for r in rows if r["status"] == STATUS_ACTIVE),
        "rated": sum(1 for r in rows if r["rate"] is not None),
        "unrated": sum(1 for r in rows if r["rate"] is None),
        "changed": sum(1 for r in rows if r["previous_rate"] is not None),
    }
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 70. Chart of Accounts with balances
# ---------------------------------------------------------------------------

def account_type_options():
    return FIN_COA_ACCOUNT_TYPE_CHOICES


def chart_of_accounts(account_type="", postable_only=False, nonzero_only=False):
    balances = account_balances()
    accounts = list(ChartOfAccount.objects.order_by("code", "sort_order", "pk"))
    by_id = {a.pk: a for a in accounts}
    children = defaultdict(list)
    for a in accounts:
        children[a.parent_id].append(a)

    def level_of(a):
        depth, node = 1, a
        while node.parent_id and node.parent_id in by_id:
            node, depth = by_id[node.parent_id], depth + 1
        return depth

    figures = {}

    def rollup(a):
        if a.pk in figures:
            return figures[a.pk]
        if children[a.pk]:
            f = {"opening": ZERO, "movement": ZERO, "closing": ZERO}
            for c in children[a.pk]:
                sub = rollup(c)
                for k in f:
                    f[k] += sub[k]
        else:
            own = balances.get(a.code) or {"opening": a.opening_balance or ZERO, "movement": ZERO, "closing": a.opening_balance or ZERO}
            f = dict(own)
        figures[a.pk] = f
        return f

    rows = []

    def walk(parent_id):
        for a in children[parent_id]:
            f = rollup(a)
            level = level_of(a)
            is_group = bool(children[a.pk]) or a.is_group
            rows.append({
                "pk": a.pk, "code": a.code, "level": level, "title": f"{INDENT * (level - 1)}{a.title}", "plain_title": a.title,
                "type": ACCOUNT_TYPE_LABELS.get(a.account_type, a.account_type), "account_type": a.account_type,
                "group": "Group" if is_group else "Account", "is_group": is_group,
                "opening": money(f["opening"]), "movement": money(f["movement"]), "closing": money(f["closing"]),
                "negative": f["closing"] < 0, "status": a.status, "status_label": STATUS_LABELS.get(a.status, a.status),
            })
            walk(a.pk)

    walk(None)
    if account_type:
        rows = [r for r in rows if r["account_type"] == account_type]
    if postable_only:
        rows = [r for r in rows if not r["is_group"]]
    if nonzero_only:
        rows = [r for r in rows if r["opening"] or r["movement"] or r["closing"]]
    postable = [r for r in rows if not r["is_group"]]
    totals = {k: sum((r[k] for r in postable), ZERO) for k in ("opening", "movement", "closing")}
    totals["accounts"] = len(postable)
    totals["groups"] = len(rows) - len(postable)
    totals["by_type"] = {}
    for r in postable:
        totals["by_type"][r["account_type"]] = totals["by_type"].get(r["account_type"], ZERO) + r["closing"]
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# 71. User Access Report
# ---------------------------------------------------------------------------

def role_options():
    from apps.access_control.models import Role

    return Role.objects.filter(status=STATUS_ACTIVE).order_by("title").values_list("pk", "title")


def organization_options():
    from apps.organizations.models import Organization

    return Organization.objects.order_by("title").values_list("pk", "title")


def user_access(role=None, organization=None, active_only=False):
    User = get_user_model()
    assignments = UserAssignment.objects.select_related("role", "organization", "branch").order_by("-is_primary", "role__title")
    users = User.objects.order_by("username").prefetch_related(Prefetch("assignments", queryset=assignments, to_attr="assignment_rows"))
    if active_only:
        users = users.filter(is_active=True)
    if role:
        users = users.filter(assignments__role_id=role).distinct()
    if organization:
        users = users.filter(assignments__organization_id=organization).distinct()
    granted = {
        r["role_id"]: r["n"] for r in RolePermission.objects.filter(permission__status=STATUS_ACTIVE, permission__deleted_at__isnull=True).values("role_id").annotate(n=Count("permission_id", distinct=True))
    }
    rows = []
    for u in users:
        base = {
            "pk": u.pk, "username": u.username, "name": u.get_full_name() or u.name or u.username, "email": u.email or "",
            "user_type": u.get_user_type_display(), "superuser": "Yes" if u.is_superuser else "",
            "last_login": (u.last_login_timestamp or u.last_login).date() if (u.last_login_timestamp or u.last_login) else None,
            "active": "Yes" if u.is_active else "No", "is_active": u.is_active,
            "status": u.status, "status_label": STATUS_LABELS.get(u.status, u.status),
        }
        matching = [
            a for a in u.assignment_rows
            if (not role or a.role_id == int(role)) and (not organization or a.organization_id == int(organization))
        ]
        if not matching:
            rows.append({**base, "role": "", "organization": "", "branch": "", "primary": "", "permissions": 0, "assignment_status": "", "assignment_status_label": ""})
            continue
        for a in matching:
            rows.append({
                **base, "role": a.role.title, "organization": a.organization.title if a.organization_id else "", "branch": a.branch.title if a.branch_id else "",
                "primary": "Yes" if a.is_primary else "", "permissions": granted.get(a.role_id, 0), "start_date": a.start_date, "end_date": a.end_date,
                "assignment_status": a.status, "assignment_status_label": STATUS_LABELS.get(a.status, a.status),
            })
    totals = {
        "users": len({r["pk"] for r in rows}),
        "active": len({r["pk"] for r in rows if r["is_active"]}),
        "inactive": len({r["pk"] for r in rows if not r["is_active"]}),
        "assignments": sum(1 for r in rows if r["role"]),
        "unassigned": len({r["pk"] for r in rows if not r["role"] and not r["superuser"]}),
        "superusers": len({r["pk"] for r in rows if r["superuser"]}),
        "roles": len({r["role"] for r in rows if r["role"]}),
    }
    return {"rows": rows, "totals": totals}
