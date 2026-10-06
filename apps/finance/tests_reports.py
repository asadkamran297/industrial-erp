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

    def test_open_documents_match_aging(self):
        from apps.portal.selectors import open_documents, payables_aging, receivables_aging

        receivable = open_documents("receivable", self.today)
        self.assertEqual(receivable["totals"]["open"], receivables_aging(self.today)["totals"]["balance"])
        self.assertEqual(receivable["totals"]["open"], Decimal("2000.00"))
        self.assertEqual(receivable["rows"][0]["amount"], Decimal("3000.00"))
        payable = open_documents("payable", self.today)
        self.assertEqual(payable["totals"]["open"], payables_aging(self.today)["totals"]["balance"])

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


from django.test import TestCase  # noqa: E402

from apps.core.constants import (  # noqa: E402
    GL_CASH_PATH,
    GL_COGS_PATH,
    GL_OPENING_EQUITY_PATH,
    GL_RETAINED_EARNINGS_PATH,
    GL_SALES_RETURN_PATH,
    GL_SALES_REVENUE_PATH,
    NO,
    STATUS_CREATED,
)
from apps.finance.services import close_period_to_retained_earnings  # noqa: E402

from . import statements as fs  # noqa: E402


class StatementFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cash = gl_account(GL_CASH_PATH)
        cls.sales = gl_account(GL_SALES_REVENUE_PATH)
        cls.returns = gl_account(GL_SALES_RETURN_PATH)
        cls.cogs = gl_account(GL_COGS_PATH)
        cls.power = gl_account(("EXPENSES", "Indirect Expenses", "Electricity"))
        cls.scrap = gl_account(("REVENUE", "Indirect Revenue", "Scrap Sales"))
        cls.payable = gl_account(("LIABILITIES", "Current Liabilities", "Trade Payables"))
        cls.equity = gl_account(GL_OPENING_EQUITY_PATH)
        cls.retained = gl_account(GL_RETAINED_EARNINGS_PATH)
        ChartOfAccount.rebuild_codes()
        ChartOfAccount.objects.filter(pk=cls.cash.pk).update(opening_balance=Decimal("10000.00"))
        ChartOfAccount.objects.filter(pk=cls.equity.pk).update(opening_balance=Decimal("10000.00"))
        for node in (cls.cash, cls.sales, cls.returns, cls.cogs, cls.power, cls.scrap, cls.payable, cls.equity, cls.retained):
            node.refresh_from_db()
        FiscalYear.objects.create(title="FY1", code="FY1", start_date=date(2025, 7, 1), end_date=date(2026, 6, 30))
        FiscalYear.objects.create(title="FY2", code="FY2", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30))

        def jv(ref, day, debit, credit, amount):
            return _post_voucher(
                source_ref=ref, voucher_type=VOUCHER_TYPE_JOURNAL, voucher_date=day, account_no="",
                entries=[(debit.code, Decimal(amount), Decimal("0"), ""), (credit.code, Decimal("0"), Decimal(amount), "")],
                remarks=ref,
            )

        jv("S1", date(2025, 8, 10), cls.cash, cls.sales, "5000.00")
        jv("C1", date(2025, 8, 10), cls.cogs, cls.payable, "3000.00")
        jv("R1", date(2025, 9, 5), cls.returns, cls.cash, "500.00")
        jv("E1", date(2025, 10, 1), cls.power, cls.cash, "400.00")
        jv("O1", date(2025, 11, 1), cls.cash, cls.scrap, "200.00")
        jv("S2", date(2026, 7, 15), cls.cash, cls.sales, "1000.00")
        draft = jv("D1", date(2026, 8, 1), cls.cash, cls.sales, "999.00")
        AccountVoucher.objects.filter(pk=draft.pk).update(posted=NO, status=STATUS_CREATED)

    FY1 = fs.Column("fy1", "FY1", date(2025, 7, 1), date(2026, 6, 30))
    FY2 = fs.Column("fy2", "FY2", date(2026, 7, 1), date(2027, 6, 30))

    def months(self, start, count):
        columns, day = [], start
        for index in range(count):
            following = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
            columns.append(fs.Column(f"m{index}", f"{day:%b %Y}", day, following - timedelta(days=1)))
            day = following
        return columns

    def as_of(self, *days):
        return [fs.Column(f"d{index}", f"{day}", None, day) for index, day in enumerate(days)]

    def row(self, data, row_id):
        return next(row for row in data["rows"] if row["id"] == row_id)



