from decimal import Decimal

from django.urls import reverse

from apps.inventory.tests_reports_purchase import PurchaseReportFixture

from . import selectors_purchase as sel


class GateSelectorTests(PurchaseReportFixture):
    def test_register_variance_and_vehicle(self):
        data = sel.weighbridge_register(self.today, self.today)
        row = data["rows"][0]
        self.assertEqual(row["difference"], Decimal("-50.000"))
        self.assertEqual(row["weight_source"], "Mill")
        self.assertEqual(row["cost_impact"], Decimal("-500.00"))
        self.assertEqual(data["totals"]["vehicles"], 1)
        self.assertEqual(sel.weighbridge_register(self.today, self.today, min_difference=Decimal("60"))["totals"]["slips"], 0)
        vehicle = sel.vehicle_report(self.today, self.today)["rows"][0]
        self.assertEqual(vehicle["vehicle"], "LEA-123")
        self.assertEqual(vehicle["net_mund"], Decimal("100.000"))
        self.assertEqual(sel.gate_sheet(self.today, self.today)["totals"]["credit_kg"], Decimal("4000.000"))


class GateScreenTests(PurchaseReportFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_every_gate_report_renders_and_exports(self):
        for name in ("report_weighbridge", "report_vehicles", "report_weight_variance", "report_gate_sheet"):
            with self.subTest(report=name):
                self.assertEqual(self.client.get(reverse(f"inventory:{name}"), {"preset": "today"}).status_code, 200)
                for fmt in ("csv", "xlsx", "pdf", "png"):
                    self.assertEqual(self.client.get(reverse(f"inventory:{name}_export"), {"format": fmt, "preset": "today"}).status_code, 200, f"{name} {fmt}")
