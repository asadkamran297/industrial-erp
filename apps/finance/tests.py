from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.configurations.models import Bank, PaymentMethod
from apps.core.constants import (
    ACCOUNT_LEDGER_GENERAL,
    ACCOUNT_LEDGER_SUBSIDIARY,
    ACCOUNT_NATURE_DEBIT,
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_REVENUE,
    BALANCE_INCOME_BALANCE_SHEET,
    BALANCE_INCOME_INCOME_STATEMENT,
    STATUS_SUBMITTED,
    VOUCHER_TYPE_PAYMENT,
    VOUCHER_TYPE_RECEIPT,
    YES,
)

from .models import AccountConfiguration, AccountVoucher, AccountVoucherLine, FiscalYear


class FinanceModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="financeuser", password="pass12345", is_superuser=True)
        self.cash_method = PaymentMethod.objects.create(title="Cash")
        self.card_method = PaymentMethod.objects.create(title="Card")
        self.bank = Bank.objects.create(title="MCB")

    def create_account(self, **overrides):
        data = {
            "title": "Cash in Hand",
            "code": "A001",
            "nature": ACCOUNT_TYPE_ASSET,
            "account_no": "1001",
            "account_type": ACCOUNT_TYPE_ASSET,
            "account_ledger": ACCOUNT_LEDGER_GENERAL,
            "balance_income": BALANCE_INCOME_BALANCE_SHEET,
            "account_nature": ACCOUNT_NATURE_DEBIT,
        }
        data.update(overrides)
        return AccountConfiguration.objects.create(**data)

    def test_fiscal_year_generates_opening_monthly_and_closing_periods(self):
        fiscal_year = FiscalYear.objects.create(
            title="FY 2026",
            code="FY26",
            start_date=date(2026, 7, 1),
            end_date=date(2027, 6, 30),
        )

        fiscal_year.generate_periods()

        self.assertEqual(fiscal_year.periods.count(), 14)
        self.assertTrue(fiscal_year.periods.filter(code="FY26-00", title="Opening").exists())
        self.assertTrue(fiscal_year.periods.filter(code="FY26-01", title="July 2026").exists())
        self.assertTrue(fiscal_year.periods.filter(code="FY26-99", title="Closing").exists())

    def test_first_account_must_be_general(self):
        account = AccountConfiguration(
            title="Sub Account",
            code="A100",
            nature=ACCOUNT_TYPE_ASSET,
            account_no="1001",
            account_type=ACCOUNT_TYPE_ASSET,
            account_ledger=ACCOUNT_LEDGER_SUBSIDIARY,
            balance_income=BALANCE_INCOME_BALANCE_SHEET,
            account_nature=ACCOUNT_NATURE_DEBIT,
        )

        with self.assertRaises(ValidationError):
            account.full_clean()

    def test_subsidiary_account_requires_same_length_and_general_parent(self):
        general = self.create_account()
        subsidiary = AccountConfiguration(
            title="Petty Cash",
            code="A002",
            nature=ACCOUNT_TYPE_ASSET,
            account_no="10022",
            account_type=ACCOUNT_TYPE_ASSET,
            account_ledger=ACCOUNT_LEDGER_SUBSIDIARY,
            balance_income=BALANCE_INCOME_BALANCE_SHEET,
            account_nature=ACCOUNT_NATURE_DEBIT,
            post_to_account=general,
        )

        with self.assertRaises(ValidationError):
            subsidiary.full_clean()

    def test_voucher_totals_follow_lines_and_submission_requires_balance(self):
        self.create_account()
        expense = self.create_account(
            title="Office Expense",
            code="E001",
            account_no="2001",
            nature=ACCOUNT_TYPE_EXPENSE,
            account_type=ACCOUNT_TYPE_EXPENSE,
            balance_income=BALANCE_INCOME_INCOME_STATEMENT,
        )
        voucher = AccountVoucher.objects.create(
            account_no=expense.account_no,
            voucher_type=VOUCHER_TYPE_PAYMENT,
            payment_method=self.cash_method,
        )

        AccountVoucherLine.objects.create(
            voucher=voucher,
            line_number=1,
            voucher_no=voucher.voucher_no,
            voucher_date=voucher.voucher_date,
            account_no=expense.account_no,
            payment_method=self.cash_method,
            debit_amount=Decimal("100.00"),
        )

        voucher.refresh_from_db()
        self.assertEqual(voucher.debit_amount, Decimal("100.00"))
        self.assertEqual(voucher.credit_amount, Decimal("0.00"))

        voucher.status = STATUS_SUBMITTED
        with self.assertRaises(ValidationError):
            voucher.full_clean()

        cash = AccountConfiguration.objects.get(account_no="1001")
        AccountVoucherLine.objects.create(
            voucher=voucher,
            line_number=2,
            voucher_no=voucher.voucher_no,
            voucher_date=voucher.voucher_date,
            account_no=cash.account_no,
            payment_method=self.cash_method,
            credit_amount=Decimal("100.00"),
        )

        voucher.refresh_from_db()
        voucher.status = STATUS_SUBMITTED
        voucher.full_clean()

    def test_credit_card_line_requires_receipt_voucher_and_card_method(self):
        receipt_account = self.create_account(
            title="Sales",
            code="R001",
            account_no="3001",
            nature=ACCOUNT_TYPE_REVENUE,
            account_type=ACCOUNT_TYPE_REVENUE,
            balance_income=BALANCE_INCOME_INCOME_STATEMENT,
        )
        voucher = AccountVoucher.objects.create(
            account_no=receipt_account.account_no,
            voucher_type=VOUCHER_TYPE_RECEIPT,
            payment_method=self.card_method,
        )

        line = AccountVoucherLine(
            voucher=voucher,
            line_number=1,
            voucher_no=voucher.voucher_no,
            voucher_date=voucher.voucher_date,
            account_no=receipt_account.account_no,
            payment_method=self.card_method,
            credit_amount=Decimal("500.00"),
            credit_card_payment=YES,
            receipt_no="RC-1",
            bank=self.bank,
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_account_voucher_line_create_accepts_inline_rows(self):
        self.client.force_login(self.user)
        expense_account = self.create_account(
            title="Office Expense",
            code="E002",
            account_no="2002",
            nature=ACCOUNT_TYPE_EXPENSE,
            account_type=ACCOUNT_TYPE_EXPENSE,
            balance_income=BALANCE_INCOME_INCOME_STATEMENT,
        )
        cash_account = self.create_account(
            title="Cash in Hand",
            code="A002",
            account_no="1002",
            nature=ACCOUNT_TYPE_ASSET,
            account_type=ACCOUNT_TYPE_ASSET,
            balance_income=BALANCE_INCOME_BALANCE_SHEET,
        )
        voucher = AccountVoucher.objects.create(
            account_no=expense_account.account_no,
            voucher_type=VOUCHER_TYPE_PAYMENT,
            payment_method=self.cash_method,
        )

        response = self.client.post(
            reverse("finance:account_voucher_line_create", args=[voucher.pk]),
            {
                "line_account[]": [expense_account.account_no, cash_account.account_no],
                "line_description[]": ["Expense entry", "Cash entry"],
                "line_debit[]": ["100.00", "0.00"],
                "line_credit[]": ["0.00", "100.00"],
            },
        )

        self.assertRedirects(response, reverse("finance:account_voucher_detail", args=[voucher.pk]))
        voucher.refresh_from_db()
        self.assertEqual(voucher.lines.count(), 2)
        self.assertEqual(voucher.debit_amount, Decimal("100.00"))
        self.assertEqual(voucher.credit_amount, Decimal("100.00"))
