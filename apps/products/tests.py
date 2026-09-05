from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.constants import (
    PRD_LEDGER_OPENING,
    PRD_LEDGER_PURCHASE,
    PRD_LEVEL_GROUP,
    PRD_LEVEL_ITEM,
    PRD_LEVEL_SUB_GROUP,
    PRD_SPEC_FINISH_ITEM,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_SERVICE_ITEM,
    PRD_UNIT_KG,
    PRD_UNIT_PIECE,
    STATUS_ACTIVE,
    STATUS_CLOSED,
    STATUS_INACTIVE,
)

from . import selectors, services
from .models import ProductLedger, ProductNode


class ProductTreeTests(TestCase):
    def setUp(self):
        self.group = ProductNode.objects.create(level=PRD_LEVEL_GROUP, code_segment="01", name="Raw")
        self.sub = ProductNode.objects.create(
            parent=self.group, level=PRD_LEVEL_SUB_GROUP, code_segment="01", name="Wheat Private"
        )

    def _item(self, segment="001", **overrides):
        fields = {
            "parent": self.sub,
            "level": PRD_LEVEL_ITEM,
            "code_segment": segment,
            "name": "Wheat Pvt - P",
            "specification": PRD_SPEC_RAW_ITEM,
            "unit": PRD_UNIT_KG,
            "starting_date": timezone.localdate(),
        }
        fields.update(overrides)
        return ProductNode.objects.create(**fields)

    def test_code_is_assembled_from_the_tree(self):
        item = self._item()
        self.assertEqual(item.complete_code, "01-01-001")
        self.assertEqual(item.display_code, "01-01-001")

    def test_heading_code_is_padded_and_not_postable(self):
        # Each missing level is padded to its own width: GG-SS-III.
        self.assertEqual(self.group.display_code, "01-00-000")
        self.assertEqual(self.sub.display_code, "01-01-000")
        self.assertFalse(self.group.is_postable)
        self.assertFalse(self.sub.is_postable)
        self.assertTrue(self._item().is_postable)

    def test_renumbering_a_heading_moves_the_codes_beneath_it(self):
        item = self._item()
        self.sub.code_segment = "02"
        self.sub.save()
        item.refresh_from_db()
        self.assertEqual(item.complete_code, "01-02-001")

    def test_next_segment_skips_codes_already_spent(self):
        self._item("001")
        self._item("002", name="Wheat Pvt - J")
        self.assertEqual(selectors.next_code_segment(self.sub, PRD_LEVEL_ITEM), "003")

    def test_item_must_sit_under_a_sub_group(self):
        stray = ProductNode(parent=self.group, level=PRD_LEVEL_ITEM, code_segment="001", name="Loose")
        with self.assertRaises(ValidationError):
            stray.clean()


class SpecificationRuleTests(TestCase):
    def setUp(self):
        group = ProductNode.objects.create(level=PRD_LEVEL_GROUP, code_segment="02", name="Finish")
        self.sub = ProductNode.objects.create(
            parent=group, level=PRD_LEVEL_SUB_GROUP, code_segment="01", name="Atta"
        )

    def _item(self, specification, unit=PRD_UNIT_PIECE, unit_weight=15, segment="001"):
        return ProductNode.objects.create(
            parent=self.sub,
            level=PRD_LEVEL_ITEM,
            code_segment=segment,
            name="Atta Jugnoo 15 kg",
            specification=specification,
            unit=unit,
            unit_weight=unit_weight,
        )

    def test_a_finish_item_is_produced_and_never_bought(self):
        item = self._item(PRD_SPEC_FINISH_ITEM)
        self.assertFalse(item.can_buy)
        self.assertTrue(item.can_produce)
        self.assertTrue(item.can_sell)
        with self.assertRaises(ValueError):
            services.link_purchase_account(item, object())

    def test_a_service_item_never_reaches_the_ledger(self):
        item = self._item(PRD_SPEC_SERVICE_ITEM, unit=PRD_UNIT_KG, unit_weight=0, segment="002")
        self.assertFalse(item.keeps_stock)
        with self.assertRaises(ValueError):
            services.post_movement(item, 5, PRD_LEDGER_PURCHASE)

    def test_unit_weight_is_fixed_by_the_unit_where_the_unit_fixes_it(self):
        piece = self._item(PRD_SPEC_FINISH_ITEM, unit=PRD_UNIT_PIECE, unit_weight=15)
        kilo = self._item(PRD_SPEC_FINISH_ITEM, unit=PRD_UNIT_KG, unit_weight=999, segment="003")
        self.assertEqual(piece.effective_unit_weight, Decimal("15"))
        self.assertEqual(kilo.effective_unit_weight, Decimal("1"))


class StockAndStatusTests(TestCase):
    def setUp(self):
        group = ProductNode.objects.create(level=PRD_LEVEL_GROUP, code_segment="01", name="Raw")
        sub = ProductNode.objects.create(parent=group, level=PRD_LEVEL_SUB_GROUP, code_segment="01", name="Wheat")
        self.item = ProductNode.objects.create(
            parent=sub,
            level=PRD_LEVEL_ITEM,
            code_segment="001",
            name="Wheat Pvt - P",
            specification=PRD_SPEC_RAW_ITEM,
            unit=PRD_UNIT_KG,
        )

    def test_stock_is_the_signed_ledger_sum(self):
        services.post_movement(self.item, 100, PRD_LEDGER_PURCHASE)
        services.post_movement(self.item, -30, PRD_LEDGER_PURCHASE)
        self.assertEqual(selectors.product_stock(self.item), Decimal("70.000"))

    def test_saving_the_opening_twice_rewrites_one_ledger_row(self):
        services.set_opening_balance(self.item, 500)
        services.set_opening_balance(self.item, 400)
        entries = ProductLedger.objects.filter(product=self.item, source=PRD_LEDGER_OPENING)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(selectors.product_stock(self.item), Decimal("400.000"))

    def test_rate_update_keeps_history(self):
        services.set_rate(self.item, 90, timezone.localdate())
        services.set_rate(self.item, 95, timezone.localdate())
        self.assertEqual(self.item.rates.count(), 2)
        self.assertEqual(self.item.rates.filter(is_current=True).count(), 1)
        self.assertEqual(self.item.rates.get(is_current=True).rate, Decimal("95"))

    def test_a_product_is_deactivated_not_deleted_and_closing_is_final(self):
        services.toggle_status(self.item)
        self.assertEqual(self.item.status, STATUS_INACTIVE)
        services.toggle_status(self.item)
        self.assertEqual(self.item.status, STATUS_ACTIVE)
        services.set_status(self.item, STATUS_CLOSED)
        with self.assertRaises(ValueError):
            services.toggle_status(self.item)
