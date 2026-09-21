# UI Audit — 2026-09-21 (before)

Scope: every template rendering `{% component "table/board" %}` (50) plus every form template. Columns: Tiles = status tiles rendered (mixin auto via `filter_fields["status"]`, or `tiles` slot); Sort = `sort_header.html` in template (`+mixin` = view has `SortableListMixin`); Footer = `table_footer.html`; Cols = column picker (`browser` = generic localStorage picker, `server` = `ColumnSet`); Status = how the status column renders; Actions = row actions present; Detail = detail page exists; ds = `default_sort`; q = `search_fields`.

Reference pair: **Suppliers** (full) vs **Customers** (generic `simple_list`).

## MASTER lists

| Screen | Template / View | Title source | add_label | search_placeholder | Tiles | Sort | Footer | Cols | Status | Actions | Detail | ds / q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Suppliers | inventory/supplier_list · SupplierListView | ctx `title` | Supplier | Search suppliers | Y (slot: Suppliers/Bought/Payable) | Y +mixin | Y | browser | switch | view, edit, ledger | Y | added / name,code,email,tel1 |
| Customers | inventory/simple_list · CustomerListView | ctx `title` | (default "New") | (default "Search") | Y (mixin) | N | N | browser | switch + default switch | edit | N | – / customer_name,customer_code,customer_cell_no |
| UOM Conversions | inventory/simple_list · UOMConversionListView | ctx `title` | (default) | (default) | Y (mixin) | N | N | browser | switch | edit | N | – / uom_from__title,uom_to__title |
| Items | inventory/item_list · ItemListView | ctx `title` | Item | Search items | Y (mixin) | N | N | browser | switch | edit | N | – / item_name,code,item_bar_code,stock__* |
| Item Categories | inventory/class_list · InventoryClassListView | ctx | – | – | N (two-pane `split`, no board) | N | N | N | – | inline | pane | – / title,class_code |
| Units of Measure | inventory/uom_list · UOMListView | ctx | – | – | N (two-pane `split`, no board) | N | N | N | – | inline | pane | – / title,code |
| Products | products/product_list · ProductListView | ctx `title` | Product | Search products | Y (mixin) | N | N | server | switch | edit, ledger | N | – / name,complete_code,quick_code |
| Godowns | godowns/godown_list · GodownListView | ctx `title` | Godown | Search godowns | Y (mixin) | N | N | browser | badge + toggle | view, edit | Y | – / code,name,location,incharge |
| Employees | hr/employee_list · EmployeeListView | literal "Team Directory" | Employee | Search employees | Y (mixin) | N | N | browser | badge | view, edit, **delete** | Y | – / full_name,cnic,email,contact,department,designation |
| Organizations | organizations/organization_list | literal | Organization | Search organizations | Y (mixin) | N | N | browser | badge | edit, **delete** | N | – / title,code,parent__title |
| Branches | organizations/branch_list | literal | Branch | Search branches | Y (mixin) | N | N | browser | badge | edit, **delete** | N | – / title,code,phone,email,organization,city |
| Roles | access_control/role_list | literal | Role | Search roles | Y (mixin) | N | N | browser | badge | edit, **delete** | N | – / title |
| Permissions | access_control/permission_list | literal | Permission | Search permissions | Y (mixin) | N | N | browser | badge | edit, **delete** | N | – / title,code |
| User Assignments | access_control/user_assignment_list | literal | Assignment | Search assignments | Y (mixin) | N | N | browser | badge | edit, **delete** | N | – / user__*,role,organization,branch |
| Configuration masters (all slugs) | configurations/master_list · MasterListView | `master_config.label` | Record | (default) | Y (mixin) | N | N | browser | badge | edit, **delete** | N | – / title,code |
| Chart of Accounts | finance/account_configuration_list | literal "Account Configuration" | Account | (default) | Y (mixin) | N | N | browser | badge | edit, ledger | N | – / title,code,account_no |
| Fiscal Years | finance/fiscal_year_list | literal | Fiscal Year | (default) | Y (mixin) | N | N | browser | switch/badge | edit (+expand periods) | N | – / title,code |
| Salary Items | payroll/employee_salary_list | literal | Salary Item | (default) | N | N | Y | browser | none | edit, **delete** | N | – / employee__full_name,allowance_deduction__title |