class StatementEngineTests(StatementFixture):
    def test_profit_and_loss_sections(self):
        pl = fs.profit_and_loss([self.FY1])
        totals = {key: values["fy1"] for key, values in pl["totals"].items()}
        self.assertEqual(totals["income"], Decimal("4500.00"))
        self.assertEqual(totals["cogs"], Decimal("3000.00"))
        self.assertEqual(totals["gross_profit"], Decimal("1500.00"))
        self.assertEqual(totals["expenses"], Decimal("400.00"))
        self.assertEqual(totals["net_operating_income"], Decimal("1100.00"))
        self.assertEqual(totals["other_income"], Decimal("200.00"))
        self.assertEqual(totals["net_income"], Decimal("1300.00"))

    def test_contra_revenue_is_negative(self):
        pl = fs.profit_and_loss([self.FY1])
        self.assertEqual(self.row(pl, self.returns.code)["values"]["fy1"], Decimal("-500.00"))

    def test_unposted_lines_never_move_figures(self):
        self.assertEqual(fs.profit_and_loss([self.FY2])["totals"]["income"]["fy2"], Decimal("1000.00"))
        sheet = fs.balance_sheet(self.as_of(date(2026, 8, 31)))
        self.assertEqual(self.row(sheet, self.cash.code)["values"]["d0"], Decimal("15300.00"))
        self.assertEqual(fs.balances_as_of({"x": date(2026, 8, 31)})[self.cash.code]["x"], Decimal("15300.00"))

    def test_balance_sheet_ties_at_every_date(self):
        days = (date(2025, 1, 1), date(2025, 12, 31), date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31))
        sheet = fs.balance_sheet(self.as_of(*days))
        for key in sheet["totals"]["difference"]:
            self.assertEqual(sheet["totals"]["difference"][key], Decimal("0.00"), key)
            self.assertEqual(sheet["totals"]["assets"][key], sheet["totals"]["liabilities_and_equity"][key])
        self.assertFalse(any(row["kind"] == "error" for row in sheet["rows"]))
        self.assertEqual(sheet["totals"]["net_income"]["d3"], Decimal("1000.00"))
        self.assertEqual(sheet["totals"]["retained_earnings"]["d3"], Decimal("1300.00"))

    def test_net_income_matches_profit_and_loss(self):
        day = date(2025, 12, 31)
        sheet = fs.balance_sheet(self.as_of(day))
        pl = fs.profit_and_loss([fs.Column("t", "", fs.fiscal_year_start(day), day)])
        self.assertEqual(sheet["totals"]["net_income"]["d0"], pl["totals"]["net_income"]["t"])

    def test_period_close_changes_nothing(self):
        days = (date(2026, 6, 30), date(2026, 7, 31))
        before_pl = fs.profit_and_loss([self.FY1])["totals"]
        before_bs = fs.balance_sheet(self.as_of(*days))["totals"]
        close_period_to_retained_earnings(closing_date=date(2026, 6, 30))
        self.assertEqual(fs.profit_and_loss([self.FY1])["totals"], before_pl)
        after_bs = fs.balance_sheet(self.as_of(*days))["totals"]
        for key in ("assets", "liabilities_and_equity", "net_income", "retained_earnings", "difference"):
            self.assertEqual(after_bs[key], before_bs[key], key)

    def test_month_columns_sum_to_total(self):
        months = self.months(date(2025, 7, 1), 12)
        by_month = fs.profit_and_loss(months)
        total = fs.profit_and_loss([self.FY1])
        for key, values in total["totals"].items():
            self.assertEqual(sum(by_month["totals"][key].values(), Decimal("0.00")), values["fy1"], key)

    def test_query_count_is_constant(self):
        for count in (1, 12):
            columns = self.months(date(2025, 7, 1), count)
            with self.assertNumQueries(2):
                fs.profit_and_loss(columns)
            with self.assertNumQueries(3):
                fs.balance_sheet(self.as_of(*[column.end for column in columns]))

    def test_rows_filter(self):
        quiet = gl_account(("EXPENSES", "Indirect Expenses", "Rent"))
        ChartOfAccount.rebuild_codes()
        quiet.refresh_from_db()
        ids = {row["id"] for row in fs.profit_and_loss([self.FY1])["rows"]}
        self.assertNotIn(quiet.code, ids)
        ids = {row["id"] for row in fs.profit_and_loss([self.FY1], show=fs.SHOW_ALL)["rows"]}
        self.assertIn(quiet.code, ids)


