# Master Prompt — Purchase Module Review (Hamza Afzal, 19 Oct 2026)

Paste everything below the line into a fresh session.

---

## Role

You are the senior Django ERP engineer and an experienced UI/UX front-end engineer on `industrial_erp` (flour-mill ERP, live at flourorbit.com). Deliver the reviewer's nine points below. Read `CLAUDE.md`, `docs/UI_SYSTEM.md`, `docs/DATABASE_RULES.md`, `docs/TWO_DOCUMENT_REFACTOR.md` first and obey them; where this prompt and `CLAUDE.md` disagree, `CLAUDE.md` wins — except rule 25a, which Point 6 deliberately replaces (update `CLAUDE.md` 25a and `docs/UI_SYSTEM.md` when Point 6 ships).

Global points (2, 3, 7.2) apply to the whole software, not just the screen named.

## What exists today (verified 2026-10-19 — re-verify before building)

| Piece | Where | State |
|---|---|---|
| Purchase menu | `apps/portal/constants.py` `NAV_ITEMS` → "Purchase" | Order: Purchase Invoices, Purchase Orders, Purchase Returns, Suppliers, Pending Orders, Purchase Report. |
| Wheat invoice | `/inventory/purchases/new/` → `WheatPurchaseEntryView`, `templates/inventory/wheat_purchase_form.html`; service in `apps/inventory/services.py` (~L1230–1530) | The only invoice in the menu. Wheat + bardana lines, mill product stock via `apps.products.services.post_movement`. |
| General (stores) invoice | `/inventory/purchases/stores/new/` → `PurchaseInvoiceCreateView`, `templates/inventory/purchase_invoice_form.html` | Exists, posts `InventoryItem` lines through `ItemLedger`, but has no menu entry. |
| Invoice list | `/inventory/purchases/` → `PurchaseInvoiceListView` | One list for both kinds. |
| Purchase Order | `/inventory/purchase-orders/new/`, `templates/inventory/purchase_order_form.html` | Has a "Wheat & Bardana" section and Sub Total / Discount / Tax / Total box (`components/forms/totals_row.html`). |
| Purchase Return | `/inventory/purchase-returns/new/`, `templates/inventory/purchase_return_form.html`; `purchase_return_lines()` in `apps/inventory/services.py` (~L799) | Reads only `InventoryItem` lines of kind product → wheat/bardana invoices show "Lines = 0", greyed "Wheat / bardana" pill, cannot be picked (rule 25a). No mill-product return movement exists. |
| Pending Orders | URLs `inventory:report_pending_orders` (+ `_export`, `_columns`) in `apps/inventory/urls.py` L150–152 → `rvp.OrderFulfilmentView`; old view in `apps/inventory/views.py` ~L2832 + `templates/inventory/pending_orders_report.html`; nav entry in `apps/portal/constants.py` L39 **and** "Order Fulfilment" reports entry L129; `apps/core/reports.py` L58; test list in `apps/inventory/tests_reports_purchase.py` L111 | Two screens/names share the route. |
| Suppliers list | `/inventory/suppliers/`, `templates/inventory/supplier_list.html` | Long figures in tiles, uneven action icons. |
| Wheat Purchase Register | `/inventory/reports/purchases/` → `WheatRegisterView` + `WHEAT_REGISTER_COLUMNS` in `apps/inventory/report_views_purchase.py`; rows from `_slip_row()` / `wheat_register()` in `apps/inventory/selectors_purchase.py` | Tile "Slips"; "Sack Ded." column exists but `default=False`; Brokerage hidden by default; blank cells for `None` weights. |
| Net payable | `PurchaseInvoice.supplier_payable_amount` (`apps/inventory/models.py` ~L539) | `total − WHT − freight (if paid by mill) − brokerage (if borne by supplier)`; `total = all line amounts (wheat + bardana) + freight (if not paid by mill) − discount + tax`. Register "Goods" shows only the wheat line amount → bardana amount, tax, discount, brokerage are the "hidden adjustments". |
| WHT | `SystemSetting.wheat_withholding_rate_per_40kg`; service: `withholding = credit_weight / 40 × rate` | Rs 0.60 / 40 kg = Rs 0.015 / kg, which is what the reviewer saw. Calculation matches the setting; the **rate/base** is the question (see Decisions). |

