"""Bring existing data in line with the November 2026 accounts review.

Runs inside one transaction and rolls back unless ``--apply`` is given.

1. Chart of accounts: headings/accounts flags, standard accounts, stock split.
2. Unposted demo vouchers (E-DEMO-nnn / R-DEMO-nnn): soft-deleted.
3. Mill openings, sales and sale returns with no godown: moved to ``--godown``.
4. Old "Inventory" account: one journal moving its balance to the split stock accounts.
5. Approved payrolls: posted to the books.
6. Report only: unposted manual vouchers, wheat slips with too few kg per bag.
"""

import re
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.constants import (
    GL_INVENTORY_PATH,
    GL_STOCK_LABELS,
    GL_STOCK_STORES,
    PRD_LEDGER_OPENING,
    PRD_LEDGER_SALE,
    PRD_LEDGER_SALE_RETURN,
    STATUS_ACTIVE,
    STATUS_APPROVED,
    VOUCHER_TYPE_JOURNAL,
    WHEAT_MIN_KG_PER_SACK,
    YES,
)
from apps.finance.models import AccountVoucher, ChartOfAccount, posted_lines

DEMO_VOUCHER = re.compile(r"^[ER]-DEMO-\d+$")
RECLASS_REF = "inventory_reclass:1"


class Rollback(Exception):
    pass


