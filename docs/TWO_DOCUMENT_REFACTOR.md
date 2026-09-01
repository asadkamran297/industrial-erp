# Two-document lifecycle refactor

Purchase and sales collapse to two documents each. The order is optional and
commits nothing to the books; the invoice is mandatory and is the only thing
that moves stock or posts to the ledger.

## Where the current design does not fit

Three facts about the code as it stands decide most of what follows.

1. **The invoice is not its own table.** A direct purchase is written today as
   `PurchaseOrder(is_direct=True)`, numbered `PI-000001` off a second counter,
   with `PurchaseBill` posting the money against it. So "invoice" is currently
   two rows in two tables, and an ordered purchase's invoice is only the bill.

2. **The general ledger *is* the voucher tables.** There is no other ledger:
   `AccountVoucher` and `AccountVoucherLine` are the entries, and the trial
   balance, the account statements and the fiscal-year close all read them.

3. **There is no sales order.** `POSMaster` is the sale invoice. Nothing
   upstream of it exists, so the sales half is new work, not a refactor.

## Two decisions taken, and why

**"No separate voucher document" is read as: no separate voucher *step*.**
The invoice still writes an `AccountVoucher` keyed
`source_ref = "inv_purchase_invoices:<pk>"`, automatically, at submit. What
goes is the manual purchase and sales voucher entry — those two types are
already hidden from the voucher screens by `FIN_VOUCHER_TYPE_HIDDEN`. Building
a second ledger table hanging off the invoice would mean rewriting the trial
balance, the account statements and the year-end close to read from two
places, and would leave a purchase posting that no account statement could
see. The posting metadata the spec asks to move onto the invoice — posting
date, journal ref, tax — is denormalised onto the invoice row instead, so the
invoice is readable without a join.

**`PurchaseInvoice` becomes its own model.** Both of today's shapes migrate
into it: the `PB-` bills and the `PI-` direct rows. `PurchaseOrder` goes back
to being only an order — `is_direct` is dropped. This is what makes "order
optional, invoice mandatory" true in the schema rather than by convention.

## Schema

### New: `inv_purchase_invoices` (`PurchaseInvoice`)

| Column | Notes |
|---|---|
| `invoice_num` | `PI-000001`, own counter, unique |
| `supplier` | FK, PROTECT |
| `purchase_order` | FK, **nullable** — the optional order |
| `supplier_invoice_num` | supplier's own number; unique per supplier while posted |
| `supplier_invoice_date`, `invoice_date`, `due_date` | |
| `goods_amount`, `discount_amount`, `freight_amount`, `tax_amount`, `total_amount` | |
| `paid_amount`, `balance_amount` | |
| `status` | draft / posted / reversed / cancelled |
| `posted_at`, `posted_by` | posting metadata, moved off the bill |
| `journal_ref` | the `AccountVoucher.voucher_no` this invoice posted |
| `legacy_bill_no` | read-only `PB-...` for audit; blank on new invoices |
| `reversal_of`, `reverse_reason`, `reversed_on` | reversal design unchanged |

Indexes: `(invoice_num)`, `(invoice_date)`, `(status, -invoice_date)`,
`(supplier, -invoice_date)`, `(purchase_order)`.

### New: `inv_purchase_invoice_items`

`invoice`, `purchase_order_item` (nullable), `inventory_item`, `seq_num`,
`descr`, `quantity`, `rate`, `uom`, `tax_perc`, `tax_amount`,
`discount_amount`, `amount`. Unique on `(invoice, seq_num)`.

### Changed: `PurchaseOrderItem`

`qty_ordered` and `qty_invoiced` replace the receipt-era counters.
`qty_pending` is a property, not a column — a stored copy of a subtraction is a
second source of truth that drifts.

Dropped from the line: `last_receive_qty`, `curr_receive_qty`,
`total_receive_qty`, `extra_qty`. `billed_qty` is renamed `qty_invoiced` and
`quantity` is renamed `qty_ordered`.

### Changed: `PurchaseOrder`

`is_direct` dropped. Statuses become
`draft -> submitted -> partially_invoiced -> fully_invoiced -> closed / cancelled`.
An order auto-closes to `fully_invoiced` when every line is fully invoiced;
manual close keeps the existing `close_reason`, `close_remarks` and
`closed_by` fields.

### Dropped entirely

`PurchaseBill`, `PurchaseBillItem`, `PurchaseOrderItemReceived` (the receipt
leg of the three-way match), `PurchaseMaster`, `PurchaseMasterReturn`, and the
GRN clearing account path. Purchase price variance goes with them: with no
receipt to match against there is no second figure to vary from, so freight
and discount land on the invoice total directly.

### Sales, mirrored

New `inv_sales_orders` and `inv_sales_order_items`, same status model and the
same ordered/invoiced split. `POSMaster` gains a nullable `sales_order` FK and
the same posting metadata columns. It keeps its table and its `SAL-` number
series, because every existing sale return and customer-ledger row points at
it; renaming it would be churn with no reader benefit.