class StatementEngineMoreTests(StatementFixture):
    def test_trial_balance_balances_for_any_dates(self):
        for start, end in ((None, date(2025, 12, 31)), (date(2025, 7, 1), date(2026, 6, 30)), (date(2026, 7, 1), date(2026, 8, 31)), (date(2030, 1, 1), date(2030, 1, 31))):
            for tree in (False, True):
                with self.subTest(start=start, end=end, tree=tree):
                    data = fs.trial_balance(start, end, tree=tree)
                    self.assertTrue(data["balanced"], data["totals"])
        flat = fs.trial_balance(date(2025, 7, 1), date(2026, 6, 30))
        cash = next(row for row in flat["rows"] if row["code"] == self.cash.code)
        self.assertEqual(cash["values"]["o_dr"], Decimal("10000.00"))
        self.assertEqual(cash["values"]["c_dr"], Decimal("14300.00"))

    def test_cash_flow_ties_to_balance_sheet(self):
        for column in (self.FY1, self.FY2, fs.Column("all", "", None, date(2026, 8, 31))):
            with self.subTest(column=column.key):
                flow = fs.cash_flow([column])
                sheet = fs.balance_sheet([fs.Column("x", "", None, column.end)])
                cash = next(row for row in sheet["rows"] if row["code"] == self.cash.code)["values"]["x"]
                self.assertEqual(flow["totals"]["end"][column.key], cash)
                self.assertEqual(flow["totals"]["difference"][column.key], Decimal("0.00"))
        flow = fs.cash_flow([self.FY1])
        self.assertEqual(flow["totals"]["net_income"]["fy1"], Decimal("1300.00"))
        self.assertEqual(flow["totals"]["operating"]["fy1"], Decimal("4300.00"))

    def test_cash_flow_months_sum_to_total(self):
        months = self.months(date(2025, 7, 1), 12)
        by_month = fs.cash_flow(months)
        total = fs.cash_flow([self.FY1])
        for key in ("operating", "investing", "financing", "net_change", "net_income"):
            self.assertEqual(sum(by_month["totals"][key].values(), Decimal("0.00")), total["totals"][key]["fy1"], key)
        self.assertEqual(by_month["totals"]["end"]["m11"], total["totals"]["end"]["fy1"])

    def test_cash_flow_ignores_period_close(self):
        before = fs.cash_flow([self.FY1])["totals"]
        close_period_to_retained_earnings(closing_date=date(2026, 6, 30))
        self.assertEqual(fs.cash_flow([self.FY1])["totals"], before)

    def test_ledger_matches_statements(self):
        accounts = {row["code"]: row for row in fs.ledger(start=date(2025, 7, 1), end=date(2026, 6, 30))}
        self.assertEqual(accounts[self.cash.code]["opening"], Decimal("10000.00"))
        self.assertEqual(accounts[self.cash.code]["closing"], Decimal("14300.00"))
        self.assertEqual(accounts[self.cash.code]["rows"][0]["split"], self.sales.title)
        self.assertNotIn(self.retained.code, accounts)
        detail = {row["code"]: row for row in fs.ledger(codes=fs.load_chart().codes_of(*fs.PL_TYPES), start=date(2025, 7, 1), end=date(2026, 6, 30), with_opening=False, exclude_close=True)}
        self.assertEqual(detail[self.returns.code]["movement"], Decimal("-500.00"))
        self.assertEqual(detail[self.sales.code]["movement"], Decimal("5000.00"))
        drafts = fs.ledger(codes=[self.cash.code], start=date(2026, 8, 1), end=date(2026, 8, 31))
        self.assertEqual(drafts[0]["rows"], [])

    def test_changes_in_equity_ties(self):
        for column in (self.FY1, self.FY2, fs.Column("all", "", None, date(2026, 8, 31))):
            with self.subTest(column=column.key):
                data = fs.changes_in_equity([column])
                sheet = fs.balance_sheet([fs.Column("x", "", None, column.end)])
                self.assertEqual(data["totals"]["end"][column.key], sheet["totals"]["equity"]["x"])
                self.assertEqual(data["totals"]["difference"][column.key], Decimal("0.00"))
        self.assertEqual(fs.changes_in_equity([self.FY1])["totals"]["begin"]["fy1"], Decimal("10000.00"))
        close_period_to_retained_earnings(closing_date=date(2026, 6, 30))
        self.assertEqual(fs.changes_in_equity([self.FY2])["totals"]["difference"]["fy2"], Decimal("0.00"))

    def test_journal_balances_per_voucher(self):
        vouchers = fs.journal(date(2025, 7, 1), date(2026, 8, 31))
        self.assertEqual(len(vouchers), 6)
        self.assertTrue(all(entry["balanced"] for entry in vouchers))


