from datetime import timedelta
from decimal import Decimal

from django.urls import reverse

from apps.core.constants import STATUS_POSTED, STATUS_SUBMITTED, YES
from apps.core.reporting import GROUP_DAY
from apps.inventory.models import (
    InventoryClass, InventoryItem, PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrder, PurchaseOrderItem,
    PurchaseReturnDetail, PurchaseReturnMaster, UOM,
)
from apps.portal.tests import OwnerPackFixture

from . import selectors_purchase as sel


class PurchaseReportFixture(OwnerPackFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        invoice = PurchaseInvoice.objects.filter(status=STATUS_POSTED).get()
        invoice.vehicle_no = "LEA-123"
        invoice.freight_amount = Decimal("2000.00")
        invoice.freight_paid_by_mill = True
        invoice.brokerage_amount = Decimal("400.00")
        invoice.brokerage_borne_by_supplier = True
        invoice.withholding_rate_per_40kg = Decimal("0.60")
        invoice.withholding_amount = Decimal("60.00")
        invoice.paid_amount = Decimal("10000.00")
        invoice.save()
        cls.invoice = invoice
        line = invoice.items.get()
        line.party_weight = Decimal("4100.000")
        line.mill_weight = Decimal("4050.000")
        line.selected_weight = Decimal("4050.000")
        line.khoot = Decimal("40.500")
        line.moisture = Decimal("9.500")
        line.katla = Decimal("0.000")
        line.save()

        uom = UOM.objects.create(title="Pcs", code="PCS")
        klass = InventoryClass.objects.create(title="Spares", class_code="SP")
        cls.item = InventoryItem.objects.create(item_name="Belt", uom=uom, item_class=klass)
        cls.po = PurchaseOrder.objects.create(supplier=cls.supplier, purchase_date=cls.today - timedelta(days=10), status=STATUS_SUBMITTED, expected_date=cls.today - timedelta(days=1))
        cls.po_item = PurchaseOrderItem.objects.create(
            purchase_order=cls.po, seq_num=1, purchase_num=cls.po.purchase_num, purchase_date=cls.po.purchase_date, inventory_item=cls.item,
            quantity=Decimal("10"), rate=Decimal("500"), qty_invoiced=Decimal("4"), descr="Belt",
        )
        stores = PurchaseInvoice.objects.create(supplier=cls.supplier, purchase_order=cls.po, invoice_date=cls.today, status=STATUS_POSTED, goods_amount=Decimal("2000.00"), total_amount=Decimal("2000.00"))
        cls.stores_line = PurchaseInvoiceLine.objects.create(
            invoice=stores, purchase_order_item=cls.po_item, inventory_item=cls.item, seq_num=1, descr="Belt", quantity=Decimal("4"), rate=Decimal("500"), amount=Decimal("2000.00"), uom=uom,
        )
        ret = PurchaseReturnMaster.objects.create(transaction_id="PR1", purchase_invoice=stores, return_date=cls.today, posted=YES, status=STATUS_POSTED, returned_amount=Decimal("500.00"))
        PurchaseReturnDetail.objects.create(purchase_return_master=ret, invoice_line=cls.stores_line, inventory_item=cls.item, item_code="B", item_name="Belt", quantity=Decimal("1"), rate=Decimal("500"), total_price=Decimal("500.00"), uom=uom)


class PurchaseSelectorTests(PurchaseReportFixture):
    def test_wheat_register_row(self):
        data = sel.wheat_register(self.today, self.today)
        row = data["rows"][0]
        self.assertEqual(row["credit_mund"], Decimal("100.000"))
        self.assertEqual(row["rate_per_mund"], Decimal("400.00"))
        self.assertEqual(row["weight_source"], "Mill")
        self.assertEqual(row["freight_payer"], "Mill")
        self.assertEqual(row["net_payable"], Decimal("40000.00") - Decimal("60.00") - Decimal("2000.00") - Decimal("400.00"))
        self.assertEqual(data["totals"]["slips"], 1)
        self.assertEqual(sel.wheat_register(self.today, self.today, weight_source="party")["totals"]["slips"], 0)

    def test_summary_and_trend(self):
        row = sel.purchase_summary(self.today, self.today, GROUP_DAY)["rows"][0]
        self.assertEqual(row["mund"], Decimal("100.000"))
        self.assertEqual(row["avg_rate"], Decimal("400.00"))
        self.assertEqual(row["wht"], Decimal("60.00"))
        self.assertEqual(row["balance"], Decimal("30000.00"))
        trend = sel.rate_trend(self.today, self.today, GROUP_DAY)
        self.assertEqual(trend["rows"][0]["min_rate"], Decimal("400.00"))

    def test_arhti_quality_and_charges(self):
        arhti = sel.supplier_purchases(self.today, self.today)["rows"][0]
        self.assertEqual(arhti["avg_impurities"], Decimal("1.00"))
        quality = sel.wheat_quality(self.today, self.today, threshold=Decimal("0.5"))
        self.assertEqual(quality["totals"]["flagged"], 1)
        self.assertEqual(quality["rows"][0]["moisture"], Decimal("0.23"))
        charges = sel.freight_brokerage(self.today, self.today)["totals"]
        self.assertEqual(charges["freight_mill"], Decimal("2000.00"))
        self.assertEqual(charges["brokerage_supplier"], Decimal("400.00"))
        self.assertEqual(sel.wht_register(self.today, self.today)["totals"]["wht"], Decimal("60.00"))

    def test_stores_orders_returns_payments(self):
        stores = sel.stores_register(self.today, self.today)
        self.assertEqual(stores["rows"][0]["match"], "Against order")
        self.assertEqual(stores["totals"]["amount"], Decimal("2000.00"))
        orders = sel.order_fulfilment(self.today - timedelta(days=30), self.today, as_of=self.today)
        self.assertEqual(orders["rows"][0]["pending"], Decimal("6.000"))
        self.assertTrue(orders["rows"][0]["overdue"])
        self.assertEqual(orders["totals"]["overdue"], 1)
        returns = sel.purchase_returns(self.today, self.today)
        self.assertEqual(returns["totals"]["returned"], Decimal("500.00"))
        pay = sel.supplier_payment_status(self.today)["rows"][0]
        self.assertEqual(pay["invoiced"], Decimal("42000.00"))
        self.assertEqual(pay["paid"], Decimal("10000.00"))
        self.assertEqual(pay["balance"], Decimal("1200.00"))


class PurchaseScreenTests(PurchaseReportFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_purchase_report_renders_and_exports(self):
        names = ("report_purchase", "report_purchase_summary", "report_supplier_purchases", "report_wheat_quality", "report_wheat_rate_trend",
                 "report_freight_brokerage", "report_wht", "report_stores_purchases", "report_pending_orders", "report_purchase_return", "report_supplier_payments")
        for name in names:
            with self.subTest(report=name):
                response = self.client.get(reverse(f"inventory:{name}"), {"preset": "year", "threshold": "0.5"})
                self.assertEqual(response.status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    response = self.client.get(reverse(f"inventory:{name}_export"), {"format": fmt, "preset": "year"})
                    self.assertEqual(response.status_code, 200, f"{name} {fmt}")
