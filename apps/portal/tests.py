from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.constants import (
    ACCOUNT_TYPE_ASSET,
    PRD_LEDGER_PRODUCTION_IN,
    PRD_LEDGER_PURCHASE,
    PRD_LEDGER_SALE,
    PRD_LEVEL_GROUP,
    PRD_LEVEL_ITEM,
    PRD_LEVEL_SUB_GROUP,
    PRD_SPEC_FINISH_ITEM,
    PRD_SPEC_RAW_ITEM,
    PRD_UNIT_KG,
    PRD_UNIT_PIECE,
    STATUS_POSTED,
    STATUS_REVERSED,
    VOUCHER_TYPE_JOURNAL,
    YES,
)
from apps.core.reporting import Period, PRESET_MONTH, mund, previous_period
from apps.finance.models import ChartOfAccount
from apps.finance.services import _post_voucher, create_customer_receivable_account, create_supplier_payable_account
from apps.godowns.models import Godown
from apps.inventory.models import Customer, POSDetail, POSMaster, PurchaseInvoice, PurchaseInvoiceLine, Supplier
from apps.production.models import GrindingOutput, GrindingVoucher
from apps.products.models import ProductLedger, ProductNode

from . import selectors


class OwnerPackFixture(TestCase):
    """A day of trading: one wheat slip, one grinding run, one atta sale, cash in the till."""

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.user = get_user_model().objects.create_superuser("owner", "owner@example.com", "pass12345")

        raw = ProductNode.objects.create(level=PRD_LEVEL_GROUP, code_segment="01", name="Raw")
        wheat_group = ProductNode.objects.create(parent=raw, level=PRD_LEVEL_SUB_GROUP, code_segment="01", name="Wheat")
        cls.wheat = ProductNode.objects.create(
            parent=wheat_group, level=PRD_LEVEL_ITEM, code_segment="001", name="Wheat Pvt",
            specification=PRD_SPEC_RAW_ITEM, unit=PRD_UNIT_KG, starting_date=cls.today,
        )
        finished = ProductNode.objects.create(level=PRD_LEVEL_GROUP, code_segment="02", name="Finished")
        atta_group = ProductNode.objects.create(parent=finished, level=PRD_LEVEL_SUB_GROUP, code_segment="01", name="Atta")
        cls.atta = ProductNode.objects.create(
            parent=atta_group, level=PRD_LEVEL_ITEM, code_segment="001", name="Atta 20kg",
            specification=PRD_SPEC_FINISH_ITEM, unit=PRD_UNIT_PIECE, unit_weight=Decimal("20"), starting_date=cls.today,
        )
        cls.godown = Godown.objects.create(code="G1", name="Main")

        cls.supplier = Supplier.objects.create(name="Arhti One")
        cls.customer = Customer.objects.create(customer_name="Dealer One", credit_limit=Decimal("1000.00"))
        cls.supplier_account = create_supplier_payable_account(supplier=cls.supplier)
        cls.customer_account = create_customer_receivable_account(customer=cls.customer)

        assets = ChartOfAccount.objects.filter(parent=None, title="ASSETS").first()
        current = ChartOfAccount.objects.filter(parent=assets, title="Current Assets").first()
        cls.cash = ChartOfAccount.objects.create(parent=current, title="Cash", account_type=ACCOUNT_TYPE_ASSET, is_group=False, opening_balance=Decimal("5000.00"))
        ChartOfAccount.rebuild_codes()
        cls.cash.refresh_from_db()
        cls.supplier_account.refresh_from_db()
        cls.customer_account.refresh_from_db()

        invoice = PurchaseInvoice.objects.create(
            supplier=cls.supplier, invoice_date=cls.today, godown=cls.godown, status=STATUS_POSTED,
            goods_amount=Decimal("40000.00"), total_amount=Decimal("40000.00"),
        )
        PurchaseInvoiceLine.objects.create(
            invoice=invoice, product=cls.wheat, seq_num=1, descr="Wheat", quantity=Decimal("4000"), rate=Decimal("10"),
            amount=Decimal("40000.00"), credit_weight=Decimal("4000.000"), rate_per_mund=Decimal("400.00"),
        )
        reversed_invoice = PurchaseInvoice.objects.create(
            supplier=cls.supplier, invoice_date=cls.today, godown=cls.godown, status=STATUS_REVERSED,
            goods_amount=Decimal("999.00"), total_amount=Decimal("999.00"),
        )
        PurchaseInvoiceLine.objects.create(
            invoice=reversed_invoice, product=cls.wheat, seq_num=1, descr="Wheat", quantity=Decimal("99"), rate=Decimal("10"),
            amount=Decimal("999.00"), credit_weight=Decimal("99.000"),
        )
        ProductLedger.objects.create(product=cls.wheat, entry_date=cls.today, source=PRD_LEDGER_PURCHASE, quantity=Decimal("4000"), rate=Decimal("10"), godown=cls.godown)

        voucher = GrindingVoucher.objects.create(
            seq_num=1, voucher_no="WG-1", date=cls.today, production_from=time(8), production_to=time(16),
            wheat_item=cls.wheat, disposal_wheat=Decimal("1000.000"), godown=cls.godown,
            total_output_kg=Decimal("900.000"), yield_percent=Decimal("90"),
        )
        GrindingOutput.objects.create(voucher=voucher, line_number=1, product=cls.atta, quantity=Decimal("45"), unit_weight=Decimal("20"))
        ProductLedger.objects.create(product=cls.wheat, entry_date=cls.today, source="production_out", quantity=Decimal("-1000"), godown=cls.godown)
        ProductLedger.objects.create(product=cls.atta, entry_date=cls.today, source=PRD_LEDGER_PRODUCTION_IN, quantity=Decimal("45"), rate=Decimal("200"), godown=cls.godown)

        sale = POSMaster.objects.create(
            transaction_id="T1", sale_date=cls.today, customer=cls.customer, posted=YES, status=STATUS_POSTED,
            total_amount=Decimal("3000.00"), net_amount=Decimal("3000.00"), total_paid=Decimal("0.00"), balance=Decimal("3000.00"),
        )
        POSDetail.objects.create(
            pos_master=sale, transaction_id="T1", sale_num=sale.sale_num, seq_num=1, product=cls.atta, item_code="A", item_name="Atta 20kg",
            quantity=Decimal("10"), price=Decimal("300"), total_price=Decimal("3000.00"), net_total=Decimal("3000.00"),
        )
        ProductLedger.objects.create(product=cls.atta, entry_date=cls.today, source=PRD_LEDGER_SALE, quantity=Decimal("-10"), rate=Decimal("300"), godown=cls.godown)

        _post_voucher(
            source_ref="TEST-SALE", voucher_type=VOUCHER_TYPE_JOURNAL, voucher_date=cls.today, account_no="",
            entries=[(cls.customer_account.code, Decimal("3000.00"), Decimal("0"), ""), (cls.cash.code, Decimal("0"), Decimal("3000.00"), "")],
            remarks="sale on credit", user=cls.user,
        )
        _post_voucher(
            source_ref="TEST-PURCHASE", voucher_type=VOUCHER_TYPE_JOURNAL, voucher_date=cls.today, account_no="",
            entries=[(cls.cash.code, Decimal("1200.00"), Decimal("0"), ""), (cls.supplier_account.code, Decimal("0"), Decimal("1200.00"), "")],
            remarks="wheat on credit", user=cls.user,
        )


