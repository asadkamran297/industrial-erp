"""Repair the two data faults the chart-of-accounts audit found.

1. Unposted vouchers whose lines point at account codes that do not exist in
   the chart. They are one-sided entries left over from seed data, and because
   ``account_balances()`` can only report on codes it knows, they were being
   dropped from every statement — which is what made the trial balance appear
   to balance. They are soft-deleted, so the rows survive for audit.

2. Opening balances entered on the asset side with no counterpart. Assets held
   at day one came from the owner, so the matching credit belongs in Owner's
   Capital. Without it the accounting equation cannot hold.

Both steps are idempotent: a second run finds nothing to do. Use ``--dry-run``
to see the changes without writing them.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.constants import GL_OPENING_EQUITY_PATH, STATUS_ACTIVE
from apps.finance.models import AccountVoucher, AccountVoucherLine, ChartOfAccount
from apps.finance.services import signed_to_dr_cr

# Where the missing opening counterpart belongs.
OWNER_CAPITAL_TITLE = "Owner's Capital"


class Command(BaseCommand):
    help = "Remove orphaned seed vouchers and balance the opening entry."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change without saving.")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        zero = Decimal("0.00")

        # ── 1. vouchers posting to codes that are not in the chart ──────────
        known = {code for code in ChartOfAccount.objects.values_list("code", flat=True) if code}
        orphan_line_ids = set(
            AccountVoucherLine.objects.exclude(account_no__in=known).values_list("id", flat=True)
        )
        voucher_ids = set(
            AccountVoucherLine.objects.filter(id__in=orphan_line_ids).values_list("voucher_id", flat=True)
        )
        vouchers = AccountVoucher.objects.filter(id__in=voucher_ids)

        self.stdout.write(self.style.MIGRATE_HEADING("Vouchers posting to unknown accounts"))
        removed = 0
        for voucher in vouchers.order_by("voucher_no"):
            if voucher.posted == "Y":
                # A posted voucher is history; correcting it needs a reversing
                # entry, not a deletion. Flag it rather than touch it.
                self.stdout.write(self.style.WARNING(
                    f"  {voucher.voucher_no}: POSTED — left alone, reverse it manually"
                ))
                continue
            detail = ", ".join(
                f"{line.account_no} Dr {line.debit_amount:,.2f} Cr {line.credit_amount:,.2f}"
                for line in voucher.lines.all()
            )
            self.stdout.write(f"  {voucher.voucher_no:<14} {detail}")
            if not dry_run:
                # Queryset updates, not model.soft_delete(): AccountVoucherLine
                # .save() runs full_clean(), and these rows fail validation on
                # the very field being cleaned up — so the model can refuse to
                # let its own invalid data be removed.
                stamp = timezone.now()
                AccountVoucherLine.all_objects.filter(voucher=voucher).update(
                    is_active=False, deleted_at=stamp, updated_at=stamp
                )
                AccountVoucher.all_objects.filter(pk=voucher.pk).update(
                    is_active=False, deleted_at=stamp, updated_at=stamp
                )
            removed += 1
        if not removed:
            self.stdout.write("  none")

        # ── 2. opening balances that do not balance ─────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Opening balance counterpart"))
        debit = credit = zero
        for account in ChartOfAccount.objects.filter(status=STATUS_ACTIVE, children__isnull=True):
            row_debit, row_credit = signed_to_dr_cr(account.opening_balance or zero, account.account_type)
            debit += row_debit
            credit += row_credit
        difference = debit - credit
        self.stdout.write(f"  opening Dr {debit:,.2f}   Cr {credit:,.2f}   out by {difference:,.2f}")

        if not difference:
            self.stdout.write("  already balanced — nothing to post")
        else:
            capital = ChartOfAccount.objects.filter(
                title=OWNER_CAPITAL_TITLE, status=STATUS_ACTIVE
            ).first()
            if not capital:
                capital = ChartOfAccount.objects.filter(
                    title=GL_OPENING_EQUITY_PATH[-1], status=STATUS_ACTIVE
                ).first()
            if not capital:
                self.stdout.write(self.style.ERROR(
                    f"  no '{OWNER_CAPITAL_TITLE}' account found — create one and re-run"
                ))
            else:
                # Capital is credit-natured, so a positive balance is a credit:
                # exactly what the surplus of opening debits needs.
                new_balance = (capital.opening_balance or zero) + difference
                self.stdout.write(
                    f"  {capital.code} {capital.title}: "
                    f"{capital.opening_balance:,.2f} -> {new_balance:,.2f} (credit)"
                )
                if not dry_run:
                    capital.opening_balance = new_balance
                    capital.save(update_fields=["opening_balance", "updated_at"])

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING("dry run — nothing saved"))
        else:
            self.stdout.write(self.style.SUCCESS(f"{removed} voucher(s) removed; opening entry balanced."))