## Decisions to confirm with the owner before building (ask in one message, then proceed)

1. **WHT basis (Point 9.7)** — keep per-40kg weight rate, or switch to % of goods value (e.g. sec. 153/236 style)? If %, add `wheat_withholding_percent` + a basis switch in settings; old invoices keep their snapshotted rate/amount (rule 26).
2. **Wheat/bardana returns (Point 6.2)** — confirm scope: return reverses wheat via a new `ProductLedger` `purchase_return` movement, reverses party/mill bardana custody, and debits the supplier. Return Qty for wheat in kg (3 decimals) at the invoice's snapshotted rate per kg.
3. **Direct return without invoice (Point 6.4)** — rate source: last purchase rate from that supplier, or typed by user?
4. **Button size (Point 2)** — 11–12px is the reviewer's figure; confirm against `docs/UI_SYSTEM.md` button tokens before changing the token globally.

## Build order

Do High-priority correctness first, cosmetic last. Commit nothing until the owner asks.

### Step 1 — Point 8: remove Pending Orders completely
- Delete nav entries (`apps/portal/constants.py` L39 and the "Order Fulfilment" reports entry L129), `apps/core/reports.py` L58, URLs L150–152, `OrderFulfilmentView`/`Export`/`Columns`, the old view in `views.py` ~L2832, `templates/inventory/pending_orders_report.html`, its selector(s), its test entry, any dashboard tile/search/notification/page action in `apps/access_control/pages.py`.
- Keep one redirect: `reports/pending-orders/` → `inventory:purchase_order_board` (permanent). Nothing else may reference the old name: `grep -rn "pending_orders\|pending-orders\|Order Fulfilment\|OrderFulfilment"` must return only the redirect.
- PO board must cover it: status filter Pending / Partially Received / Completed / Cancelled (constants in `apps/core/constants.py`), columns Ordered Qty, Received Qty, Balance Qty (computed in the selector with annotations, no N+1).
- `python manage.py seed` after `pages.py` changes.

### Step 2 — Point 4: simplify Purchase Order
- Remove the "Wheat & Bardana" section (+ Line panel) and the Sub Total / Discount / Tax / Total box from `purchase_order_form.html`, its JS and the PO form-settings toggles.
- Keep header (number + date in `page_header` `fields` slot), item lines (Item, Qty, Unit, Price/Unit, Amount), Narration, Amount box with amount in words.
- Service: PO saves with discount/tax forced to 0; Save Draft works with only these fields. Old POs keep their stored figures on detail/print (show only when non-zero).
- PO stays commitment-only: no ledger, no stock (rule 24).

### Step 3 — Point 5: two invoice formats
- Rename current `/inventory/purchases/new/` screen title/menu to **Wheat Purchase Invoice**; layout and logic unchanged (rule 21).
- **General Purchase Invoice** = the existing stores form at `/inventory/purchases/stores/new/`: bring it to the DOCUMENT FORM contract — Supplier (balance chip), number + date in header, Godown, rows (Item, Qty, Unit, Rate, Amount), Narration, Discount, Tax, Total, amount in words. Do not build a second one.
- PO link optional on both: "Pick order" pulls items + rates; invoicing reduces PO balance (existing receipt tracking — verify it updates for both formats). Direct invoice without PO must work.
- List: two menu entries — **Wheat Purchase Invoices** and **General Purchase Invoices** — same `PurchaseInvoiceListView` filtered by kind (a `?kind=` or two URL names), each with its own "New" button.
- Posting: wheat → `apps.products.services.post_movement` only (rule 25); general → `ItemLedger`. Both post supplier ledger/GL. Add/extend tests in `apps.inventory.tests` for: general invoice without PO; general invoice from PO reduces PO balance.

