"""Dump the purchase bills to a file before the tables are dropped.

The bills themselves are not needed after the refactor -- every one of them is
carried on a ``PurchaseInvoice`` with its ``legacy_bill_no``, and the voucher it
posted is untouched -- but a dump costs nothing and means the decision to drop
the tables is not the only copy of them that ever existed.

Run before migration 0041. It is a no-op once the tables are gone.
"""

import json
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import ProgrammingError

DEFAULT_PATH = Path(settings.BASE_DIR) / "deploy" / "backups" / "purchase_bills.json"


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class Command(BaseCommand):
    help = "Write the purchase bills and their lines to a JSON file before they are dropped."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(DEFAULT_PATH))

    def handle(self, *args, **options):
        from apps.inventory.models import PurchaseBill

        path = Path(options["path"])
        try:
            bills = list(PurchaseBill.all_objects.order_by("seq_num").prefetch_related("items"))
        except ProgrammingError:
            self.stdout.write("Purchase bill tables are already gone; nothing to archive.")
            return

        payload = []
        for bill in bills:
            row = {
                field.name: _plain(getattr(bill, field.attname, None))
                for field in bill._meta.fields
            }
            row["items"] = [
                {field.name: _plain(getattr(line, field.attname, None))
                 for field in line._meta.fields}
                for line in bill.items.all()
            ]
            payload.append(row)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Archived {len(payload)} bills to {path}"))