class Command(BaseCommand):
    help = "Repair books after the accounts review (dry run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Save the changes.")
        parser.add_argument("--godown", type=int, help="Godown id for mill openings and sales saved without one.")
        parser.add_argument("--post-manual", action="store_true", help="Also post balanced manual vouchers left unposted.")

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                self._run(options)
                if not options["apply"]:
                    raise Rollback
        except Rollback:
            self.stdout.write(self.style.WARNING("Dry run: nothing saved. Re-run with --apply."))
            return
        self.stdout.write(self.style.SUCCESS("Saved."))

    def _run(self, options):
        self._heading("1. Chart of accounts")
        call_command("seed_chart_of_accounts", stdout=self.stdout)

        self._heading("2. Demo vouchers")
        self._demo_vouchers()

        self._heading("3. Mill openings and sales without a godown")
        self._sale_godowns(options.get("godown"))

        self._heading("4. Inventory account split")
        self._inventory_reclass()

        self._heading("5. Approved payrolls")
        self._payrolls()

        self._heading("6. Unposted manual vouchers")
        self._manual_vouchers(options["post_manual"])

        self._heading("7. Wheat slips to check (bags)")
        self._bag_counts()

    def _heading(self, text):
        self.stdout.write(self.style.MIGRATE_HEADING(text))

    def _line(self, text):
        self.stdout.write(f"  {text}")

    def _demo_vouchers(self):
        found = [
            voucher for voucher in AccountVoucher.objects.filter(voucher_no__contains="-DEMO-", source_ref="")
            if DEMO_VOUCHER.match(voucher.voucher_no)
        ]
        for voucher in found:
            if voucher.posted == YES:
                self._line(f"{voucher.voucher_no}: posted, left alone")
                continue
            voucher.soft_delete()
            self._line(f"{voucher.voucher_no} {voucher.voucher_date:%d-%m-%Y} {voucher.debit_amount:,.2f}: deleted")
        if not found:
            self._line("none")

    def _sale_godowns(self, godown_id):
        from apps.godowns.models import Godown
        from apps.inventory.models import POSMaster, POSReturnMaster
        from apps.products.models import ProductLedger

        entries = ProductLedger.objects.filter(godown__isnull=True, source__in=(PRD_LEDGER_OPENING, PRD_LEDGER_SALE, PRD_LEDGER_SALE_RETURN))
        count = entries.count()
        if not count:
            self._line("none")
            return
        godowns = Godown.objects.filter(status=STATUS_ACTIVE)
        if godown_id is None and godowns.count() == 1:
            godown_id = godowns.first().pk
        godown = godowns.filter(pk=godown_id).first() if godown_id else None
        if godown is None:
            choices = ", ".join(f"{g.pk}={g.name}" for g in godowns.order_by("pk"))
            raise CommandError(f"{count} opening/sale entries have no godown. Pass --godown (one of: {choices}).")
        sale_refs = set(entries.filter(source=PRD_LEDGER_SALE).values_list("reference", flat=True))
        return_refs = set(entries.filter(source=PRD_LEDGER_SALE_RETURN).values_list("reference", flat=True))
        entries.update(godown=godown, updated_at=timezone.now())
        sales = POSMaster.objects.filter(sale_num__in=sale_refs, godown__isnull=True).update(godown=godown)
        return_sales = POSMaster.objects.filter(
            pk__in=POSReturnMaster.objects.filter(return_num__in=return_refs).values("pos_master_id"), godown__isnull=True,
        ).update(godown=godown)
        self._line(f"{count} ledger entries and {sales + return_sales} sales moved to {godown.name}")

    def _inventory_reclass(self):
        from apps.finance.services import _post_voucher, stock_entries

        if AccountVoucher.objects.filter(source_ref=RECLASS_REF).exists():
            self._line("already done")
            return
        legacy = ChartOfAccount.objects.filter(title=GL_INVENTORY_PATH[-1], parent__title=GL_INVENTORY_PATH[-2]).first()
        if legacy is None or not legacy.code:
            self._line("no old Inventory account")
            return
        zero = Decimal("0.00")
        shares, total = {}, zero
        for line in posted_lines().filter(account_no=legacy.code).select_related("voucher"):
            amount = (line.debit_amount or zero) - (line.credit_amount or zero)
            total += amount
            for bucket, part in self._split(line.voucher.source_ref, amount).items():
                shares[bucket] = shares.get(bucket, zero) + part
        shares = {bucket: amount.quantize(Decimal("0.01")) for bucket, amount in shares.items() if amount}
        if not total:
            self._line("old Inventory account is already nil")
            return
        for bucket, amount in sorted(shares.items()):
            self._line(f"{GL_STOCK_LABELS[bucket]}: {amount:,.2f}")
        entries = stock_entries(shares, debit=True, remark="Stock moved from the old Inventory account")
        entries.append((legacy.code, zero, total, "Balance moved to stock accounts") if total > 0
                       else (legacy.code, -total, zero, "Balance moved to stock accounts"))
        voucher = _post_voucher(
            source_ref=RECLASS_REF, voucher_type=VOUCHER_TYPE_JOURNAL, voucher_date=timezone.localdate(),
            account_no=legacy.code, remarks="Inventory split into stock accounts", entries=entries,
        )
        self._line(f"{total:,.2f} moved in {voucher.voucher_no}")

    def _split(self, source_ref, amount):
        from apps.finance.services import purchase_invoice_stock_split, purchase_return_stock_split, split_by_bucket
        from apps.inventory.models import PurchaseInvoice, PurchaseReturnMaster

        table, _, rest = (source_ref or "").partition(":")
        table = table.removesuffix("_reversal")
        pk = rest.split(":")[0]
        weights = None
        if pk.isdigit() and table == "inv_purchase_invoices":
            invoice = PurchaseInvoice.all_objects.filter(pk=int(pk)).first()
            weights = purchase_invoice_stock_split(invoice) if invoice else None
        elif pk.isdigit() and table == "inv_purchase_return_masters":
            purchase_return = PurchaseReturnMaster.all_objects.filter(pk=int(pk)).first()
            weights = purchase_return_stock_split(purchase_return) if purchase_return else None
        if not weights:
            return {GL_STOCK_STORES: amount}
        return split_by_bucket(list(weights.items()), amount)

    def _payrolls(self):
        from apps.payroll.models import Payroll
        from apps.payroll.services import sync_payroll_gl

        posted = 0
        for payroll in Payroll.objects.filter(status=STATUS_APPROVED).select_related("employee"):
            if sync_payroll_gl(payroll) is not None:
                posted += 1
        self._line(f"{posted} approved payrolls in the books")

    def _manual_vouchers(self, post):
        from apps.finance.services import post_manual_voucher

        pending = AccountVoucher.objects.filter(source_ref="").exclude(posted=YES).order_by("voucher_date", "voucher_no")
        if not pending.exists():
            self._line("none")
            return
        for voucher in pending:
            state = "balanced" if voucher.is_balanced and voucher.lines.exists() else "NOT balanced"
            if post and state == "balanced":
                post_manual_voucher(voucher=voucher)
                state = "posted"
            self._line(f"{voucher.voucher_no} {voucher.voucher_date:%d-%m-%Y} {voucher.debit_amount:,.2f}: {state}")

    def _bag_counts(self):
        from apps.inventory.models import PurchaseInvoiceLine

        flagged = 0
        for invoice_id, lines in self._wheat_invoices(PurchaseInvoiceLine).items():
            kg = sum((line.selected_weight or line.mill_weight or line.party_weight or Decimal("0")) for line in lines if line.product and not line.bardana_ownership)
            bags = sum((line.quantity for line in lines if line.bardana_ownership), Decimal("0"))
            if bags and kg and kg / bags < WHEAT_MIN_KG_PER_SACK:
                flagged += 1
                self._line(f"{lines[0].invoice.invoice_num}: {kg:,.0f} kg, {bags:,.0f} bags ({kg / bags:,.1f} kg/bag)")
        if not flagged:
            self._line("none")

    def _wheat_invoices(self, line_model):
        grouped = {}
        for line in line_model.objects.filter(product__isnull=False).select_related("invoice", "product"):
            grouped.setdefault(line.invoice_id, []).append(line)
        return grouped
