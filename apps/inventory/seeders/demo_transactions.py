"""Demo purchase documents for the mill.

Everything goes through the real services rather than writing rows directly,
so the demo data exercises the same validation, numbering, stock movement,
product ledger, item ledger and general ledger postings the screens do.

Each document carries a marker in a field the user can see, so re-running the
seeder recognises its own work and stays idempotent.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core.constants import (
    GL_BROKERS_GROUP_PATH,
    INV_BARDANA_MILL,
    INV_BARDANA_PARTY,
    INV_BARDANA_RETURNABLE,
    STATUS_ACTIVE,
    STATUS_DRAFT,
)
from apps.finance.models import ChartOfAccount
from apps.finance.services import gl_account
from apps.godowns.models import Godown
from apps.inventory.models import InventoryItem, PurchaseInvoice, PurchaseOrder, Supplier
from apps.inventory.seeders.suppliers import (
    BARDANA_SUPPLIER_CODES,
    STORES_SUPPLIER_CODES,
    WHEAT_SUPPLIER_CODES,
)
from apps.inventory.services import (
    approve_purchase_order,
    create_purchase_invoice,
    create_purchase_order,
)
from apps.products.models import ProductNode, RawBardanaLink

PO_MARKER = "DEMO-Q-%03d"
INVOICE_MARKER = "DEMO-INV-%03d"
STORES_MARKER = "DEMO-STR-%03d"
BARDANA_MARKER = "DEMO-BRD-%03d"
WHEAT_REMARK = "DEMO-WHT-%03d"

BROKERS = ("Haji Sadiq Broker", "Mian Aslam Commission Agent", "Ch. Riaz Broker")
WHEAT_CODES = ("01-01-001", "01-01-002", "01-02-001")
BAG_CODES = ("03-01-001", "03-01-002", "03-01-003", "03-02-002", "03-02-003", "03-02-004",
             "03-02-007", "03-02-008", "03-02-009", "03-02-011", "03-02-001", "03-02-006")
RATE_PER_MUND = (Decimal("4830"), Decimal("4790"), Decimal("4860"), Decimal("4750"), Decimal("4900"))
LOADS_KG = (Decimal("74567"), Decimal("38420"), Decimal("52110"), Decimal("61880"), Decimal("29760"), Decimal("45300"))
VEHICLES = ("JV-7454", "LES-3321", "SGD-8810", "FDA-1207", "MNC-4478", "LEB-9902")
TRANSPORTERS = ("Goods Transport Co", "Bismillah Goods", "Al-Madina Carriage", "Punjab Goods Forwarders")


def _node(code: str):
    return ProductNode.objects.filter(complete_code=code).first()


def _suppliers(codes):
    return list(Supplier.objects.filter(code__in=codes).order_by("code"))


def _mill_godown():
    return Godown.objects.filter(status=STATUS_ACTIVE).order_by("pk").first()


def _brokers(user):
    heading = gl_account(GL_BROKERS_GROUP_PATH, user=user)
    accounts = []
    for title in BROKERS:
        account = ChartOfAccount.objects.filter(parent=heading, title=title).first()
        if account is None:
            next_order = (
                ChartOfAccount.objects.filter(parent=heading).order_by("-sort_order")
                .values_list("sort_order", flat=True).first() or 0
            ) + 1
            account = ChartOfAccount.objects.create(
                parent=heading, title=title, account_type=heading.account_type,
                is_group=False, sort_order=next_order, created_by=user, updated_by=user,
            )
            ChartOfAccount.rebuild_codes()
            account.refresh_from_db()
        accounts.append(account)
    return accounts


def _rate_for(item, index):
    rate = item.purchase_price or item.price or Decimal("0")
    if rate <= 0:
        rate = Decimal(250 + (index % 20) * 35)
    return Decimal(rate).quantize(Decimal("0.01"))


def seed_demo_wheat_purchases(count: int = 50, *, user=None) -> int:
    """Wheat slips off the gate: weighed loads, sacks, freight, broker, WHT."""
    suppliers = _suppliers(WHEAT_SUPPLIER_CODES)
    wheats = [w for w in (_node(code) for code in WHEAT_CODES) if w is not None]
    godown = _mill_godown()
    if not suppliers or not wheats or godown is None:
        return 0

    bags = {link.wheat_item_id: link.bardana_item for link in RawBardanaLink.objects.select_related("bardana_item")}
    brokers = _brokers(user)
    ownerships = (INV_BARDANA_MILL, INV_BARDANA_MILL, INV_BARDANA_PARTY, INV_BARDANA_MILL, INV_BARDANA_RETURNABLE, INV_BARDANA_MILL)
    today = timezone.localdate()
    created_count = 0

    for index in range(1, count + 1):
        remark = WHEAT_REMARK % index
        if PurchaseInvoice.all_objects.filter(remarks=remark).exists():
            continue

        wheat = wheats[(index - 1) % len(wheats)]
        bag = bags.get(wheat.pk)
        if bag is None:
            continue

        load = LOADS_KG[(index - 1) % len(LOADS_KG)]
        tare = Decimal(9800 + (index % 7) * 350)
        mill_load = load + tare
        party_load = mill_load + Decimal(index % 5) * Decimal("20")
        katla = (load * Decimal("0.004")).quantize(Decimal("0.001")) if index % 3 == 0 else None
        moisture = (load * Decimal("0.006")).quantize(Decimal("0.001")) if index % 4 == 0 else None
        sacks = (load / Decimal("100")).quantize(Decimal("1"))
        ownership = ownerships[(index - 1) % len(ownerships)]
        bag_rate = Decimal("85") if ownership == INV_BARDANA_MILL and index % 2 == 0 else Decimal("0")
        sack_deduction = sacks * Decimal("0.5") if ownership == INV_BARDANA_MILL else Decimal("0")

        wheat_line = {
            "product": wheat,
            "party_load_weight": party_load,
            "party_tare_weight": tare,
            "mill_load_weight": mill_load,
            "mill_tare_weight": tare,
            "party_weight": party_load - tare,
            "mill_weight": load,
            "selected_weight": load,
            "katla": katla,
            "khoot": None,
            "moisture": moisture,
            "sack_weight_deduction": sack_deduction or None,
            "rate_per_mund": RATE_PER_MUND[(index - 1) % len(RATE_PER_MUND)],
        }
        bardana_line = {
            "product": bag,
            "quantity": sacks,
            "rate": bag_rate,
            "bardana_ownership": ownership,
        }

        freight = (load / Decimal("40") * Decimal("242")).quantize(Decimal("0.01"))
        create_purchase_invoice(
            supplier=suppliers[(index - 1) % len(suppliers)],
            supplier_invoice_num="",
            invoice_date=today - timedelta(days=count - index),
            lines=[wheat_line, bardana_line],
            freight_amount=freight,
            freight_paid_by_mill=True,
            brokerage_borne_by_supplier=True,
            remarks=remark,
            godown=godown,
            vehicle_no=VEHICLES[(index - 1) % len(VEHICLES)],
            broker=brokers[(index - 1) % len(brokers)] if index % 5 else None,
            brokerage_rate_per_100kg=Decimal("10.00") if index % 5 else Decimal("0"),
            withholding_rate_per_40kg=Decimal("0.60"),
            extra_data={
                "transporter": TRANSPORTERS[(index - 1) % len(TRANSPORTERS)],
                "driver_phone": f"0300-{7100000 + index}",
                "builty_no": f"B-{4400 + index}",
            },
            user=user,
        )
        created_count += 1

    return created_count


def seed_demo_bardana_purchases(count: int = 50, *, user=None) -> int:
    """Sacks and bags bought from bardana traders: product lines on an ordinary invoice."""
    suppliers = _suppliers(BARDANA_SUPPLIER_CODES)
    bags = [b for b in (_node(code) for code in BAG_CODES) if b is not None]
    godown = _mill_godown()
    if not suppliers or not bags or godown is None:
        return 0

    today = timezone.localdate()
    created_count = 0
    for index in range(1, count + 1):
        bill_number = BARDANA_MARKER % index
        if PurchaseInvoice.all_objects.filter(supplier_invoice_num=bill_number).exists():
            continue

        lines = []
        for offset in range(3):
            bag = bags[(index * 3 + offset) % len(bags)]
            lines.append({
                "product": bag,
                "quantity": Decimal(20000 + (index % 6) * 5000),
                "rate": Decimal(22 + (index + offset) % 7 * 6),
            })

        create_purchase_invoice(
            supplier=suppliers[(index - 1) % len(suppliers)],
            supplier_invoice_num=bill_number,
            supplier_invoice_date=today - timedelta(days=count - index + 2),
            invoice_date=today - timedelta(days=count - index + 2),
            lines=lines,
            remarks=f"Bardana lot {index}",
            godown=godown,
            user=user,
        )
        created_count += 1

    return created_count


def seed_demo_purchase_orders(count: int = 50, *, user=None) -> int:
    """Orders on the stores suppliers for spares and consumables."""
    suppliers = _suppliers(STORES_SUPPLIER_CODES)
    items = list(InventoryItem.objects.order_by("pk"))
    if not suppliers or not items:
        return 0

    today = timezone.localdate()
    created_count = 0

    for index in range(1, count + 1):
        quot_num = PO_MARKER % index
        if PurchaseOrder.all_objects.filter(quot_num=quot_num).exists():
            continue

        supplier = suppliers[(index - 1) % len(suppliers)]
        order_date = today - timedelta(days=count - index + 5)
        lines = []
        for offset in range((index % 3) + 1):
            item = items[(index + offset) % len(items)]
            lines.append({
                "inventory_item": item,
                "quantity": Decimal(2 + (index % 8) * 3),
                "rate": _rate_for(item, index + offset),
            })

        awaiting_approval = index % 10 == 0
        order, _net = create_purchase_order(
            supplier=supplier,
            quot_num=quot_num,
            quot_date=order_date,
            order_date=order_date,
            lines=lines,
            expected_date=order_date + timedelta(days=7),
            remarks=f"Stores requisition {index}",
            status=STATUS_DRAFT,
            user=user,
        )
        if not awaiting_approval:
            approve_purchase_order(order=order, user=user)
        created_count += 1

    return created_count


def seed_demo_purchase_invoices(count: int = 50, *, user=None) -> int:
    """Invoice the submitted orders. This is what brings stores stock in."""
    today = timezone.localdate()
    created_count = 0

    orders = list(
        PurchaseOrder.objects.filter(quot_num__startswith="DEMO-Q-")
        .exclude(status=STATUS_DRAFT)
        .order_by("pk")
    )

    for index, order in enumerate(orders[:count], start=1):
        invoice_num = INVOICE_MARKER % index
        if PurchaseInvoice.all_objects.filter(supplier=order.supplier, supplier_invoice_num=invoice_num).exists():
            continue

        lines = []
        for order_item in order.items.all():
            pending = order_item.qty_pending
            if pending <= 0:
                continue
            quantity = pending if index % 4 else (pending / 2).quantize(Decimal("0.0001"))
            if quantity <= 0:
                continue
            lines.append({
                "order_item": order_item,
                "inventory_item": order_item.inventory_item,
                "quantity": quantity,
                "rate": order_item.rate,
            })

        if not lines:
            continue

        invoice_date = min(order.purchase_date + timedelta(days=4), today)
        create_purchase_invoice(
            supplier=order.supplier,
            supplier_invoice_num=invoice_num,
            supplier_invoice_date=invoice_date,
            invoice_date=invoice_date,
            lines=lines,
            tax_amount=Decimal("0"),
            remarks=f"Against {order.purchase_num}",
            user=user,
        )
        created_count += 1

    return created_count


def seed_demo_stores_purchases(count: int = 50, *, user=None) -> int:
    """Spares and consumables bought straight off the supplier's bill, no order."""
    suppliers = _suppliers(STORES_SUPPLIER_CODES)
    items = list(InventoryItem.objects.order_by("pk"))
    if not suppliers or not items:
        return 0

    today = timezone.localdate()
    created_count = 0

    for index in range(1, count + 1):
        bill_number = STORES_MARKER % index
        if PurchaseInvoice.all_objects.filter(supplier_invoice_num=bill_number).exists():
            continue

        supplier = suppliers[(index + 2) % len(suppliers)]
        lines = []
        goods_total = Decimal("0.00")
        for offset in range((index % 3) + 1):
            item = items[(index * 2 + offset) % len(items)]
            quantity = Decimal(1 + (index % 10) * 2)
            rate = _rate_for(item, index + offset)
            goods_total += (quantity * rate).quantize(Decimal("0.01"))
            lines.append({"inventory_item": item, "quantity": quantity, "rate": rate})

        paid = goods_total if index % 3 == 0 else (goods_total / 2).quantize(Decimal("0.01"))
        bill_date = today - timedelta(days=count - index + 1)

        create_purchase_invoice(
            supplier=supplier,
            supplier_invoice_num=bill_number,
            supplier_invoice_date=bill_date,
            invoice_date=bill_date,
            lines=lines,
            paid_amount=paid,
            remarks=f"Cash memo {index}",
            user=user,
        )
        created_count += 1

    return created_count
