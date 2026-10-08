from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core import features, numbering
from apps.core.constants import VOUCHER_TYPE_JOURNAL, VOUCHER_TYPE_PAYMENT, VOUCHER_TYPE_RECEIPT
from apps.finance.services import _post_voucher, gl_account, next_voucher_number
from apps.finance.models import ChartOfAccount
from apps.inventory.form_layout import FORM_PURCHASE_INVOICE, FORM_PURCHASE_ORDER, get_layout
from apps.inventory.selectors import picker_item_kinds
from apps.inventory.services import _switch_off_line_money


class GeneralSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "pass12345")

    def setUp(self):
        self.client.force_login(self.user)

    def test_every_tab_renders(self):
        for tab in ("features", "numbering", "company", "wheat"):
            with self.subTest(tab=tab):
                self.assertEqual(self.client.get(reverse("portal:general_settings"), {"tab": tab}).status_code, 200)

    def test_feature_switches_hide_fields(self):
        flags = features.current()
        self.assertTrue(flags[features.PURCHASE_TAX])
        self.assertFalse(flags[features.SERVICES])
        self.assertTrue(get_layout(FORM_PURCHASE_ORDER)["shown"]["tax_amount"])
        response = self.client.post(reverse("portal:general_settings"), {"tab": "features", "features": [features.SALES_TAX]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(features.enabled(features.PURCHASE_TAX))
        self.assertTrue(features.enabled(features.SALES_TAX))
        for form in (FORM_PURCHASE_ORDER, FORM_PURCHASE_INVOICE):
            layout = get_layout(form)
            self.assertFalse(layout["shown"]["tax_amount"])
            self.assertFalse(layout["shown"]["discount_amount"])
            self.assertNotIn("tax_amount", [field["code"] for field in layout["optional_fields"]])
        self.assertFalse(get_layout(FORM_PURCHASE_INVOICE)["shown"]["freight_amount"])
        self.assertEqual(features.zero_unless(features.PURCHASE_TAX, Decimal("5")), Decimal("0.00"))
        self.assertEqual(picker_item_kinds(), ("P",))
        lines = _switch_off_line_money([{"tax_perc": Decimal("17"), "discount_amount": Decimal("9")}], tax=False, discount=True)
        self.assertEqual((lines[0]["tax_perc"], lines[0]["discount_amount"]), (Decimal("0"), Decimal("9")))

    def test_services_switch(self):
        self.assertNotContains(self.client.get(reverse("inventory:item_list")), "?kind=S")
        features.save({features.SERVICES})
        self.assertContains(self.client.get(reverse("inventory:item_list")), "?kind=S")
        self.assertEqual(set(picker_item_kinds()), {"P", "S"})

    def test_numbering_start_and_padding(self):
        self.assertEqual(numbering.preview(numbering.SERIES_PURCHASE_INVOICE, None), "PI-000001")
        row = numbering.series(numbering.SERIES_PURCHASE_INVOICE)
        row.start_number = 0
        row.save()
        self.assertEqual(numbering.next_seq(numbering.SERIES_PURCHASE_INVOICE, None), 0)
        self.assertEqual(numbering.preview(numbering.SERIES_PURCHASE_INVOICE, None), "PI-000000")
        self.assertEqual(numbering.next_seq(numbering.SERIES_PURCHASE_INVOICE, 5), 6)
        row.start_number = 100
        row.save()
        self.assertEqual(numbering.next_seq(numbering.SERIES_PURCHASE_INVOICE, 5), 100)

    def test_voucher_entries_number_by_series(self):
        self.assertEqual(next_voucher_number(VOUCHER_TYPE_PAYMENT, "cash"), "CP-1")
        self.assertEqual(next_voucher_number(VOUCHER_TYPE_RECEIPT, "bank"), "BR-1")
        self.assertEqual(next_voucher_number(VOUCHER_TYPE_JOURNAL, ""), "JV-1")
        expense = gl_account(("EXPENSES", "Admin", "Electricity"))
        cash = gl_account(("ASSETS", "Current Assets", "Cash"))
        ChartOfAccount.rebuild_codes()
        expense.refresh_from_db()
        cash.refresh_from_db()
        voucher = _post_voucher(
            source_ref="T-1", voucher_type=VOUCHER_TYPE_JOURNAL, voucher_date="2026-10-06", account_no="",
            entries=[(expense.code, Decimal("10"), Decimal("0"), ""), (cash.code, Decimal("0"), Decimal("10"), "")], remarks="t",
        )
        self.assertEqual(voucher.voucher_no, "JV-1")
        self.assertEqual(next_voucher_number(VOUCHER_TYPE_JOURNAL, ""), "JV-2")

        payload = {"tab": "numbering"}
        for row in numbering.all_series():
            payload.update({f"{row.code}-prefix": row.prefix, f"{row.code}-start_number": row.start_number, f"{row.code}-padding": row.padding})
        payload["journal-start_number"] = 0
        response = self.client.post(reverse("portal:general_settings"), payload)
        self.assertContains(response, "Already used up to 1")
        payload["journal-start_number"] = 50
        payload["purchase_invoice-start_number"] = 0
        self.assertEqual(self.client.post(reverse("portal:general_settings"), payload).status_code, 302)
        self.assertEqual(next_voucher_number(VOUCHER_TYPE_JOURNAL, ""), "JV-50")
        self.assertEqual(numbering.preview(numbering.SERIES_PURCHASE_INVOICE, None), "PI-000000")

    def test_voucher_entry_screens(self):
        for query, title in (({"voucher_type": "PV", "money_mode": "cash"}, "Cash Payment"), ({"voucher_type": "RV", "money_mode": "bank"}, "Bank Receipt"), ({"voucher_type": "JV"}, "Journal Voucher")):
            with self.subTest(title=title):
                self.assertContains(self.client.get(reverse("finance:account_voucher_list"), query), title)
                self.assertContains(self.client.get(reverse("finance:account_voucher_create"), query), title)

    def test_products_board_has_tiles_and_setup_menu(self):
        response = self.client.get(reverse("products:product_list"))
        self.assertContains(response, "All products")
        self.assertContains(response, "Rate Update")
        self.assertNotContains(response, 'label="Sale"')
