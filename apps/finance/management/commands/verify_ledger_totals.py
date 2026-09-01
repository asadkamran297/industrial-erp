"""Prove a migration did not move the general ledger.

Run with ``--before`` ahead of the migration and ``--after`` behind it. The
second run diffs the two snapshots and exits non-zero on any difference, so it
can be wired into a deploy rather than read by eye.

What it snapshots is what a reader of the books would notice going wrong:
total debits and credits, the balance on every account, and how many vouchers
and lines carry them. A refactor that moves postings between documents is
allowed; one that changes any of these figures is not.
"""

import json
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from apps.finance.models import AccountVoucher, AccountVoucherLine

DEFAULT_DIR = Path(settings.BASE_DIR) / "deploy" / "backups"


def _snapshot() -> dict:
    totals = AccountVoucherLine.objects.aggregate(
        debit=Sum("debit_amount"), credit=Sum("credit_amount")
    )
    # Per account, because two errors that cancel each other out leave the
    # grand totals untouched and are exactly what this is meant to catch.
    balances = {
        row["account_no"]: str(
            (row["debit"] or Decimal("0.00")) - (row["credit"] or Decimal("0.00"))
        )
        for row in AccountVoucherLine.objects.values("account_no")
        .annotate(debit=Sum("debit_amount"), credit=Sum("credit_amount"))
        .order_by("account_no")
    }
    return {
        "total_debit": str(totals["debit"] or Decimal("0.00")),
        "total_credit": str(totals["credit"] or Decimal("0.00")),
        "voucher_count": AccountVoucher.objects.count(),
        "line_count": AccountVoucherLine.objects.count(),
        "account_balances": balances,
    }


class Command(BaseCommand):
    help = "Snapshot general ledger totals before a migration and verify them after."

    def add_arguments(self, parser):
        parser.add_argument("--before", action="store_true", help="Write the baseline snapshot.")
        parser.add_argument("--after", action="store_true", help="Compare against the baseline.")
        parser.add_argument(
            "--path",
            default=str(DEFAULT_DIR / "ledger_baseline.json"),
            help="Where the baseline snapshot is kept.",
        )

    def handle(self, *args, **options):
        if options["before"] == options["after"]:
            raise CommandError("Pass exactly one of --before or --after.")

        path = Path(options["path"])
        current = _snapshot()

        if options["before"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(current, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Baseline written to {path}"))
            self.stdout.write(
                f"  debit {current['total_debit']}  credit {current['total_credit']}  "
                f"vouchers {current['voucher_count']}  lines {current['line_count']}"
            )
            return

        if not path.exists():
            raise CommandError(f"No baseline at {path}. Run with --before first.")
        baseline = json.loads(path.read_text(encoding="utf-8"))

        problems = []
        for key in ("total_debit", "total_credit", "voucher_count", "line_count"):
            if baseline[key] != current[key]:
                problems.append(f"{key}: was {baseline[key]}, now {current[key]}")

        before_balances = baseline["account_balances"]
        after_balances = current["account_balances"]
        for code in sorted(set(before_balances) | set(after_balances)):
            was = before_balances.get(code, "0.00")
            now = after_balances.get(code, "0.00")
            if Decimal(was) != Decimal(now):
                problems.append(f"account {code}: was {was}, now {now}")

        if problems:
            self.stdout.write(self.style.ERROR("Ledger totals moved:"))
            for problem in problems:
                self.stdout.write(self.style.ERROR(f"  {problem}"))
            raise CommandError(f"{len(problems)} difference(s) against the baseline.")

        self.stdout.write(self.style.SUCCESS("Ledger unchanged."))
        self.stdout.write(
            f"  debit {current['total_debit']}  credit {current['total_credit']}  "
            f"vouchers {current['voucher_count']}  lines {current['line_count']}  "
            f"accounts {len(after_balances)}"
        )