### Step 4 — Point 6: Purchase Return fix and redesign
- `purchase_return_lines()` returns wheat and bardana lines too (kind tag on each line); remove the greyed "Wheat / bardana" block. Picker click must select the invoice and load lines: Item, Unit, Invoiced, Returned, Returnable, Return Qty, Rate, Amount. Fix the click handler (reproduce in the browser console first; it currently does nothing even on stores invoices — verify).
- Validation in the service: Returnable = Invoiced − posted returns; Return Qty ≤ Returnable; weights 3 dp, money 2 dp, `Decimal` + quantize before `full_clean()`.
- Posting: stores lines → `ItemLedger` out; wheat/bardana → new `ProductLedger` movement `purchase_return` via `post_movement` (add the movement constant in `apps/core/constants.py`), bardana custody reversed for whoever owned it; supplier debit note (GL). Reversal of a posted return by mirror entries only (rule 23).
- Optional direct return (no invoice) per Decision 3.
- Layout: wider supplier field (shared component, Step 7), full-width grid with no horizontal scroll at 1366px, clear totals panel. Save & Post enabled once a line has qty.
- Invoice detail shows updated Returned qty.
- Update `CLAUDE.md` 25a, `docs/UI_SYSTEM.md`, and the memory note `purchase-return-stores-only`.
- Tests: wheat return reduces product stock + supplier balance; return qty > returnable rejected.

### Step 5 — Point 9: Wheat Purchase Register
- Tile "Slips" → "Invoices" (also in `PURCHASE_SUMMARY_COLUMNS` and other purchase reports that say "Slips").
- Rename column "Sack Ded." → **Bardana Ded. (kg)** and make it `default=True`, so Mill/Party Wt − Katla − Impurities − Moisture − Bardana Ded. = Credit Kg on every row.
- Add visible columns for every Net Payable adjustment: **Bardana Amount** (bardana line amounts on the invoice), **Discount**, **Tax**, Brokerage (Supplier-borne) default on, Freight with payer. Row identity: Goods + Bardana Amount − Discount + Tax ± Freight − Brokerage(supplier) − WHT = Net Payable. Add a selector-level assertion in tests for seeded data.
- Rows are per wheat line but header amounts (freight, WHT, payable) come from the invoice — if an invoice has two wheat lines, header amounts must not be double-counted in totals. Verify and fix.
- WHT per Decision 1.
- Numeric cells show `0` / `0.000`, never blank.
- Filter bar wraps to two rows (or collapsible "Filters" panel) — do it in the shared reporting template so every report gets it.
- Freeze first columns (Slip, Date, Arhti) via sticky columns in the shared table component; Columns chooser already exists — confirm it lists every column.

### Step 6 — Point 7: Suppliers list + KPI cards everywhere
- Shared money-short filter in `apps/core` (e.g. `{{ value|money_m }}` → `Rs 433.25 M`; below 1 M show full figure), exact value in `title=`. Apply in `components/table/tile.html` (or the tile helper `_tile()`) so every board and report tile gets it at once.
- Tile labels never truncate: full labels ("Total Purchases", "Total Payable"), equal widths, one row, wrap on narrow screens.
- Row actions on every supplier row, fixed order: View, Edit, Ledger, Active/Inactive — each with a distinct icon and `title=` tooltip. Remove the duplicate ledger/document icon (or give Statement its own icon). Same on Customers (customers = suppliers parity).

### Step 7 — Points 2 & 3: buttons and field sizes (global)
- Buttons: one size/weight token in `static/src/components.css` used by `components/buttons/*`; short labels everywhere — Save, Save & New, Save Draft, Post, Print, Cancel, Back. Grep templates for long button text and shorten. `npm run build:css`.
- Fields: one Supplier/party picker component with one width class; one date width (≥ 11.5rem, rule 17) used by PO, both invoices, Return. Remove per-screen overrides (e.g. the larger Order Date box on PO).

### Step 8 — Point 1: menu order (last, after routes exist)
Purchase → Purchase Orders, Wheat Purchase Invoices, General Purchase Invoices, Purchase Returns, Suppliers, Purchase Report. Run `python manage.py seed`.

## Gates (every step)

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py ui_lint
python manage.py test apps.inventory.tests
npm run build:css   # when Tailwind classes changed
```

Migrations when models change, with indexes in the same migration. No probe scripts against real data (rule 33). Owner tests screens personally.

## Hand-back

1. Fill the reviewer's summary table (Status, Developer Remarks) for points 1–9 and give it back as text the owner can paste into the review file.
2. One dated entry in `docs/WORKLOG.md` (Local / Live / Open).
3. Live deploy only when the owner asks — follow `docs/DEPLOYMENT.md`; DB dump first (Points 5, 6, 9 change posting).
