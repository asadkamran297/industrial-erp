from datetime import timedelta
from decimal import Decimal

from django.urls import reverse

from apps.inventory.models import ItemLedger, ManualTransaction, Stock
from apps.inventory.tests_reports_purchase import PurchaseReportFixture

from . import selectors_stock as sel


class StockFixture(PurchaseReportFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Stock.objects.update_or_create(inventory_item=cls.item, defaults={"item_code": "B", "item_name": "Belt", "current_quantity": Decimal("3"), "current_price": Decimal("500")})
        ItemLedger.objects.create(transaction_id="L1", inventory_item=cls.item, item_code="B", item_name="Belt", transaction_type="receive", transaction_date=cls.today - timedelta(days=40),
                                  ref_table="x", ref_id=1, quantity=Decimal("4"), old_quantity=Decimal("0"), new_quantity=Decimal("4"), old_price=Decimal("0"), current_price=Decimal("500"))
        ItemLedger.objects.create(transaction_id="L2", inventory_item=cls.item, item_code="B", item_name="Belt", transaction_type="purchase_return", transaction_date=cls.today,
                                  ref_table="x", ref_id=2, quantity=Decimal("1"), old_quantity=Decimal("4"), new_quantity=Decimal("3"), old_price=Decimal("500"), current_price=Decimal("500"))
        ManualTransaction.objects.create(transaction_id="MT1", supplier=cls.supplier, inventory_item=cls.item, item_code="B", item_name="Belt", qty=Decimal("-1"), price=Decimal("500"), descr="damaged", created_by=cls.user)


class StockSelectorTests(StockFixture):
    def test_mill_and_stores_stock(self):
        mill = sel.mill_stock(self.today, self.today)
        wheat = next(r for r in mill["rows"] if r["family"] == "Wheat")
        self.assertEqual(wheat["qty_in"], Decimal("4000.000"))
        self.assertEqual(wheat["closing"], Decimal("3000.000"))
        self.assertEqual(wheat["closing_mund"], Decimal("75.000"))
        stores = sel.stores_stock(self.today, self.today)["rows"][0]
        self.assertEqual(stores["opening"], Decimal("4.000"))
        self.assertEqual(stores["qty_out"], Decimal("1.000"))
        self.assertEqual(stores["closing"], Decimal("3.000"))
        self.assertEqual(stores["value"], Decimal("1500.00"))

    def test_ageing_adjustments_godown_days(self):
        slow = sel.slow_moving(self.today + timedelta(days=45), book="stores")
        self.assertEqual(slow["rows"][0]["bucket"], "30-59")
        adj = sel.adjustment_register(self.today, self.today)
        self.assertEqual(adj["totals"]["qty_out"], Decimal("1.000"))
        self.assertEqual(adj["rows"][0]["reason"], "damaged")
        godown = sel.godown_stock(self.today)
        self.assertEqual(godown["totals"]["wheat_kg"], Decimal("3000.000"))
        self.assertEqual(godown["totals"]["stores_value"], Decimal("1500.00"))
        days = sel.wheat_days_trend(self.today)
        self.assertEqual(days["latest"]["stock_kg"], Decimal("3000.000"))
        self.assertEqual(days["latest"]["days"], Decimal("90.0"))


class StockScreenTests(StockFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_stock_report_renders_and_exports(self):
        for name in ("report_mill_stock", "report_stores_stock", "report_slow_moving", "report_stock_adjustments", "report_godown_stock", "report_wheat_days"):
            with self.subTest(report=name):
                self.assertEqual(self.client.get(reverse(f"inventory:{name}"), {"preset": "month"}).status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    self.assertEqual(self.client.get(reverse(f"inventory:{name}_export"), {"format": fmt, "preset": "month"}).status_code, 200, f"{name} {fmt}")