## Migration plan

Five migrations, in order, each reversible.

1. **`0037_purchase_invoice_tables`** — create the two new tables with their
   indexes. Nothing reads them yet. Reverse: drop.

2. **`0038_migrate_bills_to_invoices`** — data migration, `RunPython` with a
   real reverse.
   - Every `PurchaseBill` becomes a `PurchaseInvoice`: totals copied,
     `legacy_bill_no = bill.bill_num`, `purchase_order` kept, `journal_ref`
     read off the voucher whose `source_ref` is `inv_purchase_bills:<pk>`,
     `posted_at = bill.created_at`.
   - Every `PurchaseOrder(is_direct=True)` with no bill becomes a
     `PurchaseInvoice` with `purchase_order = None`.
   - Each `AccountVoucher.source_ref` is rewritten from
     `inv_purchase_bills:<pk>` to `inv_purchase_invoices:<new pk>`. **No
     voucher line is created, edited or deleted** — that is the whole reason
     ledger totals cannot move.
   - Reverse recreates the bills from the invoices and puts the `source_ref`
     back.

3. **`0039_purchase_order_lifecycle`** — rename the line quantity columns, add
   the new statuses, and map the old values: `raised` to `submitted`,
   `partial_received` to `partially_invoiced`, `fully_received` to
   `fully_invoiced`, `closed_short` to `closed`.

4. **`0040_sales_order_tables`** — create the sales order tables and add
   `sales_order` plus the posting columns to `POSMaster`.

5. **`0041_drop_bill_and_receipt_tables`** — drop `PurchaseBill`,
   `PurchaseBillItem`, `PurchaseOrderItemReceived`, `PurchaseMaster`,
   `PurchaseMasterReturn`, and `PurchaseOrder.is_direct`. Last, so every
   earlier step can still be reversed against live tables.

The spec asks for archive-and-soft-delete rather than a drop. Soft-deleting
44 rows in a table nothing reads keeps a dead model, its admin, its forms and
its 27 view references alive forever, and the next agent has to work out
whether they matter. The audit need it protects is met by `legacy_bill_no` on
the invoice plus the untouched voucher, both of which survive the drop. The
bills are dumped to `deploy/backups/purchase_bills.json` by the command below
before step 5 runs.

### Reconciliation report

`python manage.py verify_ledger_totals --before` writes a JSON snapshot of
total debits, total credits, per-account balances and the voucher count. Run
it again with `--after` and it diffs the two and exits non-zero on any
difference. Run either side of migration 2; that is the proof the ledger is
unchanged.

## UI flows

### New Purchase Invoice

One screen, branching on the supplier and nothing else.

1. Pick supplier.
2. The screen asks `purchases/po-options/` for that supplier's open orders.
3. **Open orders exist** — the order picker opens and a selection is required.
   Lines are pulled from the chosen orders with quantity, rate and tax
   defaulted from the order and editable. Quantity is capped at `qty_pending`.
4. **No open orders** — the line grid opens empty for manual entry.
5. Submit posts stock, the item ledger and the voucher in one transaction, and
   advances each source order's status.

Several orders on one invoice is now allowed; the old one-order-per-bill rule
went with the bill.

Dropped from the invoice list: the Bill column and the "No bill posted" KPI
tile. Dropped from the detail: the "No bill posted against this purchase"
panel and the "No bill" pill.

### New Sales Invoice

The same screen the other way round: pick customer, open sales orders are
offered and optional, and submitting posts stock out and the voucher.

## Files changed

### Phase 1 - schema and data (done)

| File | What |
|---|---|
| `apps/core/constants.py` | new lifecycle statuses, order/invoice status lists, `INV_ORDER_OPEN_STATUSES` |
| `apps/inventory/models.py` | `PurchaseInvoice`, `PurchaseInvoiceLine`; `qty_invoiced`/`qty_ordered`/`qty_pending`/`invoiced_status()` on the order and its lines; order default status now draft |
| `apps/inventory/migrations/0037_purchase_invoice_tables.py` | the two new tables and their indexes |
| `apps/inventory/migrations/0038_migrate_bills_to_invoices.py` | bills and direct orders into invoices, vouchers repointed, reversible |
| `apps/inventory/migrations/0039_purchase_order_lifecycle.py` | `billed_qty` renamed, statuses remapped, reversible |
| `apps/inventory/services.py` | order-line callers moved to `qty_invoiced` |
| `apps/inventory/purchase_board.py` | same |
| `apps/finance/management/commands/verify_ledger_totals.py` | new: the reconciliation report |

`qty_ordered` is a property over `quantity`, not a column rename. The name is
shared with three other models across 36 call sites, and `quantity` on a
purchase *order* line already means ordered; a second stored copy of the same
number is a second thing that can be wrong.

Run against the local book: ledger unchanged either side of migration 2 --
debit and credit both 222,296,806.00, 244 vouchers, 588 lines, 106 accounts.
94 invoices carried across, every one with its `journal_ref`.

### Phase 2 - services and screens (done)

