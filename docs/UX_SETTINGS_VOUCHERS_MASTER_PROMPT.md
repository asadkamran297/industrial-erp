# Master Prompt — General Settings, Five Vouchers, UI/UX Pass

Paste everything below the line into a fresh session.

---

## Role

You are the senior Django ERP engineer and an experienced UI/UX front-end engineer on `industrial_erp` (flour-mill ERP). Deliver the owner's change list below. Read `CLAUDE.md`, `docs/UI_SYSTEM.md`, `docs/DATABASE_RULES.md` first and obey them; where this prompt and `CLAUDE.md` disagree, `CLAUDE.md` wins.

## Owner's list (2026-10-06, decisions already taken)

1. **Products list** (`/products/`, `templates/products/product_list.html`) — make the listing better.
2. **Top header** — remove the **Sale** and **Voucher** quick buttons from the portal top bar (`templates/layouts/portal.html`, the two `button.html` includes next to the favourites bar).
3. **Purchases numbering "start from 0"** — the **starting number of every document series is a General Settings value**, editable by the admin (e.g. purchase invoices can start at `PI-000000`).
4. **Vouchers** — five separate entries, each its own sidebar item and its own form: **Cash Payment, Cash Receipt, Bank Payment, Bank Receipt, Journal Voucher**. Cash vs bank is fixed by the entry, never picked inside the form.
5. **Voucher form** (`/finance/vouchers/new/?voucher_type=PV`) — rebuild to a current, polished UI/UX. Behaviour stays correct; the look is what changes.
6. **General Settings = the software's master control** — **feature on/off switches**. Example given by the owner: if tax is off, nothing about tax appears on the PO (or anywhere else).
7. **Software general look** — a UI/UX pass across the app as an experienced front-end engineer would do it.
8. **Items** (`/inventory/items/`) — remove/hide **Services**.

Out of scope: "live chat Namecheap hosting with existing domain 1 year" is a hosting/purchase task for the owner, not code.

## What exists today (verified 2026-10-06 — re-verify before building)

| Piece | Where | State |
|---|---|---|
| Settings | `apps/core/models.py::SystemSetting` (singleton via `get_solo()`, in context as `system_setting`) | Branding, colours, theme, helpline, wheat WHT and brokerage rates. Edited only through Django Admin. No feature switches, no numbering. |
| Numbering | `apps/inventory/services.py::next_purchase_order_number`, `next_sale_invoice_number`, `next_sales_order_number`, `next_purchase_return_number`, `next_purchase_invoice_number`; models allocate in `save()` from `seq_num` (e.g. `PurchaseInvoice.save()` → `PI-{seq_num:06d}`); finance `services.next_voucher_number()` uses `FIN_VOUCHER_PREFIX_MAP` + `FIN_MONEY_MODE_SUFFIX` | Every series starts at 1, hard-coded. |
| Vouchers | `finance.AccountVoucher` (`voucher_type` PV/RV/JV/CN/SV/PU, `settlement_mode`, `account_no` header account), form `templates/finance/account_voucher_form.html` (~860 lines), nav `apps/portal/constants.py` "Vouchers" group built from `FIN_VOUCHER_TYPE_PICKER_META` | Cash/bank is derived from the header account's role (`money_mode_for_account`). Contra (CN) is hidden from the picker. |
| Tax / discount / freight fields | `PurchaseOrder` / `PurchaseInvoice` / lines (`tax_amount`, `discount_amount`, `freight_amount`), sale documents, prints, list columns | Always shown. |
| Items | `inventory.InventoryItem` with `item_kind` product/service (`INVENTORY_KIND_PRODUCT`, `INVENTORY_KIND_SERVICE`); `templates/inventory/item_form.html` Product/Service radio | Services selectable everywhere. |
| UI system | `docs/UI_SYSTEM.md`, `static/src/components.css`, `templates/components/`, `python manage.py ui_lint` | Board pattern for lists, DOCUMENT FORM contract for documents. |

## Part A — General Settings screen (portal, not Admin)

- New portal screen **General Settings** under Setup (page in `apps/access_control/pages.py`, admin-only, then `python manage.py seed`). Django Admin is not the product UI.
- Tabs (reuse `components/ui/tabs.html`): **Features**, **Numbering**, **Company** (move the existing `SystemSetting` branding fields here), **Wheat** (existing WHT/brokerage rates).
- Save goes straight back with a success message. Labels only; no help text (CLAUDE.md 11–12).

### A1. Feature switches (the master control)

