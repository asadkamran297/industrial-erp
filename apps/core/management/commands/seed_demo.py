"""Seed a full book of demo data for walking the ERP end to end.

Master data comes from ``seed``; this command adds the trading records on top:
customers, employees with payroll, and purchase and sale documents built
through the real services so stock, the item ledger and the general ledger all
move the way they do on the screens.

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
    seed_demo_direct_purchases,
    seed_demo_purchase_bills,
    seed_demo_purchase_orders,
    seed_demo_sales,
)

DEFAULT_COUNT = 50


class Command(BaseCommand):
    help = "Seed demo customers, employees, purchase orders, bills, sales and vouchers."

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
        # The purchase and sale services run their real permission checks, and
        # those dereference the user, so a fresh database with no superuser
        # crashes deep inside a service instead of failing here.
        if user is None:
            raise CommandError(
                "No superuser found. Run `python manage.py ensure_superuser` first."
            )

        # Order matters: bills need approved orders, and sales need the stock
        # those bills brought in.
        steps = [
            ("chart of accounts", lambda: seed_demo_accounts()),
            ("fiscal year", lambda: seed_demo_fiscal_year()),
            ("customers", lambda: seed_demo_customers(count)),
            ("employees, salaries and payroll", lambda: seed_demo_employees(count)),
            ("purchase orders", lambda: seed_demo_purchase_orders(count, user=user)),
            ("supplier bills", lambda: seed_demo_purchase_bills(count, user=user)),
            ("purchase invoices", lambda: seed_demo_direct_purchases(count, user=user)),
            ("sales", lambda: seed_demo_sales(count, user=user)),
            ("vouchers", lambda: seed_demo_vouchers(count, user=user)),
        ]

        total = 0
        for label, step in steps:
            created = step()
            total += created
            self.stdout.write(self.style.SUCCESS(f"  {label}: {created} created"))

        self.stdout.write(self.style.SUCCESS(f"Demo data seeded. {total} new records."))