class StatementScreenTests(StatementFixture):
    def setUp(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser("acct", "acct@example.com", "pass12345")
        self.client.force_login(user)

    def test_profit_and_loss_variants_render(self):
        base = {"preset": "custom", "date_from": "2025-07-01", "date_to": "2026-06-30"}
        for extra in ({}, {"by": "month"}, {"by": "quarter", "compare": "py", "chg": "1", "pct": "1"}, {"compare": "pp", "poi": "1", "neg": "minus", "k": "1", "np": "1", "show": "all"}):
            with self.subTest(extra=extra):
                response = self.client.get(reverse("finance:income_statement"), {**base, **extra})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Gross Profit")
                xlsx = self.client.get(reverse("finance:income_statement"), {**base, **extra, "format": "xlsx"})
                self.assertEqual(xlsx.status_code, 200)
        response = self.client.get(reverse("finance:income_statement"), base)
        self.assertContains(response, "1,300.00")
        self.assertContains(response, "(500.00)")
        self.assertContains(response, f"account_no={self.sales.code}")

    def test_balance_sheet_variants_render(self):
        for extra in ({}, {"by": "month"}, {"compare": "py", "chg": "1", "pct": "1"}, {"compare": "pp"}):
            with self.subTest(extra=extra):
                params = {"as_of": "2026-07-31", **extra}
                response = self.client.get(reverse("finance:balance_sheet"), params)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Out of balance")
                self.assertEqual(self.client.get(reverse("finance:balance_sheet"), {**params, "format": "xlsx"}).status_code, 200)
        response = self.client.get(reverse("finance:balance_sheet"), {"as_of": "2026-07-31"})
        self.assertContains(response, "15,300.00")
        self.assertContains(response, "Retained Earnings")

    def test_trial_balance_and_cash_flow_render(self):
        for name, params in (
            ("finance:trial_balance", {}), ("finance:trial_balance", {"view": "tree", "preset": "all"}),
            ("finance:cash_flow", {"preset": "custom", "date_from": "2025-07-01", "date_to": "2026-06-30"}),
            ("finance:cash_flow", {"preset": "custom", "date_from": "2025-07-01", "date_to": "2026-06-30", "by": "month", "compare": "py", "chg": "1"}),
            ("finance:cash_flow", {"preset": "custom", "date_from": "2025-07-01", "date_to": "2026-06-30", "method": "direct"}),
        ):
            with self.subTest(name=name, params=params):
                response = self.client.get(reverse(name), params)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Difference to cash")
                self.assertEqual(self.client.get(reverse(name), {**params, "format": "xlsx"}).status_code, 200)

    def test_ledger_screens_render(self):
        params = {"preset": "custom", "date_from": "2025-07-01", "date_to": "2026-06-30"}
        for name in ("finance:report_general_ledger", "finance:report_pl_detail", "finance:report_bs_detail", "finance:report_changes_in_equity", "finance:report_journal", "finance:report_open_invoices", "finance:report_unpaid_bills"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name), params)
                self.assertEqual(response.status_code, 200)
                export = {} if name in ("finance:report_journal", "finance:report_open_invoices", "finance:report_unpaid_bills") else {"format": "xlsx"}
                target = reverse(name) if export else reverse(f"{name}_export")
                self.assertEqual(self.client.get(target, {**params, **(export or {"format": "xlsx"})}).status_code, 200)
        response = self.client.get(reverse("finance:report_general_ledger"), {**params, "account_no": self.cash.code})
        self.assertContains(response, "14,300.00")
        response = self.client.get(reverse("finance:account_ledger"), {"account_no": self.cash.code, "posted": "1", "date_from": "2026-08-01", "date_to": "2026-08-31"})
        self.assertNotContains(response, "999.00")
        response = self.client.get(reverse("finance:report_voucher_register"), {"preset": "custom", "date_from": "2025-07-01", "date_to": "2026-08-31", "posted": "N"})
        self.assertEqual(response.status_code, 200)

    def test_saved_reports(self):
        from apps.finance.models import SavedReport

        url = reverse("finance:income_statement")
        response = self.client.post(reverse("finance:saved_report_create"), {"report_key": "finance:income_statement", "name": "Monthly", "querystring": "by=month", "shared": "1"})
        self.assertRedirects(response, f"{url}?by=month", fetch_redirect_response=False)
        saved = SavedReport.objects.get()
        self.assertEqual((saved.name, saved.shared), ("Monthly", "Y"))
        self.assertContains(self.client.get(url), "Monthly")
        self.assertEqual(self.client.post(reverse("finance:saved_report_create"), {"report_key": "admin:index", "name": "x"}).status_code, 302)
        self.assertEqual(SavedReport.objects.count(), 1)
        self.client.post(reverse("finance:saved_report_delete", args=[saved.pk]))
        self.assertEqual(SavedReport.objects.count(), 0)
