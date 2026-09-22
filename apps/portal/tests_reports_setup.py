from datetime import timedelta
from decimal import Decimal

from django.urls import reverse

from apps.access_control.models import Permission, Role, RolePermission, UserAssignment
from apps.products.models import ProductRate

from . import report_selectors_setup as sel
from .tests import OwnerPackFixture


class SetupFixture(OwnerPackFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        ProductRate.objects.create(product=cls.atta, rate=Decimal("280.00"), effective_date=cls.today - timedelta(days=30), is_current=False)
        ProductRate.objects.create(product=cls.atta, rate=Decimal("300.00"), effective_date=cls.today, is_current=True)
        cls.role = Role.objects.create(title="Clerk")
        for code in ("a.view", "b.view"):
            RolePermission.objects.create(role=cls.role, permission=Permission.objects.create(title=code, code=code))
        UserAssignment.objects.create(user=cls.user, role=cls.role, is_primary=True)


class SetupSelectorTests(SetupFixture):
    def test_party_directory_reads_ledger_balances(self):
        data = sel.party_directory(self.today)
        customer = next(r for r in data["rows"] if r["customer_id"] == self.customer.pk)
        supplier = next(r for r in data["rows"] if r["supplier_id"] == self.supplier.pk)
        self.assertEqual(customer["balance"], Decimal("3000.00"))
        self.assertEqual(customer["credit_limit"], Decimal("1000.00"))
        self.assertTrue(customer["over_limit"])
        self.assertEqual(supplier["balance"], Decimal("1200.00"))
        self.assertEqual(supplier["account"], self.supplier_account.code)
        self.assertEqual(data["totals"]["receivable"], Decimal("3000.00"))
        self.assertEqual(data["totals"]["payable"], Decimal("1200.00"))
        self.assertEqual([r["kind"] for r in sel.party_directory(self.today, kind="supplier")["rows"]], ["Supplier"])

    def test_product_master_rates(self):
        data = sel.product_master()
        atta = next(r for r in data["rows"] if r["pk"] == self.atta.pk)
        self.assertEqual(atta["category"], "Finished")
        self.assertEqual(atta["sub_group"], "Atta")
        self.assertEqual(atta["unit_kg"], Decimal("20.000"))
        self.assertEqual(atta["rate"], Decimal("300.00"))
        self.assertEqual(atta["rate_date"], self.today)
        self.assertEqual(atta["previous_rate"], Decimal("280.00"))
        wheat = next(r for r in data["rows"] if r["pk"] == self.wheat.pk)
        self.assertIsNone(wheat["rate"])
        self.assertEqual(data["totals"]["unrated"], 1)

    def test_chart_of_accounts_rolls_up(self):
        data = sel.chart_of_accounts()
        cash = next(r for r in data["rows"] if r["pk"] == self.cash.pk)
        self.assertEqual(cash["opening"], Decimal("5000.00"))
        self.assertEqual(cash["movement"], Decimal("-1800.00"))
        self.assertEqual(cash["closing"], Decimal("3200.00"))
        self.assertEqual(cash["level"], 3)
        self.assertTrue(cash["title"].startswith(sel.INDENT * 2))
        assets = next(r for r in data["rows"] if r["level"] == 1 and r["account_type"] == "asset")
        self.assertGreaterEqual(assets["closing"], Decimal("6200.00"))
        postable = sel.chart_of_accounts(postable_only=True)["rows"]
        self.assertFalse(any(r["is_group"] for r in postable))

    def test_user_access(self):
        data = sel.user_access()
        row = next(r for r in data["rows"] if r["pk"] == self.user.pk)
        self.assertEqual(row["role"], "Clerk")
        self.assertEqual(row["permissions"], 2)
        self.assertEqual(row["superuser"], "Yes")
        self.assertEqual(data["totals"]["assignments"], 1)
        self.assertEqual(sel.user_access(role=self.role.pk)["totals"]["users"], 1)


class SetupScreenTests(SetupFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_setup_report_renders_and_exports(self):
        for name in ("report_party_directory", "report_product_master", "report_chart_of_accounts", "report_user_access"):
            with self.subTest(report=name):
                self.assertEqual(self.client.get(reverse(f"portal:{name}")).status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    self.assertEqual(self.client.get(reverse(f"portal:{name}_export"), {"format": fmt}).status_code, 200, f"{name} {fmt}")
