from django.urls import NoReverseMatch, reverse

from apps.core.constants import STATUS_REVERSED

# GL source_ref table prefix -> (document kind, detail url name); longest prefix wins.
SOURCE_DOCUMENTS = {
    "inv_purchase_invoices": ("Purchase Invoice", "inventory:purchase_invoice_detail", "inventory.PurchaseInvoice", "invoice_num"),
    "inv_purchase_return_masters": ("Purchase Return", "inventory:purchase_return_detail", "inventory.PurchaseReturnMaster", "return_num"),
    "inv_pos_masters": ("Sale Invoice", "inventory:pos_detail", "inventory.POSMaster", "sale_num"),
    "inv_pos_return_masters": ("Sale Return", "inventory:pos_return_detail", "inventory.POSReturnMaster", "return_num"),
}


def doc_link(kind, label, url, dead=False):
    return {"kind": kind, "label": str(label or ""), "url": str(url or ""), "dead": bool(dead)}


def url_or_blank(name, *args, query=""):
    try:
        url = reverse(name, args=args)
    except NoReverseMatch:
        return ""
    return f"{url}?{query}" if query else url


def _voucher_kind(source_ref):
    prefix = source_ref.split(":", 1)[0]
    if prefix.endswith("_reversal"):
        return "Reversal Voucher"
    if prefix.endswith("_paid"):
        return "Payment Voucher"
    return "GL Voucher"


def voucher_links(*source_refs):
    from apps.finance.models import AccountVoucher

    refs = [ref for ref in source_refs if ref]
    if not refs:
        return []
    vouchers = AccountVoucher.objects.filter(source_ref__in=refs).order_by("voucher_date", "id")
    return [
        doc_link(_voucher_kind(v.source_ref), v.voucher_no, reverse("finance:account_voucher_detail", args=[v.pk]),
                 dead=v.status == STATUS_REVERSED)
        for v in vouchers
    ]


def ref_family(table, pk):
    """Every source_ref a document can post under: itself, its payment, and their reversals."""
    return [f"{table}{suffix}:{pk}" for suffix in ("", "_paid", "_reversal", "_paid_reversal")]


def first_voucher_url(*source_refs):
    from apps.finance.models import AccountVoucher

    voucher = AccountVoucher.objects.filter(source_ref__in=[r for r in source_refs if r]).order_by("id").first()
    return reverse("finance:account_voucher_detail", args=[voucher.pk]) if voucher else ""


def source_document_link(source_ref):
    if not source_ref or ":" not in source_ref:
        return None
    prefix, _, rest = source_ref.partition(":")
    pk = rest.split(":", 1)[0]
    if not pk.isdigit():
        return None
    for table in sorted(SOURCE_DOCUMENTS, key=len, reverse=True):
        if prefix == table or prefix.startswith(f"{table}_"):
            from django.apps import apps

            kind, url_name, model, number = SOURCE_DOCUMENTS[table]
            record = apps.get_model(model).objects.filter(pk=int(pk)).first()
            if record is None:
                return None
            return doc_link(kind, getattr(record, number) or f"#{pk}", reverse(url_name, args=[record.pk]),
                            dead=getattr(record, "status", "") == STATUS_REVERSED)
    return None
