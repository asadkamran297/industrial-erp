# Master Prompt — Flour Mill Reporting Suite

Copy everything below the line into a fresh session. It is written for the engineering agent; it assumes the agent has read `CLAUDE.md`, `docs/UI_SYSTEM.md` and `docs/DATABASE_RULES.md` first.

---

## Role

You are the senior Django ERP engineer on `industrial_erp`, a flour-mill ERP (Zafaran Flour Mills demo). Build the complete reporting suite described here, module by module, in the order given. Reports are the product the owner will judge in the demo, so every report must be correct to the paisa and kilo, fast, and printable.

## Ground rules (non-negotiable)

1. Read `CLAUDE.md`, `docs/UI_SYSTEM.md` (REPORT contract, board pattern), `docs/DATABASE_RULES.md`, `docs/TWO_DOCUMENT_REFACTOR.md` before writing code.
2. One report = one selector in `apps/<module>/selectors.py` (returns rows + totals as plain dicts/Decimals), one view in `views.py`, one template extending the shared report shell, one entry in `apps/access_control/pages.py` (then `python manage.py seed`), one nav entry in `apps/portal/constants.py`.
3. Every report ships with: filter bar (date range with presets Today / This Week / This Month / This Year / Custom, plus the party/product/godown/status filters that apply), tiles counted over the filtered set, sortable table (`sort_header`), page-total and grand-total footer, pagination where rows exceed 100, and export in **PDF, Excel, CSV, Image (PNG)** through `apps/core/table_export.py` (`ColumnSet`, `FORMATS`). Add `png` to `FORMATS` once, rendered from the print template, and reuse it everywhere.
4. Print/PDF layout: mill letterhead (organization name, branch, address), report title, filter summary line, period, page N of M, printed-by and timestamp footer. Landscape for wide tables. A4.
5. Money: `Decimal`, two places. Weight: three places, kg, with a mund column (40 kg) wherever weight is shown to the owner. Never route weight through `amount-format.js`.
6. All figures come from the ledgers and posted documents, never re-derived from masters (`CLAUDE.md` rule 26). Stores stock from `inventory.ItemLedger`; mill products (wheat, bardana, atta, maida, suji, bran) from `products.ProductLedger`; party sacks from `products.PartyBardanaLedger`; accounts from `finance.AccountVoucherLine`. Reversed documents count as zero, not as negatives, unless the report is explicitly a reversal report.
7. Performance: one query for rows, one for totals, aggregate in the database (`Sum`, `Window`, `Coalesce`). Verify with `EXPLAIN`; add the `(filter, -date)` index in the same migration if a new one is needed. No N+1.
8. Screens show labels, figures and actions only. No lede, no explanatory cards. Business words: "Impurities" not khoot, "Category" not class.
9. Gates after each report: `python manage.py check`, `makemigrations --check --dry-run`, `ui_lint`, `python manage.py test apps.inventory.tests`. Add a selector test with a rolled-back fixture for every report that carries money or weight.
10. Do not touch existing reports' URLs; extend them. Existing today: `inventory` sales/purchases/purchase-returns/sale-returns/ledger/pending-orders; `production` daily-grinding/yield-trend/production-summary; `finance` trial balance, income statement, balance sheet, cash flow, inventory valuation, daybook, account ledger, period close.

## Who reads these reports

Design each report for one named reader; the tiles and default sort follow that reader.

| Reader | Cares about | Default view |
|---|---|---|
| Owner / Seth | Cash, profit, wheat stock in days, receivables, who owes what, daily position | One-page daily position, month-to-date vs last month |
| Mill Manager | Wheat in / atta out, yield %, shortage, machine downtime days, godown stock | Today and this week, by shift where captured |
| Purchase Manager / Munshi | Arhti-wise wheat, rate per mund, impurities, moisture, sacks owed/held, pending payments | Party-wise, this month |
| Sales Manager | Dealer-wise bags sold, brand mix, credit days, returns, rate trend | Party-wise and product-wise, this month |
| Accountant | Ledgers, day book, trial balance, vouchers by type, aging, WHT, period close | Fiscal period |
| Store Keeper | Spares/lubricants stock, reorder, consumption, adjustments | Item-wise, current stock |
| Gate / Weighbridge clerk | Vehicle in/out, gross/tare/net, party vs mill weight, katla | Today's slips |
| Bardana clerk | Sacks in, sacks out, party sacks held, returnable, mill stock of empty bags | Party-wise balances |
| HR / Payroll | Headcount, salary sheet, allowances, deductions, monthly cost | Month |