| File | What |
|---|---|
| `apps/inventory/services.py` | `create_purchase_invoice` replacing `create_purchase_bill` and `create_direct_purchase`; `open_order_lines`, `supplier_has_open_orders`, `next_purchase_invoice_number`, `duplicate_supplier_invoice_number`, `_refresh_order_invoiced_status`, `reverse_purchase_invoice`, `can_reverse_invoice` |
| `apps/finance/services.py` | `post_purchase_invoice_to_gl` |
| `apps/core/constants.py` | `GL_FREIGHT_PATH` |
| `apps/inventory/views.py` | invoice list, detail, create and reverse views rewritten onto `PurchaseInvoice` |
| `apps/inventory/urls.py` | `purchase_invoice_create`, `purchase_invoice_reverse` |
| `apps/inventory/purchase_board.py` | invoice column set |
| `templates/inventory/purchase_invoice_list.html` | Bill column to Order, "No bill posted" tile to Unpaid |
| `templates/inventory/purchase_invoice_detail.html` | bill panel, "No bill" pill and receipt-notes block removed; `legacy_bill_no` shown |
| `templates/inventory/purchase_invoice_form.html` | renamed from `direct_purchase_form.html` |

### Phase 3 - sales, cleanup and drops (done)

| File | What |
|---|---|
| `apps/inventory/models.py` | `SalesOrder`, `SalesOrderItem`; `sales_order`, `posted_at`, `posted_by`, `journal_ref` on `POSMaster`; `PurchaseBill`, `PurchaseBillItem`, `PurchaseOrderItemReceived` and `is_direct` removed |
| `apps/inventory/services.py` | `create_sales_order`, `submit_sales_order`, `close_sales_order`, `open_sales_order_lines`, `customer_has_open_orders`, `next_sales_order_number`, `_refresh_sales_order_status`; `create_direct_sale` takes an optional order line; purchase returns read `qty_invoiced` |
| `apps/inventory/views.py` | `SalesOrderListView`, `SalesOrderCreateView`, `SalesOrderCloseView`, `CustomerSalesOrderOptionsView`; the bill and goods-receipt views deleted |
| `apps/inventory/urls.py` | sales order routes in, bill and GRN routes out |
| `apps/inventory/purchase_board.py` | tabs are the invoicing lifecycle; receipt roll-up, `receipt_state` and `GRN_COLUMNS` gone |
| `apps/portal/constants.py` | Sales Orders in the menu |
| `apps/portal/views.py` | the dashboard's purchase trend reads invoices |
| `apps/inventory/tests.py` | rewritten onto the invoice; over-invoicing, duplicate number and voucher balance covered |
| `templates/inventory/sales_order_list.html`, `sales_order_form.html` | new |
| `apps/inventory/management/commands/archive_purchase_bills.py` | new: the pre-drop dump |
| migrations `0040`, `0041` | sales order tables; the drops |

Deleted: `grn_list.html`, `grn_detail.html`, `grn_print.html`,
`goods_receipt_form.html`, `purchase_bill_list.html`, `purchase_bill_form.html`,
`purchase_bill_detail.html`. About 1,750 lines of view and service code went
with them.

## What was kept, against the plan

**`PurchaseMaster` and `PurchaseMasterReturn` stay.** `PurchaseReturnMaster`
holds a PROTECT foreign key to `PurchaseMaster`, so dropping it would take
purchase returns down with it, and returns are outside this refactor.
`create_purchase_invoice` writes the `PurchaseMaster` row the bill used to
write, so an invoice can still be returned. They should go when the returns
module is next opened up.

**`qty_ordered` is a property, not a column.** See phase 1.

**The receipt columns on `PurchaseOrderItem`** -- `last_receive_qty`,
`curr_receive_qty`, `total_receive_qty`, `extra_qty` -- are still on the table.
Nothing reads or writes them any more. They are a one-line `RemoveField`
migration whenever somebody wants the columns back.

## Verification

Everything below was run against the local book, and the writes were rolled
back where they were probes.

```
manage.py check                        no issues
manage.py makemigrations --check       no changes detected
manage.py test apps.inventory.tests    8 tests, OK

verify_ledger_totals --after           unchanged across every migration
  debit 222,296,806.00 = credit 222,296,806.00, 244 vouchers, 588 lines, 106 accounts

19 screens rendered, 0 failures

purchase: order submitted -> partially_invoiced -> fully_invoiced (auto)
sales:    order submitted -> partially_invoiced -> fully_invoiced (auto)
guards:   over-invoice refused on both sides; duplicate supplier invoice number refused;
          typed lines refused for a supplier holding open orders
voucher:  goods 1,000 - discount 50 + freight 500 + tax 170 = 1,620, debits = credits
reversal: stock back out, order lines back to uninvoiced, mirror voucher posted
```

A clean rebuild was also run on a scratch database -- `migrate`, `seed`,
`seed_demo` from empty -- which is what caught `approve_purchase_order` still
writing the old `raised` status. The local book's data had hidden it.
