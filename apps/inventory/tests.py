from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE, STATUS_CREATED, STATUS_DRAFT, STATUS_SUBMITTED, STATUS_FULLY_INVOICED, STATUS_PARTIALLY_INVOICED

from .models import Customer, InventoryClass, InventoryItem, POSDetail, POSMaster, POSReturnDetail, POSReturnMaster, PurchaseOrder, PurchaseOrderItem, PurchaseReturnDetail, PurchaseReturnMaster, UOM, Supplier, PurchaseMaster
from .services import create_purchase_invoice, generate_transaction_id, post_purchase_return, post_sale, post_sale_return


class InventoryFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="pass12345")
        self.city = City.objects.create(title="Karachi", code="KHI", status=STATUS_ACTIVE)
        self.uom = UOM.objects.create(title="Kilogram", code="KG", status=STATUS_ACTIVE, created_by=self.user, updated_by=self.user)
        self.item_class = InventoryClass.objects.create(title="Raw Material", class_code="RM", status=STATUS_ACTIVE, created_by=self.user, updated_by=self.user)
        self.item = InventoryItem.objects.create(item_name="Steel Rod", uom=self.uom, item_class=self.item_class, price=Decimal("100.00"), created_by=self.user, updated_by=self.user)
        self.supplier = Supplier.objects.create(name="ABC Supplies", code="ABC1", city=self.city, status=STATUS_ACTIVE, created_by=self.user, updated_by=self.user)
        self.customer = Customer.objects.create(customer_name="Walk In", city=self.city, status=STATUS_ACTIVE, created_by=self.user, updated_by=self.user)

    def test_item_creates_zero_stock_row(self):
        self.assertEqual(self.item.stock.current_quantity, Decimal("0.0000"))

    def test_pos_page_renders_submit_handler_for_line_items(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("inventory:pos_list"))
        self.assertContains(response, "submitSale")
        self.assertContains(response, "guard(event)")

    def test_pos_page_hides_zero_stock_items(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("inventory:pos_list"))
        self.assertEqual(response.context["items_json"], [])

    def test_receive_sale_and_returns_update_stock(self):
        po = PurchaseOrder.objects.create(supplier=self.supplier, purchase_date=timezone.localdate(), created_by=self.user, updated_by=self.user)
        po_item = PurchaseOrderItem.objects.create(purchase_order=po, inventory_item=self.item, quantity=Decimal("10.0000"), rate=Decimal("100.00"), unit_rate=Decimal("100.0000"), uom=self.uom, descr=self.item.item_name, created_by=self.user, updated_by=self.user)
        po.status = STATUS_SUBMITTED
        po.save(update_fields=["status"])
        create_purchase_invoice(
            supplier=self.supplier,
            supplier_invoice_num="INV-1",
            lines=[{"inventory_item": self.item, "quantity": Decimal("10.0000"),
                    "rate": Decimal("120.00"), "order_item": po_item}],
            user=self.user,
        )
        self.item.stock.refresh_from_db()
        self.assertEqual(self.item.stock.current_quantity, Decimal("10.0000"))
        self.assertEqual(self.item.stock.current_price, Decimal("120.00"))

        sale = POSMaster.objects.create(transaction_id=generate_transaction_id("SAL", POSMaster), sale_date=timezone.localdate(), customer=self.customer, total_paid=Decimal("500.00"), created_by=self.user, updated_by=self.user)
        POSDetail.objects.create(pos_master=sale, inventory_item=self.item, quantity=Decimal("2.0000"), price=Decimal("150.00"), created_by=self.user, updated_by=self.user)
        post_sale(sale=sale, user=self.user)
        self.item.stock.refresh_from_db()
        self.assertEqual(self.item.stock.current_quantity, Decimal("8.0000"))

        sale_return = POSReturnMaster.objects.create(transaction_id=generate_transaction_id("SRT", POSReturnMaster), pos_master=sale, return_date=timezone.localdate(), customer=self.customer, created_by=self.user, updated_by=self.user)
        POSReturnDetail.objects.create(pos_return_master=sale_return, pos_detail=sale.items.first(), quantity=Decimal("1.0000"), created_by=self.user, updated_by=self.user)
        post_sale_return(sale_return=sale_return, user=self.user)
        self.item.stock.refresh_from_db()
        self.assertEqual(self.item.stock.current_quantity, Decimal("9.0000"))

        purchase_master = PurchaseMaster.objects.get(purchase_order=po)
        purchase_return = PurchaseReturnMaster.objects.create(transaction_id=generate_transaction_id("PRT", PurchaseReturnMaster), purchase_master=purchase_master, return_date=timezone.localdate(), created_by=self.user, updated_by=self.user)
        PurchaseReturnDetail.objects.create(purchase_return_master=purchase_return, inventory_item=self.item, quantity=Decimal("1.0000"), rate=Decimal("120.00"), created_by=self.user, updated_by=self.user)
        post_purchase_return(purchase_return=purchase_return, user=self.user)
        self.item.stock.refresh_from_db()
        self.assertEqual(self.item.stock.current_quantity, Decimal("8.0000"))
    def test_purchase_order_status_moves_from_draft_to_partial_to_fully_invoiced(self):
        """An order is moved along by the invoices against it, and nothing else."""
        po = PurchaseOrder.objects.create(
            supplier=self.supplier, purchase_date=timezone.localdate(),
            created_by=self.user, updated_by=self.user,
        )
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=po, inventory_item=self.item, quantity=Decimal("10.0000"),
            rate=Decimal("100.00"), unit_rate=Decimal("100.0000"), uom=self.uom,
            descr=self.item.item_name, created_by=self.user, updated_by=self.user,
        )

        # An order starts as a draft: nobody has committed to it yet, and
        # nothing may be invoiced against it until somebody has.
        self.assertEqual(po.status, STATUS_DRAFT)
        po.status = STATUS_SUBMITTED
        po.save(update_fields=["status"])

        create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-PO-1",
            lines=[{"inventory_item": self.item, "quantity": Decimal("4.0000"),
                    "rate": Decimal("120.00"), "order_item": po_item}],
            user=self.user,
        )
        po.refresh_from_db()
        po_item.refresh_from_db()
        self.assertEqual(po.status, STATUS_PARTIALLY_INVOICED)
        self.assertEqual(po_item.qty_invoiced, Decimal("4.0000"))
        self.assertEqual(po_item.qty_pending, Decimal("6.0000"))

        create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-PO-2",
            lines=[{"inventory_item": self.item, "quantity": Decimal("6.0000"),
                    "rate": Decimal("120.00"), "order_item": po_item}],
            user=self.user,
        )
        po.refresh_from_db()
        po_item.refresh_from_db()
        # Auto-closed by the invoice that finished it, not by anybody saying so.
        self.assertEqual(po.status, STATUS_FULLY_INVOICED)
        self.assertEqual(po_item.qty_pending, Decimal("0.0000"))

    def test_invoice_cannot_run_past_what_was_ordered(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier, purchase_date=timezone.localdate(),
            status=STATUS_SUBMITTED, created_by=self.user, updated_by=self.user,
        )
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=po, inventory_item=self.item, quantity=Decimal("5.0000"),
            rate=Decimal("100.00"), unit_rate=Decimal("100.0000"), uom=self.uom,
            descr=self.item.item_name, created_by=self.user, updated_by=self.user,
        )
        with self.assertRaises(ValidationError):
            create_purchase_invoice(
                supplier=self.supplier, supplier_invoice_num="INV-OVER",
                lines=[{"inventory_item": self.item, "quantity": Decimal("6.0000"),
                        "rate": Decimal("100.00"), "order_item": po_item}],
                user=self.user,
            )

    def test_same_supplier_invoice_number_is_refused_twice(self):
        """The supplier's own number is what catches one invoice entered twice."""
        for _ in range(1):
            create_purchase_invoice(
                supplier=self.supplier, supplier_invoice_num="DUP-1",
                lines=[{"inventory_item": self.item, "quantity": Decimal("1.0000"),
                        "rate": Decimal("100.00")}],
                user=self.user,
            )
        with self.assertRaises(ValidationError):
            create_purchase_invoice(
                supplier=self.supplier, supplier_invoice_num="DUP-1",
                lines=[{"inventory_item": self.item, "quantity": Decimal("1.0000"),
                        "rate": Decimal("100.00")}],
                user=self.user,
            )

    def test_direct_invoice_posts_a_balanced_voucher(self):
        """Goods, freight and tax in; one payable out; the two sides agree."""
        from django.db.models import Sum

        from apps.finance.models import AccountVoucher

        invoice = create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="GL-1",
            lines=[{"inventory_item": self.item, "quantity": Decimal("10.0000"),
                    "rate": Decimal("100.00")}],
            freight_amount=Decimal("500.00"),
            tax_amount=Decimal("170.00"),
            discount_amount=Decimal("50.00"),
            user=self.user,
        )
        self.assertIsNone(invoice.purchase_order)
        self.assertEqual(invoice.total_amount, Decimal("1620.00"))

        voucher = AccountVoucher.objects.get(source_ref=f"inv_purchase_invoices:{invoice.pk}")
        totals = voucher.lines.aggregate(debit=Sum("debit_amount"), credit=Sum("credit_amount"))
        self.assertEqual(totals["debit"], totals["credit"])
        self.assertEqual(totals["credit"], invoice.total_amount)
        # The invoice names the voucher it posted, so it reads on its own.
        self.assertEqual(invoice.journal_ref, voucher.voucher_no)