No user list screen exists (only User Assignments).

## DOCUMENT lists

| Screen | Template / View | Title | add_label | Tiles | Sort | Footer | Cols | Status | Actions | Detail | ds / q |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Purchase Orders (reference) | inventory/purchase_order_list | literal | Purchase Order | Y (slot) | Y +mixin | Y | server | badge (custom pill) | view, edit, print, raise/cancel/close | Y | purchase_date |
| Purchase Invoices | inventory/purchase_invoice_list | literal | Purchase Invoice | Y (slot) | Y +mixin | Y | server | badge | view, reverse | Y | invoice_date |
| Purchase Returns | inventory/purchase_return_list | literal | Return | Y (slot) | Y +mixin | N | server | text | view, print, post | Y | return_date |
| Sales Orders | inventory/sales_order_list | literal | Sales Order | Y (mixin) | Y +mixin | Y | browser | text | close only | N | order_date |
| Sale Invoices | inventory/sale_invoice_list | literal | Sale Invoice | Y (slot) | Y +mixin | Y | browser | text | view, print | Y | sale_date |
| POS Sales | inventory/pos_list · POSListView (plain View) | none | none | N | N | N | browser | text | view, print | Y | – |
| POS Returns | inventory/pos_return_list | none | none | N | N | N | browser | text | view, print | Y | – / return_num,transaction_id,sale_num |
| Account Vouchers | finance/account_voucher_list | ctx `list_title` | ctx | Y (slot) | N | Y | browser | text | view, edit, print | Y | – / voucher_no,account_no,remarks |
| Grinding | production/grinding_list | ctx `title` | Grinding | N | N | N | browser | text | view, edit, print | Y | – / voucher_no,issue_area,wheat_item |
| Conversions | production/conversion_list | ctx `title` | Conversion | N | N | N | browser | text | view, edit | Y | – / voucher_no,source_product |
| Payroll Runs | payroll/payroll_list | literal | Payroll | Y (mixin) | N | Y | browser | badge | edit, **delete** | N | – / employee__full_name,cnic |
| Manual Transactions | inventory/manual_transaction | none | – | N | N | N | browser | switch | print, delete (draft lines) | N | – |
| Product Rate Update | products/rate_update | ctx | – | N | N | N | browser | – | inline form | N | – |
| Product Opening Balances | products/opening_balances | ctx | – | N | N | N | browser | – | inline form | N | – |
| Product Links (account / bardana) | products/link_grid | ctx | – | N | N | N | browser | – | inline form | N | – |

## REPORT boards

| Screen | Template / View | Title | Tiles | Sort | Footer | Cols | Detail links | q |
|---|---|---|---|---|---|---|---|---|
| Account Ledger | finance/account_ledger | literal | Y (slot) | N | N | browser | Y | – |
| Daybook | finance/daybook | literal | Y (slot) | N | N | browser | Y | – |
| Trial Balance | finance/trial_balance | literal | N | N | N | browser | Y | – |
| Inventory Valuation | finance/inventory_valuation | none | N | N | Y | browser | ledger | – |
| Item Ledger | inventory/ledger_list | literal | N (book tiles via ctx) | N | N | browser | N | dynamic |
| Customer Ledger | inventory/customer_ledger_list | literal | N | N | N | browser | N | transaction_no,customer_* |
| Purchase Orders Report | inventory/purchase_report | literal | Y (mixin) | N | N | browser | Y | purchase_num,supplier,quot_num |
| Pending Orders | inventory/pending_orders_report | literal | Y (slot) | N | Y | browser | Y | purchase_num,supplier,quot_num |
| Daily Grinding | production/report_daily_grinding | ctx | N | N | N | browser | Y | – |
| Production Summary | production/report_production_summary | ctx | N | N | N | browser | N | – |
| Yield Trend | production/report_yield_trend | ctx | Y (slot) | N | N | browser | N | – |
| Party Bardana | products/party_bardana_list | ctx | Y (slot) | Y +mixin | Y | browser | N | party__name,bardana_item |

