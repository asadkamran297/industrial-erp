# Work Log

One entry per working day. **Local** = changes in the repo/dev environment.
**Live** = what actually reached the production host. Newest entry on top.

---

## 2026-09-22

### Live

- Commit `0ca6540` (reporting suite) pulled and deployed via cPanel (deploy #23, exit 0): `inventory.0057` migration applied on live (was pending), 6 static files collected, 50 report permissions seeded (`reports.*` pages), app restarted. Smoke-checked logged in: one report per group + PNG export all 200.

### Local

- Reporting suite, groups H / I / J built in parallel (three agents, own app files only; nav + registry wired afterwards). Pages `reports.accounts`, `reports.hr`, `reports.setup` seeded; nav "Accounts Reports" (8 new + 7 existing), "HR Reports", "Setup Reports"; `apps/core/reports.py` now lists all 71 catalogue entries (`GROUP_SETUP` added).
  - H Accounts (`apps/finance/report_selectors.py`, `report_views.py`, `tests_reports.py`, 6 tests): Cash Book, Bank Book (cheque no/date, running balance), Party Ledger (voucher lines on the party account tagged by source, sacks column for wheat suppliers), Voucher Register by Type, Expense Analysis (expense leaf × fiscal month grid, ColumnSet built per request), Receivable / Payable Summary, Opening Balances (carried vs manual), Audit Trail (GL reversals, invoice/return reversals, edited + manual vouchers). Existing daybook / ledger / TB / IS / BS / CF / period close untouched (registered, in nav) — the "extend" items (drill-downs, monthly IS columns, previous-period BS column, direct-method CF, period-close blockers) are still open.
  - I HR / Payroll (`apps/payroll/report_selectors.py`, `report_views.py`, `tests_reports.py`, 7 tests; `templates/reports/salary_sheet_print.html`): Employee Register, Salary Sheet (month of period end, bank/cash, signature column), Payroll Summary (month rows, vs last month), Allowance / Deduction Breakdown. Caveat: `Payroll` snapshots only totals, so the item-wise breakdown applies current `EmployeeSalary` items to each payroll month.
  - J Setup (`apps/portal/report_selectors_setup.py`, `report_views_setup.py`, `tests_reports_setup.py`, 5 tests): Supplier / Customer Directory (as-of balances, over-limit tone), Product Master with Rates (current, since, previous, change), Chart of Accounts with balances (tree order, group roll-ups), User Access (user × role × organization, permission count, last login).
- Reporting suite, group F (Production): `apps/production/report_selectors.py` + `apps/production/report_views.py` replace the three old report views/templates (`ReportBase`, `report_daily_grinding.html`, `report_yield_trend.html`, `report_production_summary.html`, `_report_filters.html` removed; URLs `report_daily_grinding` / `report_yield_trend` / `report_production_summary` kept). Grinding Register, Daily Grinding (every calendar day, downtime flagged as a status pill), Yield Trend (week/month toggle, standard %, variance, 7-period moving average, best/worst day tiles), Product Output Mix (share of output, % of wheat vs `standard_yield_percent` target), Shortage / Refraction (standard shortage, beyond-standard kg, cost × weighted avg wheat purchase rate, threshold chip), Product Conversion Register, Production Cost per Bag (wheat cost ÷ output share + bardana at avg purchase rate + direct expenses from `ProductAccountLink` service/wage accounts), Production Summary (month/week/day, per-day kg, output by category). `tests_reports.py` (3 tests). `templates/reports/threshold.html` shared threshold-chip screen.
- Reporting suite, group G (Stock): `apps/inventory/selectors_stock.py` + `apps/inventory/report_views_stock.py`, page `reports.stock` (seeded), nav "Stock Reports". Mill Product Stock (product × godown, opening/in/out/closing, kg + mund, value at current rate, category tiles), Stores Stock (opening/in/out/closing from `ItemLedger` new−old, value, idle days, negative-stock tile/filter), Stock Ageing / Slow Moving (both books, 30/60/90 buckets, as-of), Stock Adjustment Register (`ManualTransaction`), Godown-wise Stock (wheat, products by category, empty bags, value; stores value tile), Wheat Stock in Days (30-day trend, delta vs 30 days ago; three queries total). Item Ledger and Stock Valuation stay on their existing screens (registered + in nav). `tests_reports_stock.py` (3 tests).
  - Not sourced: stores reorder level (no field on `InventoryItem`); stores stock has no godown dimension.

## 2026-09-21

### Local

- Reporting suite, group E (Bardana): `apps/products/report_selectors.py` + `apps/products/report_views.py`, page `reports.bardana` (seeded), nav "Bardana". Bardana Stock (Mill) (item × godown: opening, purchased, returned by party, issued to packing, returned to party, closing — `ProductLedger` packing items), Party Bardana Balances (as-of, received/returned/held/returnable due, ownership filter), Bardana Movement Register (both books: `PartyBardanaLedger` + mill `ProductLedger`, source/party/item filters), Packing Consumption (grinding line: output bags vs `pack_qty`, variance). `apps/products/tests_reports.py` (2 tests).
- Reporting suite, group D (Weighbridge): `apps/inventory/report_views_gate.py` (selectors appended to `selectors_purchase.py`), page `reports.weighbridge` (seeded), nav "Weighbridge". Weighbridge Register (party/mill gross-tare-net, difference kg/%, selected source, difference ≥ X filter), Vehicle-wise (trips, net kg/mund, avg difference, last visit), Weight Variance (tolerance default 10 kg, who selected which weight, cost impact = difference × rate/mund), Daily Gate Sheet (time order, portrait print, default Today). `tests_reports_gate.py` (2 tests).
  - Not sourced: there is no weighbridge document — every row is a wheat slip line; outbound (dispatch) weighments do not exist, so "Out" tiles read 0 by design; slip time is `posted_at`.
- Reporting suite, group C (Purchase): `apps/inventory/selectors_purchase.py` + `apps/inventory/report_views_purchase.py`, page `reports.purchase` (seeded), nav "Purchase Reports". Wheat Purchase Register (`reports/purchases/` now this screen; party/mill/selected weight, weight source, katla/impurities/moisture, credit kg + mund, rate/mund, freight payer, brokerage bearer, WHT, net payable), Purchase Summary (day/week/month, delta tiles), Arhti-wise Purchase (avg impurities/moisture %, sacks held from `PartyBardanaLedger`), Wheat Quality (threshold input, per-arhti averages table), Wheat Rate Trend (min/max/avg per period), Freight & Brokerage (mill vs supplier split), WHT Register (NTN, per-month tiles), Stores Purchase Register (against order / direct), Order Fulfilment (`reports/pending-orders/` now this screen; ordered/received/pending, age, overdue), Purchase Returns (`reports/purchase-returns/` now this screen), Supplier Payment Status (as-of, oldest unpaid, due in 7 days). `tests_reports_purchase.py` (5 tests). `col()` helper in `table_columns.py` derives export + rendering from `kind`; xlsx sheet title sanitised.
  - Not sourced: "weight source" is derived (selected == mill/party weight), not stored; supplier type is derived from invoiced lines; three-way match reduces to "against order / direct" (no receipt document exists).
- Reporting suite, group B (Sales): `apps/inventory/selectors.py` + `apps/inventory/report_views.py`, page `reports.sales` (seeded), nav "Sales Reports". Sales Register (`reports/sales/` now this screen, invoice-wise with product summary, bags/kg, pay mode, status, tiles incl. cash/credit filters), Sales Summary (`group=day|week|month`, returns and net-of-returns, delta tiles vs previous period), Party-wise Sales (received = receipt-voucher credits on the customer account, closing balance from the account), Product-wise Sales (category tiles, share %), Sale Rate History (billed vs `ProductRate` in force on the day, variance, "given away" tile), Sale Returns (`reports/sale-returns/` now this screen), POS Day Sheet (cash/card/online split by cashier, default Today). `apps/inventory/tests_reports.py` (7 tests).
  - Shared additions: `ReportView.filter_specs` (declarative select chips, summary line for print), `paginate_by=100`, `group_toggle`; column-driven generic screen (`Column.kind/link/link_key/total/places/tone_key`, `components/report/table.html` + `cell.html`, `reports/generic.html`) — a report with no bespoke layout needs no template; `|get_item` filter.
  - Not built / not sourced: Salesman / Broker Commission (13) — sale documents carry no broker or brokerage fields; invoice-vs-POS filter — `POSMaster.invoice_type` is never set; "avg days to pay" — receipts are not allocated to invoices; sale return "reason" and "restocked godown" — not on the return document.
- Reporting suite, group A (Owner pack) from `docs/REPORTING_MASTER_PROMPT.md`.
  - Shared: `apps/core/reporting.py` (`resolve_period` with presets today/yesterday/this & last week/this & last month/this year/fiscal/custom, `previous_period`, `group_by`, `mund`, `delta`, and the `ReportView` / `ReportExportView` / `ReportColumnsView` bases); `apps/core/reports.py` registry (key, label, module, reader, url_name, permission, group); `components/report/shell.html` + `period.html` + `as_of.html`; `reports/print.html` letterhead print (org, branch, title, period, filter line, totals row, printed-by footer; portrait/landscape per report); PNG export (`png` in `TableExportView.FORMATS`, Pillow, server-side, no CDN) and a PNG entry in every export menu; `Column.numeric`; tile `delta` (+`delta_label`) with `.tile-delta--up/down/flat`; `table/actions` gains `ledger_url`; `|mund` filter.
  - Reports (`apps/portal/selectors.py`, `apps/portal/report_views.py`, `/portal/reports/…`, page `reports.owner`, seeded): Daily Position (8 tiles, figure list, portrait one-pager print with tiles + production table), Month at a Glance (day-wise rows, running closing cash, MTD vs last-month-to-date delta tiles), Profitability by Product (COGS = weighted average of costed ledger receipts, list rate with `*` when none), Receivables Aging and Payables Aging (as-of balances from the party account + voucher lines, balance spread over documents newest-first, 0-30/31-60/61-90/90+, over-limit tile/filter, supplier type arhti/bardana/stores derived from invoiced lines).
  - Nav "Reports" section regrouped: Owner, Sales, Purchase, Production, Stock, Accounts (existing report URLs untouched). Queries per screen: daily 28, month 22, profit 5, receivables 9, payables 9. `apps/portal/tests.py` (8 tests, rolled-back fixture). `layouts/print.html` letterhead no longer errors when no organization/branch exists.
  - Not sourced from a ledger: per-product COGS (the sale voucher books one COGS total; per-product cost is the ledger's average inbound rate); aging buckets are an allocation, not per-invoice settlement (receipts are not linked to invoices).
- UI convergence phases 3.2–3.6: every master list on SortableListMixin + switch/badge + detail page (`apps/core/views.py`: `ToggleStatusView`, `MasterDetailView`, `SaveAndNewMixin`; `templates/core/master_detail.html`); delete actions removed from roles, permissions, assignments, organizations, branches, employees, configuration masters, salary items (toggle + detail routes instead; pages seeded, `MASTER` = `MASTER_NO_DELETE` + view); `crud_form` cols=3 + Save & New everywhere, `simple_form` a wrapper; document/report boards sort (`report_sort` for dict rows), raw status pills → `status_badge` (now takes `tone`/`title`); voucher + purchase return forms on `submit_bar` (new `save_id/save_name/save_value/save_attrs/print_id`); dashboard on `stat_card` (tone, mask toggle), `.kpi` CSS dropped; `ui_lint` contract checks fail by default (`--lenient`), plus raw-pill check. Lint clean, inventory tests OK; finance tests carry 3 pre-existing errors.
- Customers = Suppliers (UI convergence phase 3.1): Customer gains `opening_balance`, `opening_balance_date`, `credit_limit`, `credit_period_days` + `(status, customer_name)` index (0057); `sync_customer_opening_balance` mirrors the payable sync; shared `components/forms/tabbed_form.html` drives both party forms (Save & New, embed); `customer_list.html` / `customer_detail.html` mirror the supplier screens (tiles, sort, expand row, receivable ledger, footer); both lists on `ColumnSet` with server export (`*_list_columns`, `*_list_export`); suppliers/customers pages gain the `view` action (seeded). 21 queries per page on both lists.
- UI convergence phase 1+2: `docs/UI_AUDIT.md` (50 boards, all forms, findings, proposed exceptions); "Screen contracts" section + MASTER/DOCUMENT skeletons in `docs/UI_SYSTEM.md`; `ui_lint` gains contract warnings (board without sort_header, delete action on master list, form without crud_form/tabbed_form/submit_bar) and `--strict`. 42 warnings today, build still clean. No screens changed.
- `components/forms/crud_form.html` was never committed; ten form screens (products, godowns, fiscal year, masters, permissions…) 500'd. Created it. Product weights optional (blank → 0).
- Columns picker on every board: server `ColumnSet` now on Products too; all other boards get a generic browser-side picker (`data-column-menu` in `filter_bar.html`, `ui.js`), saved in localStorage, `data-default-off` on a `<th>` hides by default, `no_columns=True` opts out.
- Seed data rebuilt for the flour mill; the generic industrial set (steel/textile orgs, TVs, cement, 55 mixed suppliers, 46 inventory classes) is gone.
  - `seed`: one organization `ZFM` (Zafaran Flour Mills) with mill, head office and two sales depots; 30 suppliers split into wheat arhtis / bardana traders / stores vendors (`WHEAT_SUPPLIER_CODES` etc. in `apps/inventory/seeders/suppliers.py`); 18 stores classes (roller-mill spares, sieves, belts, lubricants, lab, fumigation, PPE); 65 stores items; 21 UOMs incl. `MUND`; product tree widened to 40 items (more Atta/Maida/Fine/Suji brands, bran 49 kg, refraction, dalia) with finish-bardana links for each. Bags live only on the product tree — no stores item duplicates a sack.
  - `seed` order now includes `finance` (chart of accounts via `seed_chart_of_accounts`) before `products`, so product account links get their expense accounts on a fresh database. The sample grinding run left `seed`; masters only.
  - `seed_demo`: 40 named customers (dealers, bakeries, tandoors, feed mills), mill staff by role (operators, helpers, store keeper, QC, gate), 50 wheat slips through `create_purchase_invoice` (weights, katla/moisture, mill/party/returnable sacks, freight, broker, WHT 0.60/40 kg, dates spread over 50 days), 25 bardana lots, 50 stores POs + invoices against them + 50 direct stores bills, 25 grinding runs `WG-0001..` through `save_grinding_voucher`, 50 vouchers. No demo sales: there is no product sale service yet.
- Mill products now sell on the same documents as stores items ("product & inventory union", screens only; ledgers stay separate per rule 25).
  - `SalesOrderItem`, `POSDetail`, `POSReturnDetail` gained a nullable `product` FK beside a now-nullable `inventory_item`, with check constraints `inv_so_line_one_item_kind`, `inv_pos_line_one_item_kind`, `inv_pos_ret_line_one_item_kind` (migration inventory 0056).
  - `create_sales_order`, `create_direct_sale`, `post_sale`, `post_sale_return` post product lines through `products.services.post_movement` (`sale` / `sale_return`), stock-checked against the product ledger, COGS from the current product rate. Fixed `create_sales_order` passing undefined `godown`/`broker` (NameError on every sales order since 97a895c).
  - Sale invoice, sales order and POS pickers list stores items and sellable mill products together; a product's picker id is `p:<pk>` (`line_item_of()` in views). Sales order unit select carries product units.
  - Item Ledger board has two books: Stores (`ItemLedger`) and Mill Products (`ProductLedger`, running opening/closing via window sum), `?book=mill`; filter bar carries `keep_params`. Print follows.
  - Item masters tabs gained "Mill Products" → `/products/`.
  - `seed_demo` now seeds 50 atta/bran sales through `create_direct_sale`; `ProductSaleTests` (5) added.
- Local Postgres flushed and reseeded (dump kept in the session scratchpad before the flush).
- Rules 22a (CLAUDE.md) + DOCUMENT FORM contract (`docs/UI_SYSTEM.md`) now record the three document-form conventions above so they are applied unasked: number/date in the page header, balance chip on every party picker, direct save to list.
- Document number + date sit in the page header (`page_header` `fields` slot, `form_id` on the date) on every document form, as the purchase order/invoice already did: wheat purchase slip, sale invoice, sales order, purchase return, grinding, conversion (production `date` widgets carry `form=`, the loop skips `date`).
- Payroll form: Month + Year in the page header (`payroll_form.html` off `crud_form`; body grid keeps employee, salary figures, status). Sweep of all `*_form.html` found no other form with document number/date fields left in the body; masters (fiscal year, godown, product, party opening-balance date) are not documents and stay on `crud_form`/`tabbed_form`.
- Nav: `NavigationItem.hidden` flag (skipped in `build_navigation_item`); Departments, Designations, Job Types, Cities, Banks, Allowances & Deductions hidden from Master Data for the flour-mill demo. Routes, pages and permissions unchanged.
- Wheat purchase slip saves straight from the Save button (no "This entry will create" confirm modal) and returns to the purchase invoice list with a success message; `.wp-modal/.wp-eff/.wp-bill` CSS dropped.
- Party balance chip on every entry form (wheat purchase, purchase order, purchase return, sale invoice, sales order; purchase invoice had it): `static/js/party-balance.js` reads `data-balance` off the picked option and paints `.bal-chip` on load and on change (`data-balance-chip`/`-owed`/`-credit` on the select). `suppliers_with_balance()` / `customers_with_balance()` in `apps/inventory/views.py`; `finance.services._party_balances` reads the ledger account's closing via `account_balances` (the old `supplier_payable_balances` summed voucher lines only, dropping the account's opening balance, and the PO form showed the master's opening figure instead of the ledger). `supplier_balance` optional-field toggle removed from the purchase invoice layout; the wheat slip's separate Balance box became the chip under Sender.

### Live

- Nothing deployed. On next deploy: `migrate products` + `seed` (masters only; seeders are idempotent). Do not run `seed_demo` on live.

### Open

- Purchase report "item" filter lists stores items only; product lines are on the invoice but not filterable there yet.
- Stock check on a product sale is against today's stock, not stock as of the sale date.
- `seed_roles` reports permission assignments as "created" on every run (cosmetic, pre-existing).

---

## 2026-09-20

### Local

- Wheat purchase slip (`/inventory/purchases/wheat/new/`) restyled to one flat card: header row, `<hr>` rules between Bardana Detail / Stock Details / Total Bill / Carrier, plain labels, no "(auto)" tags, no hints. Title now "Purchase Invoice".
- Selected Wgt. is a Party / Mill select; the numeric weight is derived from the chosen net and posted as before. Weight gap, Bag Ded. and sender balance shown as figures.
- `wp-*` CSS trimmed: `wp-row`, `wp-rule`, `wp-title`; `wp-grid`/`c2..c12`/`wp-legend`/`wp-hint` removed; controls at `--control-h`; slip date box 10.5rem.
- `/inventory/purchases/new/` now opens the slip (`purchase_invoice_create`); stores invoice moved to `/purchases/stores/new/` (`stores_purchase_create`), "Stores Invoice" button on the list. Old wheat URL redirects.
- Party bardana custody: `products.PartyBardanaLedger` (migration products 0003, also adds `reversal` ledger source). Party/returnable sacks post there per supplier; mill sacks stay in `ProductLedger`. Board at `/products/party-bardana/` (page `products.party_bardana`, seeded).
- `reverse_purchase_invoice` now mirrors product lines (mill and party ledgers); it used to crash on product-only invoices.
- Slip Bag Type defaults from Raw Bardana Linking.
- Purchase Invoices board: columns picker wired (`purchase_invoice_columns`); Vehicle, Godown, Status, Supplier ref toggleable.

### Live

- Nothing deployed. Live needs `migrate products` + `seed` on deploy.

### Open

- "Restore previous icon" and "stock figure after item title" deferred by user.

---

## 2026-09-16

### Local

- One design system across all screens:
  - Tokens only in `static/src/app.css`; `static/src/components.css` rewritten as plain CSS on tokens.
  - Icon set (`apps/core/icons.py`, `{% icon %}`), `{% component %}`/`{% slot %}`, `{% capture %}`, `|control` filter.
  - New components: `forms/control`, `money`, `weight`, `section`, `form_errors`, `crud_form`, `line_items`, `totals_*`, `amount_words`, `switch`; `ui/icon_button`, `page_header`, `modal`, `tab_button`, `detail_*`, `frame_modal`; `table/board`, `tiles`, `tile`, `filter_bar`, `actions`, `table_footer`, `empty_row`, `expand_toggle`, `lines_row`.
  - Removed `board_theme`, `search_filters`, `field_wrapper`, `hero_stat`, `print_base` (now `layouts/print.html`).
  - `static/js/ui.js`: Enter-to-next, Ctrl+S, `/` search, modals, confirm dialog, table export.
  - Board mixin now supplies status tiles, `filters_active`, `base_query`; salary, payroll and sales-order lists show page totals.
- Migrated every screen: inventory, finance, products, production, godowns, hr, payroll, organizations, access control, configurations, dashboard, login.
- Every `<select>` is now searchable (`searchable-select.js`; opt out with `data-native`); list opens fixed to the viewport, new rows picked up automatically.
- Purchase invoice: totals panel moved to the right column with compact rows; narration and amount card on the left.
- Fixed on the way: PI list print linked to the PO print; PO detail status mapping; supplier credit-limit clear; SO form comma parsing; COA save button; PI detail unclosed section; organization list mojibake.
- Guard rails: `docs/UI_SYSTEM.md`, `python manage.py ui_lint` (clean), `docs/UI_AUDIT.md` statuses.

### Live

- Nothing deployed.

### Open

- Browser pass over all migrated screens.
- Not committed.

---

## 2026-09-15

### Local

- Purchase Orders board opens on the "All" tab by default.
- Purchase Returns rebuilt:
  - Board at `/inventory/purchase-returns/`: tiles, tabs, filters, column menu, export, row actions.
  - New form at `/inventory/purchase-returns/new/`: supplier → invoice picker → returnable lines, Save Draft / Save & Post.
  - Detail page with Post / Reverse.
- Services:
  - `create_purchase_return`, `purchase_return_lines`, `reverse_purchase_return`.
  - `PR-` number allocated in services under a lock, no longer in `save()`.
  - Posting re-validates per invoice line; reversal mirrors the ItemLedger and GL entries.
- Migration `inventory.0055_purchase_return_rebuild`:
  - line → invoice line FK, unit, posted_at, reversal fields, nullable `return_num`
  - indexes `(supplier, -return_date)` and `(purchase_invoice, -return_date)`
- Retired the old quick-create and add-item views; their URL names redirect.

### Live

- Nothing deployed.

### Open

- Adjusted amount on purchase returns is not captured; the net equals the gross.
- Wheat/bardana returns are still not supported (product ledger).

---

## 2026-09-01

### Local

- `config/settings/base.py`: `STATIC_ROOT` now reads from the environment, so a
  host can collect static outside the git checkout (commit `284b595`).
- `config/settings/production.py`: `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
  now merge hosts from the environment; custom domains no longer need a code
  edit.
- `config/__init__.py`: installs PyMySQL as MySQLdb when present (shared hosting
  has no libmysqlclient).
- Added `passenger_wsgi.py`, `requirements-cpanel.txt`, `.cpanel.yml`,
  `scripts/cpanel_deploy.sh`, `.env.cpanel.example`.
- Added `docs/DEPLOYMENT.md`, `deploy/cpanel.config.example`,
  `deploy/cpanel/passenger_wsgi.py`, `deploy/cpanel/htaccess`.
- Restored a dev `.env` after it was accidentally overwritten with production
  values; the original `SECRET_KEY` was not recoverable and is a placeholder.

### Live — https://flourorbit.com (first deployment)

- Repo cloned to `/home/flouruge/industrial_erp` (branch `master`).
- MySQL `flouruge_erp` created with its own user and full privileges.
- Python 3.12 app created via the CloudLinux selector at
  `/home/flouruge/erp_app`; dependencies installed into its virtualenv.
- All migrations applied to MySQL.
- Seeded **users, roles and permissions only**: 182 permissions, 507 roles.
  Superuser `admin` created. No demo or master data.
- `collectstatic` → `/home/flouruge/staticfiles` (153 files).
- Verified: `/` → 302 `/portal/`, login page 200, real login POST → `/portal/`
  200, `/static/dist/app.css` 200.

### Live — TLS

- Let's Encrypt certificate issued for `flourorbit.com` and
  `www.flourorbit.com` (HTTP-01, challenge files pushed through the cPanel API
  with a patched `acme-tiny`) and installed via `SSL/install_ssl`.
  Valid until **2026-11-29**; renewal steps in `docs/DEPLOYMENT.md`.
- `config/settings/production.py`: `SECURE_SSL_REDIRECT` now comes from the
  environment (commit `a98459e`); HTTP 301s to HTTPS on the live host.
- Verified without `-k`: `https://flourorbit.com/` 302 → `/portal/`,
  `https://flourorbit.com/accounts/login/` 200, `https://www.flourorbit.com/`
  200, `http://` → 301 to `https://`.

### Local + Live — database indexing

- `BaseModel` now indexes `created_at` and `deleted_at`, so all 58 existing
  tables and every future one are covered (commit `6e11d9e`). `deleted_at` was
  in the WHERE clause of every `ActiveManager` query with nothing indexing it.
- Composite indexes added for the real access paths: `(status, -date)` on
  purchase orders, bills, sales and returns; `(supplier, -date)`,
  `(customer, -date)`, `(inventory_item, -transaction_date)` for per-party
  history; `(ref_table, ref_id)` on the item ledger; `(account_no,
  -voucher_date)`, `(voucher_type, -voucher_date)`, `(posted, -voucher_date)`
  on vouchers and voucher lines.
- Verified with `EXPLAIN QUERY PLAN`: voucher list, account ledger, stock card
  and purchase order list all seek an index instead of scanning.
- Migrations applied to the dev database and to live MySQL.
- Standing rule written into `docs/DATABASE_RULES.md` and `CLAUDE.md`: every new
  table ships its indexes in the migration that creates it.

### Live — PostgreSQL attempt, and auto-deploy fixed

- Tried moving live to PostgreSQL (the project targets it). The host has the
  cPanel feature and the service runs, but it is **PostgreSQL 10.23** and
  Django 5.2 requires 14+. Reverted; live stays on MySQL. Recorded in
  `docs/DEPLOYMENT.md` so it is not retried blindly.
- Found why every deploy looked successful but changed nothing: `manage.py`
  defaults to `config.settings.local`, whose `USE_SQLITE` default is `True`, so
  deploy migrations and seeds were going into `db.sqlite3` inside the checkout
  while the served app used the real database. The deploy script now exports
  `DJANGO_SETTINGS_MODULE=config.settings.production` and logs a `TARGET DB:`
  line (commits `4c6889a`, `cdad035`).
- Auto-deploy is **working now**. `deployable` was `0` because the checkout was
  never clean: `staticfiles/` was tracked and rewritten by `collectstatic`, and
  the deploy script touched `tmp/restart.txt` inside the checkout. Both are now
  untracked/ignored and the restart trigger moved to the app root (commits
  `60e8df6`, `42830dc`, `4f01df3`).
- A full `VersionControl/update` + `VersionControlDeployment/create` cycle now
  runs pip install, migrate, collectstatic, seed and restart, and reports
  `TARGET DB: django.db.backends.mysql`.
- The empty `flouruge_erp` and `flouruge_pgtest` PostgreSQL databases and the
  `flouruge_app` role left by the attempt were dropped; the account now has no
  PostgreSQL objects. Live MySQL and the site were verified unaffected.

### Local — demo seeder

- `seed_demo` rewritten to build 50 of each: customers, employees with salary
  components and payroll, purchase orders, supplier bills, sales and vouchers
  (commit `4a65f74`). Purchase and sale documents go through the real services,
  so stock, the item ledger and the general ledger move as they do on screen.
- Verified on a fresh database: 452 records on the first run, 0 on the second
  (idempotent), GL lines balance, no negative stock, stock on hand equals
  receipts less sales.
- Two things the seeder had to work around, both by design in the app: the
  first sale to a customer rewrites `customer_code` to their chart-of-accounts
  code, so demo customers key on their email instead; and a voucher must be
  headed by a cash/bank leaf of the chart, with both sides on its lines.
- `SEED_DEMO=1` in `.cpanel.yml` makes a deploy seed the demo book (commit
  `46dc3cd`), and also seeds the master data the demo hangs off, since live
  otherwise carries only users, roles and permissions (commit `b670af5`). The
  flag was set for the seeding deploys and taken back out again (`fed06b8`).
- A demo voucher soft-deleted from the screens still holds its unique
  `voucher_no`, so reseeding collided with it; the seeder now looks vouchers up
  through `all_objects` and clears the soft-delete (commit `e11aa8d`).

### Live — demo book loaded

- Seeded on live over two deploys. The IP block on the management ports cleared
  on its own after about an hour; port 443 was never affected.
- Live now carries 57 suppliers, 147 items, 52 customers, 50 employees and 51
  purchase orders, with their bills, sales, item-ledger and general-ledger
  entries behind them. Verified by logging into the live site and reading the
  list screens.
- The purchase and sale documents were built while live still had only two
  items and two suppliers, so the flow data is concentrated on those. The full
  catalogue is loaded now; reseeding with a higher `--count` would spread new
  documents across it if more variety is wanted.

### Open
- cPanel password was shared in plaintext during setup; rotate it.
- Local dev Postgres has a stray `admin` superuser from a probe run; delete with
  `python manage.py shell -c "from django.contrib.auth import get_user_model as g; g().objects.filter(username='admin').delete()"`.
