from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse

from apps.core.constants import ACCOUNT_TYPE_ASSET, VOUCHER_TYPE_JOURNAL, VOUCHER_TYPE_PAYMENT, VOUCHER_TYPE_RECEIPT
from apps.finance.models import AccountVoucher, ChartOfAccount, FiscalYear
from apps.finance.services import _post_voucher, gl_account, reverse_gl_posting
from apps.inventory.models import PurchaseInvoice
from apps.portal.tests import OwnerPackFixture
from apps.products.models import PartyBardanaLedger, ProductNode

from . import report_selectors as sel


class AccountsReportFixture(OwnerPackFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        current = cls.cash.parent
        bank_group = ChartOfAccount.objects.create(parent=current, title="Bank", account_type=ACCOUNT_TYPE_ASSET, is_group=True, sort_order=9)
        cls.bank = ChartOfAccount.objects.create(parent=bank_group, title="HBL", account_type=ACCOUNT_TYPE_ASSET, is_group=False)
        cls.expense = gl_account(("EXPENSES", "Admin", "Electricity"))
        ChartOfAccount.rebuild_codes()
        for node in (cls.cash, cls.bank, cls.expense, cls.customer_account, cls.supplier_account):
            node.refresh_from_db()
        start = date(cls.today.year if cls.today.month >= 7 else cls.today.year - 1, 7, 1)
        cls.fiscal = FiscalYear.objects.create(title="FY", code="FY1", start_date=start, end_date=date(start.year + 1, 6, 30))

        _post_voucher(
            source_ref="TEST-RV", voucher_type=VOUCHER_TYPE_RECEIPT, voucher_date=cls.today, account_no=cls.cash.code,
            entries=[(cls.cash.code, Decimal("1000.00"), Decimal("0"), ""), (cls.customer_account.code, Decimal("0"), Decimal("1000.00"), "")],
            remarks="customer paid", user=cls.user,
        )
        pv = _post_voucher(
            source_ref="TEST-PV", voucher_type=VOUCHER_TYPE_PAYMENT, voucher_date=cls.today, account_no=cls.bank.code,
            entries=[(cls.supplier_account.code, Decimal("500.00"), Decimal("0"), ""), (cls.bank.code, Decimal("0"), Decimal("500.00"), "")],
            remarks="arhti paid", user=cls.user,
        )
        AccountVoucher.objects.filter(pk=pv.pk).update(cheque_no="CHQ-1", cheque_date=cls.today)
        _post_voucher(
            source_ref="TEST-EXP", voucher_type=VOUCHER_TYPE_JOURNAL, voucher_date=cls.today, account_no="",
            entries=[(cls.expense.code, Decimal("700.00"), Decimal("0"), ""), (cls.cash.code, Decimal("0"), Decimal("700.00"), "")],
            remarks="bill", user=cls.user,
        )
        _post_voucher(
            source_ref="TEST-X", voucher_type=VOUCHER_TYPE_JOURNAL, voucher_date=cls.today, account_no="",
            entries=[(cls.expense.code, Decimal("100.00"), Decimal("0"), ""), (cls.cash.code, Decimal("0"), Decimal("100.00"), "")],
            remarks="wrong", user=cls.user,
        )
        reverse_gl_posting(source_ref="TEST-X", reversal_ref="test_reversal:1", voucher_date=cls.today, remarks="undo", user=cls.user)
        PurchaseInvoice.objects.filter(status="reversed").update(reversed_on=cls.today, reverse_reason="duplicate")
        bardana = ProductNode.objects.create(parent=cls.wheat.parent, level=3, code_segment="002", name="Bori", specification="raw_packing", unit="piece", starting_date=cls.today)
        PartyBardanaLedger.objects.create(party=cls.supplier, bardana_item=bardana, entry_date=cls.today, source="purchase", reference="PI-1", quantity=Decimal("50"))


class AccountsSelectorTests(AccountsReportFixture):
    def test_cash_and_bank_books(self):
        cash = sel.cash_book(self.today, self.today)
        self.assertEqual(cash["totals"]["opening"], Decimal("5000.00"))
        self.assertEqual(cash["rows"][0]["receipts"], Decimal("2300.00"))
        self.assertEqual(cash["rows"][0]["payments"], Decimal("3800.00"))
        self.assertEqual(cash["totals"]["closing"], Decimal("3500.00"))
        bank = sel.bank_book(self.today, self.today)
        self.assertEqual(bank["rows"][0]["cheque_no"], "CHQ-1")
        self.assertEqual(bank["rows"][0]["counterpart"], "Arhti One")
        self.assertEqual(bank["totals"]["withdrawal"], Decimal("500.00"))
        self.assertEqual(bank["totals"]["closing"], Decimal("-500.00"))

    def test_party_ledger_and_summary(self):
        supplier = sel.party_ledger(self.today, self.today, self.supplier_account.code)
        self.assertEqual(supplier["party_type"], "supplier")
        self.assertEqual(supplier["totals"]["closing"], Decimal("700.00"))
        self.assertEqual(supplier["totals"]["sacks"], Decimal("50"))
        self.assertEqual(supplier["rows"][-1]["kind"], "Sacks")
        customer = sel.party_ledger(self.today, self.today, self.customer_account.code)
        self.assertEqual(customer["totals"]["closing"], Decimal("2000.00"))
        self.assertEqual(customer["rows"][-1]["balance"], Decimal("2000.00"))
        self.assertEqual(sel.party_ledger(self.today, self.today, "")["rows"], [])
        summary = sel.receivable_payable(self.today)
        self.assertEqual(summary["totals"]["receivable"], Decimal("2000.00"))
        self.assertEqual(summary["totals"]["payable"], Decimal("700.00"))
        self.assertEqual(summary["totals"]["net"], Decimal("1300.00"))
        self.assertEqual(sel.receivable_payable(self.today, "supplier")["totals"]["suppliers"], 1)

    def test_voucher_register_and_expense_grid(self):
        register = sel.voucher_register(self.today, self.today)
        self.assertEqual(register["totals"]["vouchers"], 7)
        self.assertEqual(register["totals"]["by_type"]["RV"]["count"], 1)
        self.assertEqual(sel.voucher_register(self.today, self.today, account=self.bank.code)["totals"]["vouchers"], 1)
        self.assertEqual(sel.voucher_register(self.today, self.today, voucher_type="JV")["totals"]["vouchers"], 5)
        grid = sel.expense_analysis(self.fiscal.start_date, self.fiscal.end_date)
        key = f"m_{self.today:%Y_%m}"
        self.assertEqual(grid["rows"][0][key], Decimal("700.00"))
        self.assertEqual(grid["rows"][0]["total"], Decimal("700.00"))
        self.assertEqual(grid["rows"][0]["share"], Decimal("100.00"))
        self.assertEqual(len(grid["months"]), 12)

    def test_opening_balances_and_audit_trail(self):
        manual = sel.opening_balances(self.fiscal.start_date)
        cash = next(r for r in manual["rows"] if r["code"] == self.cash.code)
        self.assertEqual((cash["source"], cash["debit"]), ("Manual", Decimal("5000.00")))
        carried = sel.opening_balances(self.today + timedelta(days=1))
        by_code = {r["code"]: r for r in carried["rows"]}
        self.assertEqual((by_code[self.cash.code]["source"], by_code[self.cash.code]["debit"]), ("Carried", Decimal("3500.00")))
        self.assertEqual(by_code[self.bank.code]["credit"], Decimal("500.00"))
        self.assertEqual(by_code[self.supplier_account.code]["credit"], Decimal("700.00"))
        self.assertEqual(carried["totals"]["debit"], Decimal("6200.00"))
        audit = sel.audit_trail(self.today, self.today)
        self.assertEqual(audit["totals"][sel.KIND_GL_REVERSAL], 1)
        self.assertEqual(audit["totals"][sel.KIND_INVOICE_REVERSAL], 1)
        self.assertEqual(audit["totals"]["reversed_amount"], Decimal("1099.00"))
        self.assertEqual(sel.audit_trail(self.today, self.today, kind=sel.KIND_INVOICE_REVERSAL)["rows"][0]["reason"], "duplicate")


class AccountsScreenTests(AccountsReportFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_accounts_report_renders_and_exports(self):
        params = {"preset": "month", "party": self.supplier_account.code}
        for name in ("report_cash_book", "report_bank_book", "report_party_ledger", "report_voucher_register", "report_expense_analysis",
                     "report_receivable_payable", "report_opening_balances", "report_audit_trail"):
            with self.subTest(report=name):
                response = self.client.get(reverse(f"finance:{name}"), params)
                self.assertEqual(response.status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    self.assertEqual(self.client.get(reverse(f"finance:{name}_export"), {"format": fmt, **params}).status_code, 200, f"{name} {fmt}")

    def test_expense_columns_follow_the_period(self):
        response = self.client.get(reverse("finance:report_expense_analysis"), {"preset": "month"})
        self.assertContains(response, f"{self.today:%b %y}")
        self.assertEqual(self.client.post(reverse("finance:report_expense_analysis_columns"), {"columns": ["group"]}).status_code, 302)