## Boards embedded in detail / dashboard pages

supplier_detail, employee_detail (has **delete** button), purchase_order_detail, pos_detail, pos_return_detail, grinding_detail, conversion_detail, portal/dashboard. Dashboard: primary KPIs use bespoke `.kpi` markup; secondary row uses `components/table/tile.html`; `stat_card.html` unused.

## Forms

| Form | Pattern | Save & New | Save & Print | Embed | Notes |
|---|---|---|---|---|---|
| supplier_form | custom tabbed (tab_button + card + submit_bar) | Y | – | Y | 4 tabs: Address / Credit & Balance / Registration / Additional |
| item_form | custom tabbed | Y | – | Y | |
| simple_form (Customer, Class, UOM, UOM Conv, PO item, POS, POS Return) | form_grid cols=3 + submit_bar | N | – | Y | Customer `opening_balance` is form-only; no credit fields on model |
| product_form | crud_form (slot, custom head) | N | – | N | |
| godown_form, master_form, permission_form, user_assignment_form, fiscal_year_form, account_configuration_form, payroll_form | crud_form (auto grid) | N | – | N | cols 2/3 mixed, `narrow` mixed |
| employee_form, branch_form, organization_form, employee_salary_form | crud_form (slot) | N | – | N | organization_form `save_label="Save Organization"`; salary form has tiles inside |
| role_form | custom page_header + card + submit_bar | N | – | N | permission matrix |
| purchase_order_form | custom document | Y | Y | Y | reference document form |
| purchase_invoice_form, sale_invoice_form | custom document + submit_bar | N | Y | Y | |
| wheat_purchase_form | custom, JS-posted `<form>` (no method=post) | N | N | N | gate slip, keep layout (rule 21) |
| sales_order_form | custom, no submit_bar | N | N | N | |
| purchase_return_form | custom, own buttons (Save Draft / Save & Post) | N | N | N | |
| account_voucher_form | custom, own buttons | N | N | N | |
| grinding_form, conversion_form | custom + submit_bar floating | N | N | N | |
| item_import, period_close, finance/opening_balances, products opening_balances/rate_update/link_grid | custom tool forms | – | – | – | |

## Findings

1. Tiles: 24/50 boards; all mixin-driven masters have them, most documents/reports don't.
2. Sort headers: 7/50 (supplier, PO, PI, PR, SO, SI, party bardana). No master besides Suppliers.
3. Footer: 12/50. Column picker: all 50 (4 server, 46 browser).
4. Status: switch on Suppliers/Customers/Items/Products/UOM Conv/Fiscal Years; badge on Godowns/Employees/Orgs/Branches/Roles/Permissions/Assignments/Config masters/Accounts; raw text on every document list except PO/PI/Payroll.
5. **Delete** action on masters (rule 23 violation): Employees, Organizations, Branches, Roles, Permissions, User Assignments, Configuration masters, Salary Items; also Payroll Runs (document).
6. Detail pages only for Suppliers, Godowns, Employees among masters.
7. `add_label` / `search_placeholder` missing on simple_list (Customers, UOM Conv), master_list, account configuration, fiscal years, salary items, payroll runs, all document lists except PO/PI/PR/SI/SO ("Search" default).
8. Two form shells for masters: `crud_form` (11 forms) vs `simple_form` (7 views). `simple_form` is the only one supporting `embed`.
9. Save & New only on supplier, item, PO forms. Save & Print only on PO/PI/SI.
10. Item Categories and Units of Measure are two-pane custom screens, not boards.
11. Title source inconsistent: literal in template vs `title` ctx vs `page_title` vs `list_title` vs `master_config.label`.
12. Customer model lacks `opening_balance`, `opening_balance_date`, `credit_limit`, `credit_period_days` (Supplier has all four).

## Proposed contract deviations (for Phase 2 sign-off)