class DailyPositionTests(OwnerPackFixture):
    def test_figures_come_from_posted_documents_and_ledgers(self):
        data = selectors.daily_position(self.today)
        self.assertEqual(data["wheat"]["kg"], Decimal("4000.000"))
        self.assertEqual(data["wheat"]["amount"], Decimal("40000.00"))
        self.assertEqual(data["wheat"]["slips"], 1)
        self.assertEqual(data["grinding"]["wheat_kg"], Decimal("1000.000"))
        self.assertEqual(data["production"][0]["kg"], Decimal("900.000"))
        self.assertEqual(data["sales"]["bags"], Decimal("10.000"))
        self.assertEqual(data["sales"]["net"], Decimal("3000.00"))
        self.assertEqual(data["cash_closing"], Decimal("3200.00"))
        self.assertEqual(data["receivables"], Decimal("3000.00"))
        self.assertEqual(data["payables"], Decimal("1200.00"))
        self.assertEqual(data["wheat_stock"]["stock_kg"], Decimal("3000.000"))
        self.assertEqual(data["wheat_stock"]["days"], Decimal("90.0"))
        self.assertEqual(mund(data["wheat"]["kg"]), Decimal("100.000"))

    def test_a_reversed_slip_counts_as_zero(self):
        self.assertEqual(selectors.wheat_purchased(self.today, self.today)["slips"], 1)


