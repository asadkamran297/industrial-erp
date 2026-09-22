from decimal import Decimal

from django.urls import reverse

from apps.core.reporting import GROUP_DAY, GROUP_MONTH
from apps.portal.tests import OwnerPackFixture

from . import report_selectors as sel
from .models import GrindingVoucher


class ProductionSelectorTests(OwnerPackFixture):
    def test_register_daily_yield_mix(self):
        GrindingVoucher.objects.update(standard_yield_percent=Decimal("92"), shortage_kg=Decimal("100"), shortage_percent=Decimal("10"))
        reg = sel.grinding_register(self.today, self.today)
        self.assertEqual(reg["totals"]["yield_pct"], Decimal("90.00"))
        self.assertEqual(reg["totals"]["below"], 1)
        daily = sel.daily_grinding(self.today, self.today)
        self.assertEqual(daily["rows"][0]["runs"], 1)
        self.assertEqual(daily["totals"]["downtime_days"], 0)
        trend = sel.yield_trend(self.today, self.today, GROUP_DAY)
        self.assertEqual(trend["rows"][0]["variance_pct"], Decimal("-2.00"))
        self.assertEqual(trend["best"][1], Decimal("90.00"))
        mix = sel.output_mix(self.today, self.today)["rows"][0]
        self.assertEqual(mix["share_pct"], Decimal("100.00"))
        self.assertEqual(mix["of_wheat_pct"], Decimal("90.00"))
        short = sel.shortage_report(self.today, self.today)
        self.assertEqual(short["rows"][0]["standard_shortage_kg"], Decimal("80.000"))
        self.assertEqual(short["rows"][0]["excess_kg"], Decimal("20.000"))
        self.assertEqual(short["rows"][0]["cost"], Decimal("1000.00"))

    def test_cost_per_bag_and_summary(self):
        cost = sel.cost_per_bag(self.today, self.today)
        self.assertEqual(cost["totals"]["wheat_rate"], Decimal("10.00"))
        self.assertEqual(cost["totals"]["wheat_cost"], Decimal("10000.00"))
        self.assertEqual(cost["rows"][0]["cost_per_bag"], Decimal("222.22"))
        summary = sel.production_summary(self.today, self.today, GROUP_MONTH)["rows"][0]
        self.assertEqual(summary["wheat_mund"], Decimal("25.000"))
        self.assertEqual(summary["yield_pct"], Decimal("90.00"))
        self.assertEqual(sel.conversion_register(self.today, self.today)["totals"]["conversions"], 0)


class ProductionScreenTests(OwnerPackFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_production_report_renders_and_exports(self):
        for name in ("report_grinding_register", "report_daily_grinding", "report_yield_trend", "report_output_mix", "report_shortage", "report_conversions", "report_cost_per_bag", "report_production_summary"):
            with self.subTest(report=name):
                self.assertEqual(self.client.get(reverse(f"production:{name}"), {"preset": "month"}).status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    self.assertEqual(self.client.get(reverse(f"production:{name}_export"), {"format": fmt, "preset": "month"}).status_code, 200, f"{name} {fmt}")
