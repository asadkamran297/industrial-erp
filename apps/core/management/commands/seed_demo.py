"""Seed a full book of demo data for walking the flour mill end to end.

Master data comes from ``seed``; this command adds the trading records on top:
customers, mill staff with payroll, wheat slips, bardana and stores purchases,
grinding runs and cash/bank vouchers, all built through the real services so
the product ledger, item ledger and general ledger move the way they do on the
screens.

Idempotent: every record carries a marker, so a second run adds nothing.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.finance.seeders.demo_vouchers import (
    seed_demo_accounts,
    seed_demo_fiscal_year,
    seed_demo_vouchers,
)
from apps.hr.seeders.demo_employees import seed_demo_employees
from apps.inventory.seeders.demo_customers import seed_demo_customers
from apps.inventory.seeders.demo_transactions import (
    seed_demo_bardana_purchases,
    seed_demo_purchase_invoices,
    seed_demo_purchase_orders,
    seed_demo_stores_purchases,
    seed_demo_wheat_purchases,
)
from apps.production.seeders.grinding import seed_grinding

DEFAULT_COUNT = 50


class Command(BaseCommand):
    help = "Seed demo customers, staff, wheat slips, bardana and stores purchases, grinding runs and vouchers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=DEFAULT_COUNT,
            help=f"How many records per entity (default {DEFAULT_COUNT}).",
        )

    def handle(self, *args, **options):
        count = options["count"]
        user = get_user_model().objects.filter(is_superuser=True).order_by("pk").first()
        if user is None:
            raise CommandError(
                "No superuser found. Run `python manage.py ensure_superuser` first."
            )

        steps = [
            ("chart of accounts", lambda: seed_demo_accounts()),
            ("fiscal year", lambda: seed_demo_fiscal_year()),
            ("customers", lambda: seed_demo_customers(count)),
            ("mill staff, salaries and payroll", lambda: seed_demo_employees(count)),
            ("wheat purchase slips", lambda: seed_demo_wheat_purchases(count, user=user)),
            ("bardana purchases", lambda: seed_demo_bardana_purchases(count // 2 or 1, user=user)),
            ("stores purchase orders", lambda: seed_demo_purchase_orders(count, user=user)),
            ("invoices against orders", lambda: seed_demo_purchase_invoices(count, user=user)),
            ("direct stores purchases", lambda: seed_demo_stores_purchases(count, user=user)),
            ("grinding runs", lambda: seed_grinding(count // 2 or 1, user=user)),
            ("vouchers", lambda: seed_demo_vouchers(count, user=user)),
        ]

        total = 0
        for label, step in steps:
            created = step()
            total += created
            self.stdout.write(self.style.SUCCESS(f"  {label}: {created} created"))

        self.stdout.write(self.style.SUCCESS(f"Demo data seeded. {total} new records."))