Add boolean fields to `SystemSetting` (one migration). Start with the switches below. Each is one constant key in `apps/core/constants.py` and one field.

| Switch | When OFF |
|---|---|
| Sales tax on purchases | PO / purchase invoice / purchase return: tax field, tax column, tax totals, Input Sales Tax lines on print — all hidden; saved value forced to 0. |
| Sales tax on sales | Same for sales order / sale invoice / sale return and their prints. |
| Discount on purchases | Discount fields/columns hidden, forced to 0. |
| Discount on sales | Same on sales. |
| Freight on purchase invoice | Freight field and "freight paid by mill" hidden, forced to 0. |
| Withholding tax on wheat | WHT field/rate hidden on the wheat slip; no WHT posting. |
| Brokerage on wheat | Brokerage fields hidden; no brokerage posting. |
| Services in items | Service kind hidden from item form, item list filter/tiles, pickers (owner item 8 = this switch OFF by default). |

Rules:
- **One door**: a single helper `apps/core/features.py::enabled(key) -> bool` (reads `SystemSetting.get_solo()`, cached per request) plus a template tag `{% if feature "purchase_tax" %}`. Never read the fields directly in templates or views.
- **Hidden means gone**: label, input, list column, column-picker entry, print line, totals row, export column. Forms drop the field; the service forces 0 so a hand-crafted POST cannot sneak a value in.
- **Old documents keep their figures**: a posted document that already carries tax still shows it on its detail/print (show a value only when non-zero). Never rewrite history (CLAUDE.md 23, 26).
- GL postings already skip zero lines (`_post_voucher` drops them); confirm and add a test per switch.
- Switching a feature back ON must restore every field with no data loss.

### A2. Document numbering

- New table **`core_document_series`** (model `DocumentSeries` in `apps.core`): `code` (unique, e.g. `purchase_invoice`), `label`, `prefix`, `start_number` (≥ 0), `padding`. Indexes per `docs/DATABASE_RULES.md` (unique `code`) in the creating migration; a data migration seeds one row per existing series with today's prefix, `start_number=1`, current padding.
- One service `apps/core/services.py::next_number(code)` → `prefix + str(max(last_seq + 1, start_number)).zfill(padding)`, where `last_seq` comes from that series' own table (unchanged per-series counters, CLAUDE.md 27). Lock with `select_for_update()` the same way the existing allocations do; `of=("self",)` if a nullable FK is joined (CLAUDE.md 28).
- Replace every hard-coded `f"PI-{...:06d}"` style allocation and every `next_*_number()` preview with `next_number()`. Vouchers too (keep the cash/bank suffix behaviour, now fixed per voucher entry — see Part B).
- Numbering tab: one row per series — label, prefix, start number, padding, a live preview of the next number. Lowering `start_number` below the last used number has no effect (numbers never repeat) — validate and refuse with a short message.
- Owner's case: `start_number = 0` must yield `PI-000000` for the first invoice on a fresh book.

## Part B — Five voucher entries

- Sidebar "Vouchers": **Cash Payment, Cash Receipt, Bank Payment, Bank Receipt, Journal Voucher**, plus the voucher list. Each opens `finance:account_voucher_create?kind=<cash_payment|cash_receipt|bank_payment|bank_receipt|journal>`. Keep `AccountVoucher.voucher_type` (PV/RV/JV); the entry fixes `voucher_type` + money mode, and the header account picker shows only Cash accounts (cash entries) or only Bank accounts (bank entries). No cash/bank toggle inside the form.
- Constants: `VOUCHER_ENTRIES` in `apps/core/constants.py` (key, label, voucher_type, money_mode, number series code). Nav built from it.
- Numbering: each entry its own series (`CP-`, `CR-`, `BP-`, `BR-`, `JV-` by default — editable in Numbering). Existing vouchers keep their numbers.
- List screen: tiles per entry (counted over the filtered set), filter by entry; detail and print titles say the entry name ("Cash Payment Voucher").
- Day Book (`report_selectors.day_book`) already sections by cash/bank; check that the new numbers show unchanged.
- Contra (bank ↔ cash) stays possible: a Bank Receipt whose line account is Cash, or a Cash Receipt from Bank — confirm with the owner before adding a sixth entry.

## Part C — Voucher form UI/UX rebuild

Target: an accountant enters a 10-line cash payment fast, by keyboard, on one screen, with zero doubt about totals.

