from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE, STATUS_CREATED, STATUS_FULLY_RECEIVED, STATUS_PARTIAL_RECEIVED

from .models import Customer, InventoryClass, InventoryItem, POSDetail, POSMaster, POSReturnDetail, POSReturnMaster, PurchaseOrder, PurchaseOrderItem, PurchaseReturnDetail, PurchaseReturnMaster, UOM, Supplier, PurchaseMaster
from .services import generate_transaction_id, post_purchase_return, post_sale, post_sale_return, receive_purchase_order_item


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
        receive_purchase_order_item(purchase_order_item=po_item, quantity=Decimal("10.0000"), extra_qty=Decimal("0.0000"), retail_price=Decimal("120.00"), receive_date=timezone.localdate(), invoice_num="INV-1", invoice_date=timezone.localdate(), rv_number="RV-1", remarks="Receive test", user=self.user)
        self.item.stock.refresh_from_db()
        self.assertEqual(self.item.stock.current_quantity, Decimal("10.0000"))
        self.assertEqual(self.item.stock.current_price, Decimal("120.00"))
        self.assertEqual(self.item.stock.last_price, Decimal("100.00"))

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
    def test_purchase_order_status_moves_from_created_to_partial_to_fully_received(self):
        po = PurchaseOrder.objects.create(supplier=self.supplier, purchase_date=timezone.localdate(), created_by=self.user, updated_by=self.user)
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=po,
            inventory_item=self.item,
            quantity=Decimal("10.0000"),
            rate=Decimal("100.00"),
            unit_rate=Decimal("100.0000"),
            uom=self.uom,
            descr=self.item.item_name,
            created_by=self.user,
            updated_by=self.user,
        )

        self.assertEqual(po.status, STATUS_CREATED)

        receive_purchase_order_item(
            purchase_order_item=po_item,
            quantity=Decimal("4.0000"),
            extra_qty=Decimal("0.0000"),
            retail_price=Decimal("120.00"),
            receive_date=timezone.localdate(),
            invoice_num="INV-PO-1",
            invoice_date=timezone.localdate(),
            rv_number="RV-PO-1",
            remarks="Partial receive",
            user=self.user,
        )
        po.refresh_from_db()
        self.assertEqual(po.status, STATUS_PARTIAL_RECEIVED)

        receive_purchase_order_item(
            purchase_order_item=po_item,
            quantity=Decimal("6.0000"),
            extra_qty=Decimal("0.0000"),
            retail_price=Decimal("120.00"),
            receive_date=timezone.localdate(),
            invoice_num="INV-PO-2",
            invoice_date=timezone.localdate(),
            rv_number="RV-PO-2",
            remarks="Full receive",
            user=self.user,
        )
        po.refresh_from_db()
        self.assertEqual(po.status, STATUS_FULLY_RECEIVED)