class MonthGlanceTests(OwnerPackFixture):
    def test_running_cash_and_totals(self):
        start = self.today.replace(day=1)
        data = selectors.month_glance(start, self.today)
        today_row = data["rows"][-1]
        self.assertEqual(today_row["purchase_kg"], Decimal("4000.000"))
        self.assertEqual(today_row["cash_in"], Decimal("1200.00"))
        self.assertEqual(today_row["cash_out"], Decimal("3000.00"))
        self.assertEqual(today_row["closing_cash"], Decimal("3200.00"))
        self.assertEqual(data["totals"]["opening_cash"], Decimal("5000.00"))
        self.assertEqual(data["totals"]["sales"], Decimal("3000.00"))
        self.assertEqual(len(data["rows"]), (self.today - start).days + 1)

    def test_previous_period_of_month_to_date(self):
        period = Period(self.today.replace(day=1), self.today, "This Month", PRESET_MONTH)
        before = previous_period(period)
        self.assertEqual(before.end, self.today.replace(day=1) - timedelta(days=1) if period.days > 28 else before.end)
        self.assertLess(before.end, period.start)
        self.assertLessEqual(before.days, period.days)


class ProductProfitTests(OwnerPackFixture):
    def test_margin_uses_ledger_cost_rate(self):
        data = selectors.product_profit(self.today, self.today)
        row = data["rows"][0]
        self.assertEqual(row["product"], "Atta 20kg")
        self.assertEqual(row["qty"], Decimal("10.000"))
        self.assertEqual(row["kg"], Decimal("200.000"))
        self.assertEqual(row["cost_rate"], Decimal("200.00"))
        self.assertEqual(row["cost_source"], "ledger")
        self.assertEqual(row["cogs"], Decimal("2000.00"))
        self.assertEqual(row["margin"], Decimal("1000.00"))
        self.assertEqual(row["margin_pct"], Decimal("33.33"))
        self.assertEqual(data["totals"]["margin"], Decimal("1000.00"))


class AgingTests(OwnerPackFixture):
    def test_receivables_bucket_and_over_limit(self):
        data = selectors.receivables_aging(self.today)
        row = data["rows"][0]
        self.assertEqual(row["balance"], Decimal("3000.00"))
        self.assertEqual(row["b0"], Decimal("3000.00"))
        self.assertTrue(row["over_limit"])
        self.assertEqual(row["over_by"], Decimal("2000.00"))
        later = selectors.receivables_aging(self.today + timedelta(days=45))
        self.assertEqual(later["rows"][0]["b1"], Decimal("3000.00"))
        self.assertEqual(selectors.receivables_aging(self.today, over_limit_only=True)["totals"]["over_limit"], 1)

    def test_payables_bucket_and_kind(self):
        data = selectors.payables_aging(self.today)
        row = data["rows"][0]
        self.assertEqual(row["balance"], Decimal("1200.00"))
        self.assertEqual(row["b0"], Decimal("1200.00"))
        self.assertEqual(row["kind"], "Arhti (wheat)")
        self.assertEqual(selectors.payables_aging(self.today, kind="stores")["rows"], [])


class OwnerReportScreenTests(OwnerPackFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_owner_report_renders_and_exports(self):
        names = ("report_daily_position", "report_month_glance", "report_product_profit", "report_receivables_aging", "report_payables_aging")
        for name in names:
            with self.subTest(report=name):
                response = self.client.get(reverse(f"portal:{name}"))
                self.assertEqual(response.status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    response = self.client.get(reverse(f"portal:{name}_export"), {"format": fmt})
                    self.assertEqual(response.status_code, 200, f"{name} {fmt}")