- Follow DOCUMENT FORM (`docs/UI_SYSTEM.md`): number + date in the `page_header` `fields` slot, entry name as the title, header account picker with the **balance chip** (`party-balance.js`), Save straight to the list with a success message, no confirm modal (CLAUDE.md 22a). One page, no vertical scroll for ≤ 12 lines (memory: one-page forms).
- Lines grid (`components/forms/line_items.html`): Account (searchable), Party/Narration, Amount (money, `amount-format.js`), remove. Enter moves to the next cell, a new line appears on Enter in the last amount, Ctrl+S saves (`[data-save]`).
- Payment/receipt entries show one Amount column (the header account takes the other side automatically); Journal shows Debit and Credit columns with a live **difference** chip that turns the Save button off until it is zero.
- Totals panel: total, amount in words (`amount_in_words`), cheque no/date only on bank entries.
- Attachments, remarks, cheque fields: collapsed into a secondary row, not the main grid.
- Cut the 860-line template: move repeated markup into components; JS into `static/js/` (no inline script blocks beyond a data bootstrap). `ui_lint` clean, light-first + `.dark` rules (CLAUDE.md 18), no CDN.
- Keep every existing validation (`AccountVoucher.clean()`, line `clean()`); do not change posting.

## Part D — Products list and Items

- `/products/` — convert to the board pattern (CLAUDE.md 13): tiles by category (Raw / Packing / Finished) counted over the filtered set, filter bar (category, status, search), sortable table with code, name, specification, unit, unit weight, current rate, status pill, icon row actions, column picker, export, pagination. Tree indentation for group / sub-group / item if the current screen shows the hierarchy — keep that information. Check N+1 (rate lookup) with `select_related` / annotation.
- `/inventory/items/` — with "Services in items" OFF (default), the Service kind disappears from the item form radio, list filters/tiles and every item picker; existing service items stay readable (deactivate, never delete — CLAUDE.md 23).

## Part E — Top bar and general look

- Remove the Sale and Voucher buttons from the top bar. Favourites bar stays.
- General look pass, as an experienced UI/UX front-end engineer. Audit first, then change in the shared layer only (`static/src/app.css` tokens, `static/src/components.css`, `templates/components/`, `templates/layouts/portal.html`) so every screen improves at once. Write the audit as a short table (screen · issue · fix) in the report, not in the repo.
  - Spacing and density: one scale (`--gap-*`), consistent card padding, table row height, page-head height.
  - Typography: one heading scale, tabular numbers on every money/weight column, muted secondary text.
  - Sidebar: active state, group headers, collapsed mode icons, keyboard focus visible.
  - Forms: aligned labels, consistent control heights, date width (CLAUDE.md 17), clear required marker, error states.
  - Tables/boards: sticky header, zebra or hover, right-aligned numbers, empty states, consistent icon actions.
  - Colour: tokens only, contrast AA in light and dark; status pills from `--st-*`.
  - Motion: subtle (150 ms) on menus and modals only.
- Do not move fields on screens the owner already arranged (CLAUDE.md 21, e.g. wheat slip).

## Build order

1. Part E top-bar buttons + Part D items/services (smallest, visible).
2. Part A1 feature switches + General Settings screen (Features + Company + Wheat tabs).
3. Part A2 numbering table + `next_number()` + Numbering tab.
4. Part B five voucher entries.
5. Part C voucher form rebuild.
6. Part D products board.
7. Part E general look pass.

Stop and ask on: a sixth (contra) voucher entry; any switch beyond the table above; changing a posted document's number format.

## Tests

- Each feature switch: OFF hides the field on form, list, print and export; a POST carrying the hidden field still saves 0; a posted document with a non-zero value still shows it; GL voucher has no line for it.
- Numbering: `start_number=0` → first `PI-000000`; series are independent; lowering below the last number is refused; concurrent allocation never duplicates (two saves in one test with the lock).
- Vouchers: each of the five entries only offers its own header accounts, posts with the right `voucher_type`, takes its own series, shows in the right Day Book section.
- Products and items boards render with tiles, filters, export; item form hides Service when the switch is off.

## Gates after every step

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.core apps.finance apps.inventory.tests apps.products apps.portal
python manage.py ui_lint
npm run build:css   # after Tailwind/class changes
```

The owner tests screens personally (CLAUDE.md 32). No probe scripts against real data. Commit only when asked. Add the day's entry to `docs/WORKLOG.md`.

## Report back

Per step: files changed, what the owner will see, the UI audit table (Part E), open questions, gates output.
