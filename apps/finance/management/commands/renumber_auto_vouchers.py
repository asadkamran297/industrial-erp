from django.core.management.base import BaseCommand
from django.db import transaction

from apps.finance.models import AccountVoucher, AccountVoucherLine

SOURCES = {
    "inv_purchase_invoices": ("PurchaseInvoice", "invoice_num", ""),
    "inv_purchase_invoices_paid": ("PurchaseInvoice", "invoice_num", "-PMT"),
    "inv_pos_masters": ("POSMaster", "sale_num", ""),
    "inv_pos_return_masters": ("POSReturnMaster", "return_num", ""),
    "inv_purchase_return_masters": ("PurchaseReturnMaster", "return_num", ""),
}
REVERSAL = "_reversal"


class Command(BaseCommand):
    help = "Give auto-posted GL vouchers the number of the document that raised them. Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def target(self, source_ref):
        from apps.inventory import models as inv

        table, _, pk = (source_ref or "").partition(":")
        spec = SOURCES.get(table)
        if not spec or not pk.isdigit():
            return ""
        model, field, suffix = spec
        number = getattr(inv, model).objects.filter(pk=int(pk)).values_list(field, flat=True).first()
        return f"{number}{suffix}" if number else ""

    def handle(self, *args, **options):
        vouchers = list(AccountVoucher.all_objects.exclude(source_ref="").order_by("pk"))
        taken = set(AccountVoucher.all_objects.values_list("voucher_no", flat=True))
        plan = {}
        for voucher in vouchers:
            if voucher.source_ref.split(":")[0].endswith(REVERSAL):
                continue
            new = self.target(voucher.source_ref)
            if new and new != voucher.voucher_no and new not in taken:
                plan[voucher.pk] = (voucher.voucher_no, new)
                taken.add(new)
        renamed = {old: new for old, new in plan.values()}
        for voucher in vouchers:
            table, _, pk = voucher.source_ref.partition(":")
            if not table.endswith(REVERSAL):
                continue
            base_ref = f"{table[: -len(REVERSAL)]}:{pk}"
            base = next((v for v in vouchers if v.source_ref == base_ref), None)
            if base is None:
                continue
            new = f"{renamed.get(base.voucher_no, base.voucher_no)}-REV"
            if new != voucher.voucher_no and new not in taken:
                plan[voucher.pk] = (voucher.voucher_no, new)
                taken.add(new)

        self.stdout.write(f"{len(plan)} voucher(s) to renumber.")
        for old, new in list(plan.values())[:10]:
            self.stdout.write(f"  {old} -> {new}")
        if not options["apply"]:
            self.stdout.write("Dry run. Re-run with --apply to write.")
            return

        from apps.inventory.models import POSMaster, PurchaseInvoice

        with transaction.atomic():
            for pk, (old, new) in plan.items():
                AccountVoucher.all_objects.filter(pk=pk).update(voucher_no=new)
                AccountVoucherLine.objects.filter(voucher_id=pk).update(voucher_no=new)
                PurchaseInvoice.objects.filter(journal_ref=old).update(journal_ref=new)
                POSMaster.objects.filter(journal_ref=old).update(journal_ref=new)
        self.stdout.write(self.style.SUCCESS(f"Renumbered {len(plan)} voucher(s)."))