## Report catalogue — build in this order

Each line: **Report** — rows · filters · tiles · notes. "Std filters" = date range + organization/branch + godown where relevant.

### A. Owner dashboard pack (build first; demo opens here)

1. **Daily Position (Owner's one-pager)** — today's wheat purchased (kg, mund, Rs), wheat ground, atta/maida/suji/bran produced, bags sold (qty, Rs), cash & bank closing, receivable & payable totals, wheat stock in days at current grinding rate · date · 8 tiles · printable A4 portrait; this is the report the owner reads on the phone every evening.
2. **Month at a Glance** — day-wise rows for the month: purchase kg, grinding kg, production kg, sales Rs, cash in, cash out, closing cash · month · totals + MTD vs previous month delta tiles.
3. **Profitability by Product** — per product: qty sold, sales Rs, COGS (from ProductLedger rate), gross margin, margin % · std filters · tile per top product.
4. **Receivables Aging** — customer-wise 0-30 / 31-60 / 61-90 / 90+ from `CustomerLedger`, credit limit, over-limit flag · as-of date, customer, over-limit only.
5. **Payables Aging** — supplier-wise same buckets from supplier ledger / unpaid `PurchaseInvoice.total_amount - paid_amount` · as-of date, supplier type (arhti / bardana / stores).

### B. Sales

6. **Sales Register** (extend existing) — invoice-wise: no, date, customer, product summary, qty (bags, kg), gross, discount, tax, net, paid, balance, pay mode, status · std + customer, product, pay mode, status, invoice type (invoice / POS) · tiles: invoices, bags, net, cash, credit, balance.
7. **Sales Summary — Daily / Weekly / Monthly** — one screen, `group=day|week|month` toggle: period, invoices, bags, kg, gross, discount, net, cash, credit, returns, net-of-returns · std filters · trend tiles (this period vs last).
8. **Party-wise Sales** — customer: invoices, bags, net, returns, received, closing balance, last sale date, avg days to pay · std + customer, city · click row → customer ledger.
9. **Product-wise Sales** — product (brand + pack): bags, kg, net, avg rate, share % of total · std + product tree node · tile per product family (Atta / Maida / Suji / Bran).
10. **Sale Rate History** — product × date rate actually billed vs `ProductRate` list rate, variance · product, customer · for the sales manager's rate discipline.
11. **Sale Returns** (extend existing) — return-wise with original invoice, reason, qty, value, restocked godown · std + customer, product.
12. **POS Cash Sales Day Sheet** — cash counter: per invoice cash/card/online, discounts, cashier, shift totals · date, cashier · tiles: cash, card, online, total.
13. **Salesman / Broker Commission** — broker-wise sales and commission due (from sale invoice broker + brokerage fields where present) · std + broker.

### C. Purchase (wheat, bardana, stores)

14. **Wheat Purchase Register** — slip-wise: invoice no, date, arhti, vehicle, party weight, mill weight, selected weight, katla, impurities, moisture, sack deduction, credit weight (kg + mund), rate/mund, goods amount, freight (who paid), brokerage (who bore), WHT, net payable, paid, balance · std + supplier, vehicle, broker, weight source (party / mill), status · tiles: slips, credit weight mund, avg rate/mund, net payable, balance.
15. **Purchase Summary — Daily / Weekly / Monthly** — grouped like report 7: slips, kg, mund, avg rate, amount, freight, brokerage, WHT, paid, balance.
16. **Arhti-wise (Party-wise) Purchase** — supplier: slips, credit kg, avg rate/mund, amount, paid, balance, avg impurities %, avg moisture %, sacks held · std + supplier · row → supplier ledger.
17. **Wheat Quality Report** — slip-wise impurities %, moisture %, katla, deductions; arhti average and mill average; flags above threshold · std + supplier, threshold input.
18. **Rate Trend (Wheat)** — day/week avg rate per mund, min, max, total mund · std · line trend tile.
19. **Freight & Brokerage** — slip-wise freight amount and payer, brokerage and bearer; totals mill-paid vs supplier-borne · std + supplier, broker.
20. **Withholding Tax (WHT) Register** — supplier-wise WHT deducted per slip, monthly total, NTN · std + supplier · for FBR filing.
21. **Stores Purchase Register** — inventory-item invoices: no, date, supplier, item, category, qty, rate, amount, PO link, three-way status · std + supplier, category, item.
22. **Purchase Orders — Pending / Fulfilment** (extend existing) — PO-wise ordered vs received vs pending, age in days, supplier · std + supplier, status.
23. **Purchase Returns** (extend existing) — return-wise with original invoice, item, qty, value, reason · std + supplier.
24. **Supplier Payment Status** — supplier: invoiced, paid, balance, oldest unpaid date, due in 7 days · as-of + supplier type.

### D. Weighbridge / Gate

25. **Weighbridge Register** — every slip: date, time, vehicle, party, direction (in = wheat purchase, out = product sale/dispatch), gross, tare, net, party weight, mill weight, difference, selected · std + vehicle, party, direction, difference > X kg · tiles: vehicles, in-kg, out-kg, avg difference.
26. **Vehicle-wise Report** — vehicle: trips, total net kg, avg difference, last visit · std + vehicle.
27. **Weight Variance Report** — slips where party vs mill weight differ beyond tolerance, who selected which weight, cost impact (difference × rate) · std + tolerance input, supplier.
28. **Daily Gate Sheet** — today's in/out in time order for the gate register; printable.

### E. Bardana (sacks)

29. **Bardana Stock (Mill)** — bardana item × godown: opening, in (purchased, returned), out (issued to packing, returned to party), closing · std + item, godown.
30. **Party Bardana Balances** — party: sacks received (party-owned), returned, held by mill, returnable due · as-of + party, ownership.
31. **Bardana Movement Register** — `PartyBardanaLedger` + `ProductLedger` bardana rows: date, party, source doc, qty in/out, ownership, godown · std + party, source.
32. **Packing Consumption** — grinding voucher-wise bags consumed per product vs output bags, variance · std + product.

### F. Production / Grinding

33. **Grinding Register** — voucher-wise: no, date, from/to, wheat issued, disposal wheat, output kg per product, total output, yield %, standard yield %, shortage kg/%, prepared by · std + godown, prepared by · tiles: vouchers, wheat kg, output kg, avg yield.
34. **Daily Grinding** (extend existing) — day-wise wheat in, output by product, yield, shortage, downtime days (days with zero grinding flagged).
35. **Yield Trend** (extend existing) — week/month yield % vs standard, best/worst day, moving average.
36. **Product Output Mix** — per period: kg and % per product (atta, maida, suji, bran, refraction) vs target mix · std.
37. **Shortage / Refraction Report** — voucher-wise shortage beyond standard, cost of shortage (× wheat rate) · std + threshold.
38. **Product Conversion Register** — conversion-wise from-product → to-product lines, qty, godown · std + product.
39. **Production Cost per Bag** — period: wheat cost (credit weight × rate), bardana cost, direct expenses (from expense accounts linked via `ProductAccountLink`), ÷ bags produced, per product · month · the number the owner uses to set atta rate.
40. **Production Summary** (extend existing) — month-wise consolidated for the manager.

### G. Stock / Inventory

41. **Mill Product Stock** — product × godown: opening, in, out, closing (kg and bags), value at current rate · as-of + product, godown · tiles per family.
42. **Stores Stock** — item × godown: opening, in, out, closing, value, reorder flag, days since last movement · as-of + category, godown, below-reorder only.
43. **Item Ledger** (extend existing, both books) — running balance per item/product with document links · std + item, book.
44. **Stock Ageing / Slow Moving** — items with no movement in 30 / 60 / 90 days and their value · as-of.
45. **Stock Adjustment Register** — `ManualTransaction` rows: date, item, qty ±, reason, user · std + item, user.
46. **Godown-wise Stock** — godown: wheat, each product, empty bags, stores value · as-of.
47. **Wheat Stock in Days** — closing wheat ÷ avg daily grinding (last 30 days) · as-of · single tile + trend.
48. **Stock Valuation** (extend existing finance report) — by valuation method, product and stores books separate, reconciliation to trial balance stock accounts.

### H. Accounts

49. **Day Book** (extend existing) — voucher-wise for the day with running cash and bank balance; group by voucher type.
50. **Cash Book** — cash account only: opening, receipts, payments, closing, day-wise · std.
51. **Bank Book** — per bank account: same as cash book with cheque no/date · std + bank.
52. **Account Ledger** (extend existing) — any account: opening, debit, credit, running balance, narration, voucher link · std + account, voucher type · export mandatory.
53. **Party Ledger (Customer / Supplier)** — combined document + voucher view: invoices, returns, receipts/payments, adjustments, running balance, sacks column for wheat suppliers · std + party · this is the statement printed and sent to the party.
54. **Voucher Register by Type** — cash receipt / cash payment / bank receipt / bank payment / journal: list with status, posted by, attachments · std + type, status, account.
55. **Trial Balance** (extend existing) — opening, debit, credit, closing; drill to ledger; period vs fiscal-year-to-date.
56. **Income Statement** (extend existing) — monthly columns option, compare with previous period, gross margin line from COGS.
57. **Balance Sheet** (extend existing) — as-of with previous period column.
58. **Cash Flow** (extend existing) — direct method: receipts from customers, payments to arhtis, stores, expenses, salaries.
59. **Expense Analysis** — expense account × month grid, share %, vs last year · fiscal year.
60. **Receivable / Payable Summary** — one screen, both sides, net position, top 10 each way · as-of.
61. **Opening Balance Report** — fiscal-year opening balances by account with source (carried / manual) · fiscal year.
62. **Period Close Checklist** (extend existing) — unposted vouchers, un-invoiced POs, negative stock, unbalanced days; blocks close until clean.
63. **Audit Trail** — document reversals, voucher edits, who posted what when · std + user, doc type.

### I. HR / Payroll

64. **Employee Register** — active/inactive by department, designation, join date, salary · status, department.
65. **Salary Sheet** — month: employee, base, allowances, deductions, net, bank/cash, signature column · month, department · printable landscape.
66. **Payroll Summary** — month-wise total cost, headcount, avg salary, vs last month · fiscal year.
67. **Allowance / Deduction Breakdown** — item-wise totals per month · month.

### J. Setup / Master reports (small, but the demo asks)

68. **Supplier / Customer Directory** — with credit limits, balances, city, contact · export.
69. **Product Master with Rates** — tree with pack size, bag weight, current rate, last rate change.
70. **Chart of Accounts** (extend existing) — tree with balances.
71. **User Access Report** — user × role × branch, permissions granted, last login.

## Shared behaviour to build once

- **Report shell component** `templates/components/report/shell.html`: page header (title, period, export menu, print), filter bar with date presets, tiles, table slot, footer totals. Every report uses it; no report pastes its own CSS.
- **Date presets** in `apps/core/reporting.py`: `resolve_period(request) -> (start, end, label)`; presets today / yesterday / this week / last week / this month / last month / this fiscal year / custom; `group_by(day|week|month)` helper returning truncated periods with Pakistani week starting Monday.
- **Export**: `png` format added to `apps/core/table_export.py` (render print template → image; pick one vendored approach, no CDN, no external service). PDF and Excel already exist through `ColumnSet`; every report defines its `ColumnSet` so column picker and export share the same list.
- **Drill-down**: any party, product, document number, or account in a report row is a link to its ledger/detail page.
- **Comparison tiles**: tile component gains optional `delta` (value and direction vs previous period) — used by summary reports.
- **Report registry**: `apps/core/reports.py` lists every report (key, label, module, reader, url_name, permission) so the Reports section of the nav, the dashboard "Reports" card and the User Access report all read from one list.
- **Scheduling (phase 2, do not build now)**: owner's Daily Position emailed/WhatsApped at 8 pm.

## Nav

Replace the current `Reports` section with grouped children mirroring the catalogue: Owner, Sales, Purchase, Weighbridge, Bardana, Production, Stock, Accounts, HR. Keep module-local report links (e.g. Production → Daily Grinding) pointing at the same URLs.

## Delivery

Work in the order A → J. After each group: run the gates, add the group's entry to `docs/WORKLOG.md`, and stop with a short list of what shipped, the query count per screen, and any figure you could not source from the ledgers. Do not ask which report to build next; the order above is the answer. Ask only when a figure's definition is ambiguous in the data (for example which weight is "credit weight" when both party and mill weights are blank).