- Item Categories / Units of Measure: keep the two-pane screens (user-built, 300+ lines each) but give them the master detail/sort behaviour? Or convert to plain boards? Default: **keep two-pane, out of MASTER LIST contract, noted as exception**.
- Wheat purchase slip: exempt from DOCUMENT FORM contract (rule 21 mirrors paper slip).
- Purchase Return / Account Voucher forms use Save Draft / Save & Post instead of Save / Save & Print; contract should allow a `label`/`post_label` pair rather than force Save & Print.
- Salary Items: treat as MASTER (per-employee element) — needs status field? Model has none; propose badge-less, no tiles, no switch.
- Payroll Runs delete: document; replace delete with reverse/cancel? Needs business decision — flagged, not changed in Phase 3.

# After — 2026-09-21 (end of day)

`python manage.py ui_lint` clean with contract checks failing by default (sort header on every register, no raw status pill, no delete on a master, every form on crud_form / tabbed_form / submit_bar).

## MASTER lists

| Screen | Sort | Tiles | Detail | Status | Delete | Save & New |
|---|---|---|---|---|---|---|
| Suppliers, Customers | Y (+ColumnSet, export) | Count / money / balance | Y (dealings + ledger) | switch / badge | – | Y (tabbed_form) |
| Items | Y | mixin | Y (movements) | switch / badge | – | Y |
| Products | tree (exempt) | mixin | Y (movements) | switch / badge | – | Y |
| UOM Conversions | Y | mixin | Y | switch / badge | – | Y |
| Godowns | Y | mixin | Y (existing) | switch / badge | – | Y |
| Employees ("Employees", was "Team Directory") | Y | mixin | Y (existing) | switch / badge | removed | Y |
| Organizations, Branches | Y | mixin | Y | switch / badge | removed | Y |
| Roles, Permissions, User Assignments | Y | mixin | Y | switch / badge | removed | Y |
| Configuration masters (17) | Y | mixin | Y | switch / badge | removed | Y |
| Accounts, Fiscal Years | Y | mixin | Y | switch / badge | – | Y |
| Salary Items | Y | – (no status) | Y | – | removed from list | Y |
| Item Categories, UOM | two-pane (exempt) | – | pane | – | – | – |

Pages: `MASTER_NO_DELETE` now carries `view`; `MASTER` is an alias of it; `hr.employees` moved off `CRUD`. Seeded.

## DOCUMENT / REPORT boards

| Screen | Sort | Status | Notes |
|---|---|---|---|
| Purchase Orders, Purchase Invoices, Purchase Returns, Sales Orders, Sale Invoices | Y | status_badge | raw pills replaced |
| Account Vouchers | Y | status_badge | edit only while unposted |
| Payroll Runs | Y | badge | edit / delete only while pending (business decision open) |
| Grinding, Conversions | Y | – | |
| POS Returns | Y | – | |
| Purchase Orders Report, Pending Orders | Y (grouped) | status_badge | |
| Trial Balance, Inventory Valuation, Daily Grinding, Yield Trend, Production Summary | Y (`report_sort`) | – | |
| Account Ledger, Daybook, Item Ledger, Customer Ledger | exempt (chronological, running balance) | – | |
| POS entry (`pos_list.html`) | exempt (entry screen) | – | |

## Forms

| Form | Shell |
|---|---|
| Supplier, Customer | `components/forms/tabbed_form.html` |
| All other masters | `crud_form` cols=3 + Save & New (`SaveAndNewMixin`) |
| Class / UOM / UOM Conversion / PO item / POS / POS Return | `simple_form.html` → thin wrapper on `crud_form` (embed kept) |
| Purchase Return, Account Voucher | `submit_bar` component (Save Draft / Save & Post; Save / Save & Print) |
| Sales Order, Grinding, Conversion, PI, SI, PO | `submit_bar` (unchanged) |
| Wheat purchase slip | exempt (rule 21) |

## Dashboard

`components/ui/stat_card.html` only (tone, icon, hint, mask toggle); `.kpi*` CSS removed.

## Still open

- Column picker on the remaining boards is the browser one (per-browser); convert to `ColumnSet` when per-user memory is wanted.
- Payroll Runs delete on pending runs; Salary Items removal lives on the employee record.
- Detail pages for Payroll Runs / POS returns are unchanged (existing).
- `apps.finance.tests`: 3 pre-existing errors (`account_no` leaf account required) unrelated to this work.
