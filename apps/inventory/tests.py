from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.configurations.models import City
from apps.core.constants import STATUS_ACTIVE, STATUS_CREATED, STATUS_DRAFT, STATUS_SUBMITTED, STATUS_FULLY_INVOICED, STATUS_PARTIALLY_INVOICED

from .models import ItemLedger, Customer, InventoryClass, InventoryItem, POSDetail, POSMaster, POSReturnDetail, POSReturnMaster, PurchaseOrder, PurchaseOrderItem, PurchaseReturnDetail, PurchaseReturnMaster, UOM, Supplier, PurchaseInvoice
from .services import create_purchase_order, create_purchase_invoice, generate_transaction_id, post_purchase_return, post_sale, post_sale_return


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

        invoice = PurchaseInvoice.objects.get(purchase_order=po)
        purchase_return = PurchaseReturnMaster.objects.create(transaction_id=generate_transaction_id("PRT", PurchaseReturnMaster), purchase_invoice=invoice, return_date=timezone.localdate(), created_by=self.user, updated_by=self.user)
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

    def test_over_receipt_is_taken_in_and_reported(self):
        """More than was ordered is posted, and the excess is handed back.

        A supplier sending a little over is ordinary and the truck is already
        at the gate, so the entry must go through. What it must not do is go
        through quietly: the excess comes back on the invoice for the screen
        to say out loud.
        """
        po = PurchaseOrder.objects.create(
            supplier=self.supplier, purchase_date=timezone.localdate(),
            status=STATUS_SUBMITTED, created_by=self.user, updated_by=self.user,
        )
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=po, inventory_item=self.item, quantity=Decimal("5.0000"),
            rate=Decimal("100.00"), unit_rate=Decimal("100.0000"), uom=self.uom,
            descr=self.item.item_name, created_by=self.user, updated_by=self.user,
        )
        invoice = create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-OVER",
            lines=[{"inventory_item": self.item, "quantity": Decimal("6.0000"),
                    "rate": Decimal("100.00"), "order_item": po_item}],
            user=self.user,
        )
        po_item.refresh_from_db()
        self.assertEqual(po_item.qty_invoiced, Decimal("6.0000"))
        self.assertEqual(len(invoice.over_invoiced), 1)
        excess = invoice.over_invoiced[0]
        self.assertEqual(excess["excess"], Decimal("1.0000"))
        self.assertEqual(excess["ordered_balance"], Decimal("5.0000"))
        # Nothing is left owing on a line that was over-delivered.
        self.assertEqual(po_item.qty_pending, Decimal("0.0000"))

    def test_receiving_stock_averages_the_cost_it_does_not_replace_it(self):
        """A delivery mixes into the pile; it does not re-price what is there.

        100 at 100 plus 100 at 200 is 200 units at 150, not 200 at 200. The
        old behaviour restated every existing unit at the newest rate, and
        every cost of sales off that stock was wrong afterwards.
        """
        stock = self.item.stock
        stock.current_quantity = Decimal("100.0000")
        stock.current_price = Decimal("100.00")
        stock.save()

        create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-AVG",
            lines=[{"inventory_item": self.item, "quantity": Decimal("100.0000"),
                    "rate": Decimal("200.00")}],
            user=self.user,
        )
        stock.refresh_from_db()
        self.assertEqual(stock.current_quantity, Decimal("200.0000"))
        self.assertEqual(stock.current_price, Decimal("150.00"))

    def test_an_order_can_commit_to_wheat_and_the_invoice_draws_it_down(self):
        """Wheat ordered ahead, then delivered in two trucks.

        The order moves nothing. Each invoice takes what actually arrived off
        the order line, and the order finds its own status from what is left.
        """
        from apps.core.constants import PRD_LEVEL_ITEM, PRD_SPEC_RAW_ITEM, PRD_UNIT_KG
        from apps.products.models import ProductNode

        group = ProductNode.objects.create(
            level=1, code_segment="92", name="Probe Raw Two", complete_code="92-000-000",
            created_by=self.user, updated_by=self.user,
        )
        sub = ProductNode.objects.create(
            parent=group, level=2, code_segment="01", name="Probe Wheat Group Two",
            created_by=self.user, updated_by=self.user,
        )
        wheat = ProductNode.objects.create(
            parent=sub, level=PRD_LEVEL_ITEM, code_segment="001", name="Probe Wheat Two",
            specification=PRD_SPEC_RAW_ITEM, unit=PRD_UNIT_KG, unit_weight=Decimal("1"),
            created_by=self.user, updated_by=self.user,
        )

        order, _net = create_purchase_order(
            supplier=self.supplier, quot_num="", quot_date=None,
            order_date=timezone.localdate(),
            lines=[{"product": wheat, "quantity": Decimal("40000"), "rate": Decimal("100")}],
            status=STATUS_SUBMITTED, user=self.user,
        )
        line = order.items.get()
        self.assertTrue(line.is_product_line)
        self.assertIsNone(line.inventory_item_id)

        # A commitment this size is over the buyer's own limit, so it lands as
        # a draft. Released here directly: who may approve is its own rule with
        # its own test, and what is under test here is the draw-down.
        if order.status == STATUS_DRAFT:
            order.status = STATUS_SUBMITTED
            order.save(update_fields=["status"])

        create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-W1",
            lines=[{"product": wheat, "order_item": line,
                    "selected_weight": "15000", "katla": "20", "rate_per_mund": "4000"}],
            tax_amount=Decimal("0"), user=self.user,
        )
        line.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(line.qty_invoiced, Decimal("14980.0000"))
        self.assertEqual(order.status, STATUS_PARTIALLY_INVOICED)

        second = create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-W2",
            lines=[{"product": wheat, "order_item": line,
                    "selected_weight": "25200", "rate_per_mund": "4000"}],
            tax_amount=Decimal("0"), user=self.user,
        )
        line.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(line.qty_invoiced, Decimal("40180.0000"))
        self.assertEqual(order.status, STATUS_FULLY_INVOICED)
        # 180 over the 25,020 that was left. Taken in, and reported.
        self.assertEqual(second.over_invoiced[0]["excess"], Decimal("180.0000"))

    def test_party_bardana_is_counted_in_but_not_bought(self):
        """The party's sacks reach the ledger and nothing reaches the bill."""
        from django.db.models import Sum

        from apps.core.constants import (
            INV_BARDANA_MILL, INV_BARDANA_PARTY, PRD_LEVEL_ITEM, PRD_SPEC_RAW_PACKING, PRD_UNIT_KG,
        )
        from apps.products.models import ProductLedger, ProductNode

        group = ProductNode.objects.create(
            level=1, code_segment="93", name="Probe Packing", complete_code="93-000-000",
            created_by=self.user, updated_by=self.user,
        )
        sub = ProductNode.objects.create(
            parent=group, level=2, code_segment="01", name="Probe Bags",
            created_by=self.user, updated_by=self.user,
        )
        bag = ProductNode.objects.create(
            parent=sub, level=PRD_LEVEL_ITEM, code_segment="001", name="Probe Bag",
            specification=PRD_SPEC_RAW_PACKING, unit=PRD_UNIT_KG, unit_weight=Decimal("1"),
            created_by=self.user, updated_by=self.user,
        )

        invoice = create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-BAGS",
            lines=[
                {"product": bag, "quantity": "300", "rate": "90",
                 "bardana_ownership": INV_BARDANA_MILL},
                {"product": bag, "quantity": "50", "rate": "90",
                 "bardana_ownership": INV_BARDANA_PARTY},
            ],
            tax_amount=Decimal("0"), user=self.user,
        )
        mill_line = invoice.items.get(bardana_ownership=INV_BARDANA_MILL)
        party_line = invoice.items.get(bardana_ownership=INV_BARDANA_PARTY)
        self.assertEqual(mill_line.amount, Decimal("27000.00"))
        self.assertEqual(party_line.amount, Decimal("0.00"))
        self.assertEqual(invoice.goods_amount, Decimal("27000.00"))
        # Both are held, so both are counted.
        self.assertEqual(
            ProductLedger.objects.filter(product=bag).aggregate(q=Sum("quantity"))["q"],
            Decimal("350.000"),
        )

    def test_weight_charges_leave_the_supplier_credited_net_of_withholding(self):
        """Brokerage is owed to the broker; withholding is kept back."""
        from apps.core.constants import PRD_LEVEL_ITEM, PRD_SPEC_RAW_ITEM, PRD_UNIT_KG
        from apps.products.models import ProductNode

        group = ProductNode.objects.create(
            level=1, code_segment="94", name="Probe Raw Three", complete_code="94-000-000",
            created_by=self.user, updated_by=self.user,
        )
        sub = ProductNode.objects.create(
            parent=group, level=2, code_segment="01", name="Probe Wheat Group Three",
            created_by=self.user, updated_by=self.user,
        )
        wheat = ProductNode.objects.create(
            parent=sub, level=PRD_LEVEL_ITEM, code_segment="001", name="Probe Wheat Three",
            specification=PRD_SPEC_RAW_ITEM, unit=PRD_UNIT_KG, unit_weight=Decimal("1"),
            created_by=self.user, updated_by=self.user,
        )

        invoice = create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-CHG",
            lines=[{"product": wheat, "selected_weight": "20000", "rate_per_mund": "4000"}],
            tax_amount=Decimal("0"),
            brokerage_rate_per_100kg=Decimal("15"),
            withholding_rate_per_40kg=Decimal("6"),
            user=self.user,
        )
        self.assertEqual(invoice.brokerage_amount, Decimal("3000.00"))
        self.assertEqual(invoice.withholding_amount, Decimal("3000.00"))
        self.assertEqual(invoice.total_amount, Decimal("2000000.00"))
        self.assertEqual(invoice.supplier_payable_amount, Decimal("1997000.00"))

        # The voucher must balance with the two extra legs on it.
        from apps.finance.models import AccountVoucher, AccountVoucherLine

        voucher = AccountVoucher.objects.get(source_ref=f"inv_purchase_invoices:{invoice.pk}")
        lines = AccountVoucherLine.objects.filter(voucher=voucher)
        debit = sum((row.debit_amount or Decimal("0")) for row in lines)
        credit = sum((row.credit_amount or Decimal("0")) for row in lines)
        self.assertEqual(debit, credit)

    def test_a_charge_with_no_weight_behind_it_is_refused(self):
        """Both charges are quoted per weight, so weightless is meaningless."""
        with self.assertRaises(ValidationError):
            create_purchase_invoice(
                supplier=self.supplier, supplier_invoice_num="INV-NOWEIGHT",
                lines=[{"inventory_item": self.item, "quantity": Decimal("1.0000"),
                        "rate": Decimal("100.00")}],
                brokerage_rate_per_100kg=Decimal("15"),
                user=self.user,
            )

    def test_wheat_line_is_priced_by_the_mound_and_posts_to_the_product_ledger(self):
        """The paid weight is what is bought, and it goes to the product ledger.

        Deductions come off the selected weight; the rest is priced per mound
        of 40 kg. Wheat never touches inventory stock -- grinding reads the
        product ledger, and two ledgers holding the same sack is how a mill
        ends up with two answers.
        """
        from django.db.models import Sum

        from apps.core.constants import PRD_LEVEL_ITEM, PRD_SPEC_RAW_ITEM, PRD_UNIT_KG
        from apps.products.models import ProductLedger, ProductNode

        group = ProductNode.objects.create(
            level=1, code_segment="91", name="Probe Raw", complete_code="91-000-000",
            created_by=self.user, updated_by=self.user,
        )
        sub = ProductNode.objects.create(
            parent=group, level=2, code_segment="01", name="Probe Wheat Group",
            created_by=self.user, updated_by=self.user,
        )
        wheat = ProductNode.objects.create(
            parent=sub, level=PRD_LEVEL_ITEM, code_segment="001", name="Probe Wheat",
            specification=PRD_SPEC_RAW_ITEM, unit=PRD_UNIT_KG, unit_weight=Decimal("1"),
            created_by=self.user, updated_by=self.user,
        )

        invoice = create_purchase_invoice(
            supplier=self.supplier, supplier_invoice_num="INV-WHEAT",
            lines=[{
                "product": wheat, "party_weight": "10100", "mill_weight": "10000",
                "selected_weight": "10000", "katla": "20", "khoot": "10",
                "moisture": "30", "sack_weight_deduction": "40",
                "rate_per_mund": "4000",
            }],
            tax_amount=Decimal("0"), user=self.user,
        )

        line = invoice.items.get()
        self.assertEqual(line.credit_weight, Decimal("9900.000"))
        self.assertEqual(line.amount, Decimal("990000.00"))
        self.assertEqual(line.rate, Decimal("100.00"))  # 4000 / 40
        self.assertIsNone(line.inventory_item_id)

        moved = ProductLedger.objects.filter(product=wheat).aggregate(q=Sum("quantity"))["q"]
        self.assertEqual(moved, Decimal("9900.000"))
        # The stores ledger knows nothing about it.
        self.assertFalse(ItemLedger.objects.filter(ref_no=invoice.invoice_num).exists())

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
