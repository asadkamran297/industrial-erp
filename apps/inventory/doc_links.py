from django.urls import reverse

from apps.core.constants import STATUS_REVERSED
from apps.core.doc_links import doc_link, ref_family, url_or_blank, voucher_links


def _supplier(supplier):
    return doc_link("Supplier", supplier.name, reverse("inventory:supplier_detail", args=[supplier.pk]))


def _customer(customer):
    if customer is None:
        return None
    return doc_link("Customer", customer.customer_name, reverse("inventory:customer_detail", args=[customer.pk]))


def _ledger(code, label="Ledger"):
    if not code:
        return None
    return doc_link(label, code, url_or_blank("finance:account_ledger", query=f"account_no={code}"))


def _clean(links):
    return [link for link in links if link]


def purchase_order(order):
    links = [_supplier(order.supplier)]
    for invoice in order.invoices.all():
        links.append(doc_link("Purchase Invoice", invoice.invoice_num,
                              reverse("inventory:purchase_invoice_detail", args=[invoice.pk]),
                              dead=invoice.status == STATUS_REVERSED))
    from .models import PurchaseReturnMaster

    for entry in PurchaseReturnMaster.objects.filter(purchase_order=order).order_by("return_date", "pk"):
        links.append(doc_link("Purchase Return", entry.return_num or "Draft",
                              reverse("inventory:purchase_return_detail", args=[entry.pk]),
                              dead=entry.status == STATUS_REVERSED))
    actions = {
        "new_url": reverse("inventory:purchase_order_create"),
        "print_url": reverse("inventory:purchase_order_print", args=[order.pk]),
    }
    return _clean(links), actions


def purchase_invoice(invoice, source_orders=()):
    links = [_supplier(invoice.supplier)]
    for order in source_orders:
        links.append(doc_link("Purchase Order", order.purchase_num, reverse("inventory:purchase_order_detail", args=[order.pk])))
    for entry in invoice.returns.all().order_by("return_date", "pk"):
        links.append(doc_link("Purchase Return", entry.return_num or "Draft",
                              reverse("inventory:purchase_return_detail", args=[entry.pk]),
                              dead=entry.status == STATUS_REVERSED))
    refs = ref_family("inv_purchase_invoices", invoice.pk)
    links += voucher_links(*refs)
    wheat = invoice.items.filter(product__isnull=False).exists()
    actions = {
        "new_url": reverse("inventory:purchase_invoice_create" if wheat else "inventory:stores_purchase_create"),
        "print_url": reverse("inventory:purchase_invoice_print", args=[invoice.pk]),
        "print_label": "Invoice",
        "voucher_url": reverse("inventory:purchase_voucher_print", args=[invoice.pk]) if wheat else "",
    }
    return _clean(links), actions


def purchase_return(record):
    links = [_supplier(record.supplier)]
    if record.purchase_invoice_id:
        invoice = record.purchase_invoice
        links.append(doc_link("Purchase Invoice", invoice.invoice_num,
                              reverse("inventory:purchase_invoice_detail", args=[invoice.pk]),
                              dead=invoice.status == STATUS_REVERSED))
    if record.purchase_order_id:
        links.append(doc_link("Purchase Order", record.purchase_order.purchase_num,
                              reverse("inventory:purchase_order_detail", args=[record.purchase_order_id])))
    refs = ref_family("inv_purchase_return_masters", record.pk)
    links += voucher_links(*refs)
    actions = {
        "new_url": reverse("inventory:purchase_return_create"),
        "print_url": reverse("inventory:purchase_return_receipt", args=[record.pk]) if record.return_num else "",
    }
    return _clean(links), actions


def sale(record):
    links = [_customer(record.customer)]
    if record.sales_order_id:
        order = record.sales_order
        links.append(doc_link("Sales Order", order.order_num,
                              url_or_blank("inventory:sales_order_list", query=f"q={order.order_num}")))
    for entry in record.returns.all().order_by("pk"):
        links.append(doc_link("Sale Return", entry.return_num or "Draft",
                              reverse("inventory:pos_return_detail", args=[entry.pk]),
                              dead=entry.status == STATUS_REVERSED))
    refs = ref_family("inv_pos_masters", record.pk)
    links += voucher_links(*refs)
    actions = {
        "new_url": url_or_blank("inventory:sale_invoice_create"),
        "print_url": reverse("inventory:pos_receipt", args=[record.pk]),
        "print_label": "Invoice",
        "edit_url": reverse("inventory:pos_update", args=[record.pk]) if record.posted != "Y" else "",
    }
    return _clean(links), actions


def sale_return(record):
    links = [_customer(record.customer)]
    if record.pos_master_id:
        links.append(doc_link("Sale Invoice", record.pos_master.sale_num,
                              reverse("inventory:pos_detail", args=[record.pos_master_id])))
    refs = ref_family("inv_pos_return_masters", record.pk)
    links += voucher_links(*refs)
    actions = {
        "print_url": reverse("inventory:pos_return_receipt", args=[record.pk]),
    }
    return _clean(links), actions


def supplier(record, payable_code=""):
    links = [_ledger(payable_code)]
    actions = {"new_url": reverse("inventory:supplier_create")}
    return _clean(links), actions


def customer(record, receivable_code=""):
    links = [_ledger(receivable_code)]
    actions = {"new_url": reverse("inventory:customer_create")}
    return _clean(links), actions


def item(record):
    links = [
        doc_link("Item Ledger", record.item_name, url_or_blank("inventory:ledger_list", query=f"item={record.pk}")),
        doc_link("Stores Purchases", "Report", url_or_blank("inventory:report_stores_purchases", query=f"item={record.pk}")),
    ]
    return _clean(links), {}
