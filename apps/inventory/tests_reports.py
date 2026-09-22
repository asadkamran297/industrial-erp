from decimal import Decimal

from django.urls import reverse

from apps.core.constants import PAY_MODE_CASH, PAY_MODE_CREDIT, STATUS_POSTED, VOUCHER_TYPE_RECEIPT, YES
from apps.core.reporting import GROUP_DAY, GROUP_MONTH
from apps.finance.services import _post_voucher
from apps.inventory.models import POSDetail, POSMaster, POSReturnDetail, POSReturnMaster
from apps.portal.tests import OwnerPackFixture
from apps.products.models import ProductRate

from . import selectors


class SalesReportFixture(OwnerPackFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        sale = POSMaster.objects.get(transaction_id="T1")
        sale.pay_mode = PAY_MODE_CREDIT
        sale.posted_by = cls.user
        sale.save()
        cash_sale = POSMaster.objects.create(
            transaction_id="T2", sale_date=cls.today, customer=cls.customer, posted=YES, status=STATUS_POSTED, pay_mode=PAY_MODE_CASH,
            posted_by=cls.user, total_amount=Decimal("560.00"), net_amount=Decimal("560.00"), total_paid=Decimal("560.00"), balance=Decimal("0.00"),
        )
        POSDetail.objects.create(
            pos_master=cash_sale, transaction_id="T2", sale_num=cash_sale.sale_num, seq_num=1, product=cls.atta, item_code="A", item_name="Atta 20kg",
            quantity=Decimal("2"), price=Decimal("280"), total_price=Decimal("560.00"), net_total=Decimal("560.00"),
        )
        ProductRate.objects.create(product=cls.atta, rate=Decimal("300.00"), effective_date=cls.today, is_current=True)
        detail = POSDetail.objects.get(transaction_id="T1")
        ret = POSReturnMaster.objects.create(
            transaction_id="R1", pos_master=sale, sale_transaction_id="T1", sale_num=sale.sale_num, return_date=cls.today,
            customer=cls.customer, posted=YES, status=STATUS_POSTED, total_invoice_amount=Decimal("3000.00"), returned_amount=Decimal("300.00"),
        )
        POSReturnDetail.objects.create(
            pos_return_master=ret, pos_master=sale, pos_detail=detail, transaction_id="R1", return_num=ret.return_num or "SR-1", seq_num=1,
            product=cls.atta, item_code="A", item_name="Atta 20kg", quantity=Decimal("1"), price=Decimal("300"), total_price=Decimal("300.00"), net_total=Decimal("300.00"),
        )
        _post_voucher(
            source_ref="TEST-RECEIPT", voucher_type=VOUCHER_TYPE_RECEIPT, voucher_date=cls.today, account_no=cls.cash.code,
            entries=[(cls.cash.code, Decimal("1000.00"), Decimal("0"), ""), (cls.customer_account.code, Decimal("0"), Decimal("1000.00"), "")],
            remarks="part payment", user=cls.user,
        )


class SalesSelectorTests(SalesReportFixture):
    def test_register_totals(self):
        data = selectors.sales_register(self.today, self.today)
        t = data["totals"]
        self.assertEqual(t["invoices"], 2)
        self.assertEqual(t["bags"], Decimal("12.000"))
        self.assertEqual(t["kg"], Decimal("240.000"))
        self.assertEqual(t["net"], Decimal("3560.00"))
        self.assertEqual(t["cash"], Decimal("560.00"))
        self.assertEqual(t["credit"], Decimal("3000.00"))
        self.assertEqual(selectors.sales_register(self.today, self.today, pay_mode=PAY_MODE_CASH)["totals"]["invoices"], 1)

    def test_summary_by_day_and_month(self):
        for group in (GROUP_DAY, GROUP_MONTH):
            data = selectors.sales_summary(self.today, self.today, group)
            row = data["rows"][0]
            self.assertEqual(row["invoices"], 2)
            self.assertEqual(row["net"], Decimal("3560.00"))
            self.assertEqual(row["returns"], Decimal("300.00"))
            self.assertEqual(row["net_of_returns"], Decimal("3260.00"))
            self.assertEqual(row["bags"], Decimal("12.000"))

    def test_customer_sales_received_and_balance(self):
        row = selectors.customer_sales(self.today, self.today)["rows"][0]
        self.assertEqual(row["net"], Decimal("3560.00"))
        self.assertEqual(row["returns"], Decimal("300.00"))
        self.assertEqual(row["received"], Decimal("1000.00"))
        self.assertEqual(row["balance"], Decimal("2000.00"))
        self.assertEqual(row["last_sale"], self.today)

    def test_product_sales_share(self):
        data = selectors.product_sales(self.today, self.today)
        row = data["rows"][0]
        self.assertEqual(row["bags"], Decimal("12.000"))
        self.assertEqual(row["share"], Decimal("100.00"))
        self.assertEqual(row["avg_rate"], Decimal("296.67"))

    def test_rate_history_variance(self):
        data = selectors.rate_history(self.today, self.today)
        below = [row for row in data["rows"] if row["variance"] is not None and row["variance"] < 0]
        self.assertEqual(len(below), 1)
        self.assertEqual(below[0]["variance"], Decimal("-20.00"))
        self.assertEqual(data["totals"]["given_away"], Decimal("-40.00"))

    def test_sale_returns_and_day_sheet(self):
        returns = selectors.sale_returns(self.today, self.today)
        self.assertEqual(returns["totals"]["returned"], Decimal("300.00"))
        self.assertEqual(returns["rows"][0]["kg"], Decimal("20.000"))
        sheet = selectors.day_sheet(self.today, self.today)
        self.assertEqual(sheet["totals"]["cash"], Decimal("560.00"))
        self.assertEqual(sheet["totals"]["invoices"], 1)


class SalesScreenTests(SalesReportFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_sales_report_renders_and_exports(self):
        names = ("report_sale", "report_sales_summary", "report_customer_sales", "report_product_sales", "report_rate_history", "report_sale_return", "report_day_sheet")
        for name in names:
            with self.subTest(report=name):
                response = self.client.get(reverse(f"inventory:{name}"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "board-foot")
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    response = self.client.get(reverse(f"inventory:{name}_export"), {"format": fmt})
                    self.assertEqual(response.status_code, 200, f"{name} {fmt}")
