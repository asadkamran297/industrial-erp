from decimal import Decimal

from django.urls import reverse

from apps.core.constants import (
    INV_BARDANA_RETURNABLE, PRD_LEDGER_PACKING_OUT, PRD_LEDGER_PURCHASE, PRD_LEVEL_ITEM, PRD_LEVEL_SUB_GROUP, PRD_SPEC_RAW_PACKING, PRD_UNIT_PIECE,
)
from apps.portal.tests import OwnerPackFixture
from apps.production.models import GrindingOutput

from . import report_selectors as sel
from .models import PartyBardanaLedger, ProductLedger, ProductNode


class BardanaFixture(OwnerPackFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        raw = ProductNode.objects.get(name="Raw")
        sacks = ProductNode.objects.create(parent=raw, level=PRD_LEVEL_SUB_GROUP, code_segment="02", name="Sacks")
        cls.sack = ProductNode.objects.create(parent=sacks, level=PRD_LEVEL_ITEM, code_segment="001", name="Jute Sack", specification=PRD_SPEC_RAW_PACKING, unit=PRD_UNIT_PIECE, starting_date=cls.today)
        ProductLedger.objects.create(product=cls.sack, entry_date=cls.today.replace(day=1), source=PRD_LEDGER_PURCHASE, quantity=Decimal("100"), godown=cls.godown)
        ProductLedger.objects.create(product=cls.sack, entry_date=cls.today, source=PRD_LEDGER_PACKING_OUT, quantity=Decimal("-40"), godown=cls.godown)
        PartyBardanaLedger.objects.create(party=cls.supplier, bardana_item=cls.sack, entry_date=cls.today, source=PRD_LEDGER_PURCHASE, quantity=Decimal("80"), ownership=INV_BARDANA_RETURNABLE)
        PartyBardanaLedger.objects.create(party=cls.supplier, bardana_item=cls.sack, entry_date=cls.today, source="purchase_return", quantity=Decimal("-30"), ownership=INV_BARDANA_RETURNABLE)
        output = GrindingOutput.objects.get()
        output.pack_product = cls.sack
        output.pack_qty = Decimal("47")
        output.save()


class BardanaSelectorTests(BardanaFixture):
    def test_stock_balances_movements_packing(self):
        stock = sel.bardana_stock(self.today, self.today)
        row = stock["rows"][0]
        self.assertEqual(row["opening"], Decimal("100.000"))
        self.assertEqual(row["packed"], Decimal("40.000"))
        self.assertEqual(row["closing"], Decimal("60.000"))
        party = sel.party_balances(self.today)["rows"][0]
        self.assertEqual(party["received"], Decimal("80.000"))
        self.assertEqual(party["held"], Decimal("50.000"))
        self.assertEqual(party["returnable"], Decimal("50.000"))
        moves = sel.movement_register(self.today, self.today)
        self.assertEqual(moves["totals"]["entries"], 3)
        self.assertEqual(sel.movement_register(self.today, self.today, book="party")["totals"]["entries"], 2)
        packing = sel.packing_consumption(self.today, self.today)["rows"][0]
        self.assertEqual(packing["bags_used"], Decimal("47.000"))
        self.assertEqual(packing["variance"], Decimal("2.000"))


class BardanaScreenTests(BardanaFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_bardana_report_renders_and_exports(self):
        for name in ("report_bardana_stock", "report_party_bardana", "report_bardana_movements", "report_packing_consumption"):
            with self.subTest(report=name):
                self.assertEqual(self.client.get(reverse(f"products:{name}"), {"preset": "month"}).status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    self.assertEqual(self.client.get(reverse(f"products:{name}_export"), {"format": fmt, "preset": "month"}).status_code, 200, f"{name} {fmt}")
