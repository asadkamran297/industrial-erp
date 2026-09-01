"""Put realistic market prices on the placeholder items left over from testing.

The seeded catalogue is priced sensibly, but a handful of hand-made rows carry
values that are obviously wrong — most visibly a laptop costing 635 million,
which on its own accounted for the entire gap between stock on hand and the
Inventory control account.

Prices are PKR and reflect ordinary retail for the Pakistani market. A cost
below its own selling price is the point: the margin is what shows up as gross
profit once the stock is sold.

Run ``--dry-run`` to see the changes without writing them.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.inventory.models import (
    InventoryItem,
    PurchaseOrderItem,
    Stock,
)

# item_code -> (unit cost, selling price)
MARKET_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    # Laptops. Entry, mid and high spec rather than three identical rows, so the
    # test data reads like a real product line.
    "ELC-0001": (Decimal("78000.00"), Decimal("89000.00")),
    "EL2-0001": (Decimal("135000.00"), Decimal("155000.00")),
    "EL3-0001": (Decimal("210000.00"), Decimal("240000.00")),
    # A 24" LED set retails around 30,000; cost was above its own sale price.
    "E01-26": (Decimal("26000.00"), Decimal("30000.00")),
}


class Command(BaseCommand):
    help = "Reprice leftover test items to realistic PKR market values."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        zero = Decimal("0.00")

        before_value = self._stock_value()
        changed = 0

        header = f"{'code':<12}{'item':<22}{'qty':>8}{'cost':>18}{'->':^5}{'cost':>14}{'price':>12}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        for code, (cost, price) in MARKET_PRICES.items():
            stock = Stock.objects.filter(item_code=code).first()
            item = InventoryItem.objects.filter(code=code).first()
            if not stock and not item:
                self.stdout.write(self.style.WARNING(f"{code:<12}not found — skipped"))
                continue

            name = (stock.item_name if stock else item.item_name)[:20]
            qty = stock.current_quantity if stock else zero
            old_cost = stock.current_price if stock else zero
            self.stdout.write(f"{code:<12}{name:<22}{qty:>8,.2f}{old_cost:>18,.2f}{'->':^5}{cost:>14,.2f}{price:>12,.2f}")

            if dry_run:
                continue

            if stock:
                # last_price keeps the previous cost, which is what the ledger
                # reports as the prior valuation.
                stock.last_price = old_cost
                stock.current_price = cost
                stock.save(update_fields=["last_price", "current_price", "updated_at"])
            if item:
                item.price = price
                item.save(update_fields=["price", "updated_at"])

            # The purchase trail carries its own copy of the price. Left alone,
            # the bad figure keeps driving the purchase report and the
            # dashboard trend even after stock has been corrected.
            if item:
                PurchaseOrderItem.all_objects.filter(inventory_item=item).update(
                    rate=cost, retail_price=cost
                )
            changed += 1

        after_value = before_value if dry_run else self._stock_value()
        self.stdout.write("")
        self.stdout.write(f"stock value before : {before_value:>22,.2f}")
        self.stdout.write(f"stock value after  : {after_value:>22,.2f}")

        if dry_run:
            self.stdout.write(self.style.WARNING("dry run — nothing saved"))
        else:
            self.stdout.write(self.style.SUCCESS(f"{changed} item(s) repriced."))
            self.stdout.write(
                "Inventory valuation has moved. Reconcile the Inventory control "
                "account from Finance > Inventory Valuation."
            )

    @staticmethod
    def _stock_value():
        return sum(
            (s.current_quantity * s.current_price for s in Stock.objects.all()),
            Decimal("0.00"),
        )
