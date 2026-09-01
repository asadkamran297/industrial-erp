"""Demo purchase and sale documents.

Everything here goes through the real services rather than writing rows
directly, so the demo data exercises the same validation, numbering, stock
movement, item ledger and general ledger postings the screens do. That is the
point: data built behind the services proves nothing about the flow.

Each document carries a marker in a field the user can see, so re-running the
seeder recognises its own work and stays idempotent.
"""

from decimal import Decimal

from django.utils import timezone

from apps.core.constants import STATUS_DRAFT
from apps.inventory.models import Customer, InventoryItem, PurchaseBill, PurchaseOrder, POSMaster, Stock, Supplier
from apps.inventory.services import (
    approve_purchase_order,
    create_direct_purchase,
    create_direct_sale,
    create_purchase_bill,
    create_purchase_order,
)

PO_MARKER = "DEMO-Q-%03d"
BILL_MARKER = "DEMO-INV-%03d"
DIRECT_PURCHASE_MARKER = "DEMO-PINV-%03d"
SALE_MARKER = "DEMO-SALE-%03d"


def _rate_for(item, index):
    """A believable buying rate: the item's own price, or a stepped fallback."""
    rate = item.purchase_price or item.price or Decimal("0")
    if rate <= 0:
        rate = Decimal(250 + (index % 20) * 35)
    return Decimal(rate).quantize(Decimal("0.01"))


def seed_demo_purchase_orders(count: int = 50, *, user=None) -> int:
    """Raise ``count`` purchase orders, a tenth of them left awaiting approval."""
    suppliers = list(Supplier.objects.order_by("pk"))
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
        # Two or three lines per order so the detail screen is not a single row.
        lines = []
        for offset in range((index % 3) + 1):
            item = items[(index + offset) % len(items)]
            lines.append({
                "inventory_item": item,
                "quantity": Decimal(10 + (index % 15) * 5),
                "rate": _rate_for(item, index + offset),
            })

        # Every tenth order stays a draft so the approval queue is not empty;
        # the rest go through the approval service rather than being written
        # straight to the approved state.
        awaiting_approval = index % 10 == 0
        # create_purchase_order returns (order, net_amount).
        order, _net = create_purchase_order(
            supplier=supplier,
            quot_num=quot_num,
            quot_date=today,
            order_date=today,
            lines=lines,
            expected_date=today,
            remarks=f"Demo purchase order {index}",
            status=STATUS_DRAFT,
            user=user,
        )
        if not awaiting_approval:
            approve_purchase_order(order=order, user=user)
        created_count += 1

    return created_count


def seed_demo_purchase_bills(count: int = 50, *, user=None) -> int:
    """Bill the approved orders. This is what brings stock in and books the debt."""
    today = timezone.localdate()
    created_count = 0

    orders = list(
        PurchaseOrder.objects.filter(quot_num__startswith="DEMO-Q-")
        .exclude(status=STATUS_DRAFT)
        .order_by("pk")
    )

    for index, order in enumerate(orders[:count], start=1):
        invoice_num = BILL_MARKER % index
        if PurchaseBill.all_objects.filter(supplier=order.supplier, supplier_invoice_num=invoice_num).exists():
            continue

        lines = []
        for order_item in order.items.all():
            pending = order_item.pending_bill_qty
            if pending <= 0:
                continue
            # Most bills arrive complete; every fourth is short so the partially
            # billed state is represented too.
            quantity = pending if index % 4 else (pending / 2).quantize(Decimal("0.0001"))
            if quantity <= 0:
                continue
            lines.append({"order_item": order_item, "quantity": quantity, "rate": order_item.rate})

        if not lines:
            continue

        create_purchase_bill(
            supplier=order.supplier,
            supplier_invoice_num=invoice_num,
            supplier_invoice_date=today,
            bill_date=today,
            lines=lines,
            tax_amount=Decimal("0"),
            remarks=f"Demo supplier bill {index}",
            user=user,
        )
        created_count += 1

    return created_count


def seed_demo_direct_purchases(count: int = 50, *, user=None) -> int:
    """Purchases typed straight off the supplier's bill, with no order first.

    These are what the purchase invoice board lists: the same tables as an
    ordered purchase, flagged ``is_direct`` so they stay off the outstanding
    orders list. Seeded separately because the ordered route above never
    produces one.
    """
    suppliers = list(Supplier.objects.order_by("pk"))
    items = list(InventoryItem.objects.order_by("pk"))
    if not suppliers or not items:
        return 0

    today = timezone.localdate()
    created_count = 0

    for index in range(1, count + 1):
        bill_number = DIRECT_PURCHASE_MARKER % index
        if PurchaseOrder.all_objects.filter(quot_num=bill_number, is_direct=True).exists():
            continue

        # Offset into the item list so these do not buy the same rows the
        # ordered purchases did, and the stock spread stays wide.
        supplier = suppliers[(index + 2) % len(suppliers)]
        lines = []
        goods_total = Decimal("0.00")
        for offset in range((index % 3) + 1):
            item = items[(index * 2 + offset) % len(items)]
            quantity = Decimal(8 + (index % 12) * 4)
            rate = _rate_for(item, index + offset)
            goods_total += (quantity * rate).quantize(Decimal("0.01"))
            lines.append({"inventory_item": item, "quantity": quantity, "rate": rate})

        # Every third invoice is settled in full, the rest part-paid, so the
        # supplier ledger carries both states.
        paid = goods_total if index % 3 == 0 else (goods_total / 2).quantize(Decimal("0.01"))

        create_direct_purchase(
            supplier=supplier,
            bill_number=bill_number,
            bill_date=today,
            lines=lines,
            paid_amount=paid,
            remarks=f"Demo purchase invoice {index}",
            user=user,
        )
        created_count += 1

    return created_count


def seed_demo_sales(count: int = 50, *, user=None) -> int:
    """Sell out of the stock the bills brought in."""
    customers = list(Customer.objects.filter(customer_code__startswith="CUST").order_by("pk"))
    if not customers:
        customers = list(Customer.objects.order_by("pk"))
    if not customers:
        return 0

    today = timezone.localdate()
    created_count = 0

    for index in range(1, count + 1):
        marker = SALE_MARKER % index
        if POSMaster.all_objects.filter(remarks=marker).exists():
            continue

        # Read stock fresh each time: earlier sales in this loop consumed some.
        in_stock = list(
            Stock.objects.filter(current_quantity__gt=1)
            .select_related("inventory_item")
            .order_by("-current_quantity")[:40]
        )
        if not in_stock:
            break

        stock = in_stock[(index - 1) % len(in_stock)]
        available = stock.current_quantity
        quantity = (available / 4).quantize(Decimal("0.01"))
        if quantity <= 0:
            continue

        item = stock.inventory_item
        # Sell at the item's list price, or a margin over cost when it has none.
        price = item.price or (stock.current_price * Decimal("1.2"))
        # create_direct_sale returns (sale, net_amount); the sale is posted inside.
        create_direct_sale(
            customer=customers[(index - 1) % len(customers)],
            sale_date=today,
            lines=[{"inventory_item": item, "quantity": quantity, "price": Decimal(price).quantize(Decimal("0.01"))}],
            remarks=marker,
            user=user,
        )
        created_count += 1

    return created_count
