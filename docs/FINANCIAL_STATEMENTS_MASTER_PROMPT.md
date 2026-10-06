# Master Prompt — QuickBooks-Grade Financial Reports

Paste everything below the line into a fresh session.

---

## Role

You are the senior Django ERP engineer on `industrial_erp` (flour-mill ERP). Rebuild the accounting reports so they behave and read like **QuickBooks Online reports**: date-driven, customisable, comparable, collapsible, drillable to the transaction, and always tying out. Correct to the paisa. Read `CLAUDE.md`, `docs/UI_SYSTEM.md`, `docs/DATABASE_RULES.md`, `docs/REPORTING_MASTER_PROMPT.md` first and obey them; where this prompt and `CLAUDE.md` disagree, `CLAUDE.md` wins.

## What exists today (verified 2026-10-05 — re-verify before building)

| Piece | Where | State |
|---|---|---|
| Ledger source | `finance.AccountVoucherLine` (`account_no`, `voucher_date`, `debit_amount`, `credit_amount`), header `AccountVoucher` (`posted`, `status`, `source_ref`) | Only source of money figures. Index `(account_no, -voucher_date)` exists on lines. |
| Chart | `finance.ChartOfAccount` tree, 5 roots (ASSETS, LIABILITIES, CAPITAL, REVENUE, EXPENSES), level-2: Current / Non Current Assets, Current / Non Current Liabilities, Owner's Capital, Reserves & Surplus, Direct / Indirect Revenue, Direct / Indirect Expenses. Leaves postable. `opening_balance` on leaf (undated). | GL paths in `apps/core/constants.py` (`GL_*_PATH`). |
| Balances | `apps/finance/services.py::account_balances()` | **Life-to-date only, no dates. Counts every voucher line, including unposted drafts.** |
| Income Statement | `services.income_statement()` + `finance/income_statement.html` | Flat revenue list + flat expense list, life-to-date, no gross profit, no period. |
| Balance Sheet | `services.balance_sheet()` + `_balance_forest()` | Tree, life-to-date, no as-of date, life-to-date net profit plugged into Capital. |
| Trial Balance | `views.TrialBalanceView` | Opening/movement/closing, no dates, no drill, `ledger_integrity()` check. |
| Cash Flow | `services.cash_flow_statement()` | Direct method, cash leg prorated across counterparts, life-to-date. |
| Period close | `services.close_period_to_retained_earnings()` | Posts `period_close:YYYY-MM-DD` journal moving P&L into Retained Earnings. |
| Ledgers & H-group | `apps/finance/report_selectors.py`, `report_views.py` | Cash/Bank book, Party ledger, Voucher register, Expense analysis (monthly cols), Receivable/Payable summary, Opening balances, Audit trail. |
| Aging | `apps/portal/selectors.py::receivables_aging / payables_aging` | Owner group. Reuse, do not duplicate. |
| Framework | `apps/core/reporting.py` (`ReportView`, `ReportExportView`, `ReportColumnsView`, `resolve_period` + presets, `as_of_report`), `apps/core/reports.py` registry, `templates/reports/generic.html`, `components/report/*` | Reuse for every new screen. |

## Defects to fix first (Phase 0 — correctness before looks)

1. **Undated balances.** Every statement must take a period (`start`, `end`) or an `as_of`. Life-to-date is just a preset.
2. **Drafts in figures.** `account_balances()` sums lines of vouchers with `posted = NO`. QuickBooks reports only booked transactions. Make "posted only" the rule for all statements. **Before switching, count unposted lines and their totals on local and report them; the switch changes figures the user has seen — get the user's yes.**
3. **Period-close double effect.** A P&L over a range that contains a `period_close:` voucher nets to zero. P&L must **exclude** vouchers whose `source_ref` starts with `period_close:`. Balance sheet must stay tied regardless (formula below).
4. **Plugged profit.** Balance sheet adds life-to-date profit to Capital. Replace with the QuickBooks split: **Retained Earnings** (everything before the fiscal-year start) and **Net Income** (fiscal-year start → as-of).
5. **Flat P&L.** No COGS / Gross Profit / Operating / Other sections.
6. **Undated opening.** `ChartOfAccount.opening_balance` has no date: treat it as dated before every transaction (sits in the first column's opening, never inside a period's movement).

## One engine, all statements

Build `apps/finance/statements.py` (selectors-style, no views). Every statement calls it; nothing else touches `AccountVoucherLine` for statement figures.

```python
Column = namedtuple("Column", "key label start end")   # start=None -> from inception

def account_movements(columns, *, codes=None, exclude_close=False) -> dict[code, dict[col_key, Decimal]]
    # ONE query: values("account_no").annotate(**{col.key: Sum(Case(When(voucher_date__range=..., then=debit-credit)))})
    # filtered to voucher__posted=YES; exclude source_ref__startswith="period_close:" when exclude_close.
    # Raw debit-minus-credit; sign flipping happens once, in the tree builder.

def balances_as_of(dates, ...)   # same, cumulative (<= date) + ChartOfAccount.opening_balance
```

- One query per statement regardless of column count (12 months = 12 conditional sums, one round trip). `EXPLAIN` it; if the join to `fin_account_voucher` for `posted` is slow on MySQL, report it and propose options — do **not** add fields unasked.
- Natural sign: debit-natured (`DEBIT_NATURE_TYPES`) shows `debit - credit`, others `credit - debit`. Contra accounts (Sales Returns, Sales Discount under Revenue) therefore show negative → render in parentheses.
- Tree builder: takes the chart (one read, `status=ACTIVE`), the per-code figures, returns flat **rows** ready to render:

```python
{"kind": "section" | "group" | "account" | "total" | "computed" | "grand",
 "depth": int, "code": str, "title": str, "values": {col_key: Decimal},
 "drill": {col_key: url} | None, "collapsible": bool, "parent": row_id}
```

  Each group emits a header row, its children, then a `Total <Group>` row (QuickBooks style). Inactive accounts that carry balance still appear (flag, never hide money). Zero rows hidden unless "Show all rows".
- Quantize every figure with `money()` from `apps/core/reporting.py`; `Decimal` only.

## Report catalogue (QuickBooks equivalents)

### P&L family — `finance:income_statement` (keep URL, extend)

Layout (QuickBooks "Profit and Loss"):

```
Income                         <- Direct Revenue (Sales Revenue, less Sales Returns, less Sales Discount)
Total Income
Cost of Goods Sold             <- Direct Expenses (COGS, Freight and Carriage, Brokerage, Purchase Price Variance, Inventory Adjustment)
Total Cost of Goods Sold
GROSS PROFIT                   = Total Income - Total COGS            (+ Gross margin % tooltip/column)
Expenses                       <- Indirect Expenses
Total Expenses
NET OPERATING INCOME           = Gross Profit - Total Expenses
Other Income                   <- Indirect Revenue
Other Expenses                 <- (empty unless a group maps here)
NET OTHER INCOME
NET INCOME
```

- Section mapping lives in `apps/core/constants.py` as `FS_PL_SECTION_BY_GROUP = {("REVENUE","Direct Revenue"): "income", ...}` keyed on root + level-2 title, same style as `GL_*_PATH`. Unmapped groups fall into a visible "Unmapped" section, never silently dropped. Ask the user before adding a per-account override field.
- Variants (same engine, same template, different defaults — each its own registry entry so it shows in the reports index):
  - **Profit and Loss** — total only.
  - **P&L by Month** — columns by month (existing `report_selectors.month_keys()`).
  - **P&L Comparison** — current vs previous period / previous year, `Change` and `% Change`.
  - **P&L as % of Total Income** — each row with `% of Income` column.
  - **P&L Detail** — every transaction under each account (date, type, number, party, memo, amount, running balance), grouped with subtotals.
  - **P&L by Product / by Party** — only if postings carry the dimension; check `source_ref` linkage first, else list as open.

### Balance Sheet family — `finance:balance_sheet` (keep URL, extend)

Layout (QuickBooks "Balance Sheet"), driven by the chart tree with `Total` rows:

```
ASSETS
  Current Assets
    Cash / Bank / Receivables / Inventory / Input Sales Tax ...
  Total Current Assets
  Non Current Assets
  Total Non Current Assets
TOTAL ASSETS
LIABILITIES AND EQUITY
  Liabilities
    Current Liabilities ... Total Current Liabilities
    Non Current Liabilities ... Total Non Current Liabilities
  Total Liabilities
  Equity
    Opening Balance Equity
    Owner's Capital ...
    Retained Earnings          (computed)
    Net Income                 (computed)
  Total Equity
TOTAL LIABILITIES AND EQUITY
```

Equity split (always ties, closed or not):

```
FY_start      = start of the fiscal year containing as_of (FiscalYear; fallback Jan 1)
Net Income    = P&L(FY_start .. as_of, exclude_close=True)
All P&L       = sum of every Revenue/Expense balance as_of INCLUDING close vouchers (natural sign, revenue - expense)
Retained Earnings line = RE account balance as_of + All P&L - Net Income
```

Variants: **Balance Sheet** (as-of), **Balance Sheet Comparison** (as-of vs previous period end / previous year end, Change, % Change), **Balance Sheet by Month/Quarter** (column per period end), **Balance Sheet Detail** (transactions per account inside the period, opening + running balance). Out-of-balance amount, if ever non-zero, shows as a red row "Out of balance" — never hidden.

### Trial Balance — `finance:trial_balance` (extend)

As-of date (default today) **and** optional period: columns Opening Dr/Cr · Period Dr/Cr · Closing Dr/Cr. Group by chart tree with collapse, or flat by code. Each amount drills to the ledger. Keep `ledger_integrity()` banner. Comparison column optional.

### Ledgers and journals

- **General Ledger** (new) — all accounts (or a chosen one / group) for a period: opening, every line (date, type, number, party, memo, split account, debit, credit, running balance), closing. Paginate per account, not per line count. Reuse `account_ledger()` logic; do not fork it.
- **Journal** (new) — every voucher in the period with all its lines, debits = credits per voucher, voucher-type filter.
- **Transaction List by Date** (new) — one row per voucher, filters: type, account, party, posted, amount range.
- Existing Account Ledger, Daybook, Cash/Bank Book, Party Ledger, Voucher Register stay; add drill-in/out links so they all interlink.

### Cash Flow — `finance:cash_flow` (extend)

QuickBooks uses the **indirect method**. Build it as the default, keep the current direct-method view as a toggle.

```
OPERATING ACTIVITIES
  Net Income                                    (= P&L for the period)
  Adjustments: change in each Current Asset (except cash/bank) and Current Liability account
Net cash from operating activities
INVESTING ACTIVITIES   change in Non Current Assets
FINANCING ACTIVITIES   change in Non Current Liabilities + Capital accounts (excl. Retained Earnings)
NET CASH INCREASE FOR PERIOD
Cash at beginning of period
CASH AT END OF PERIOD          must equal Balance Sheet cash+bank at end date
```

Reconciliation failure shows as a red difference row.

### Receivables / payables (QuickBooks A/R + A/P set)

Reuse `portal.selectors.receivables_aging / payables_aging` and `report_selectors.party_ledger / receivable_payable`. Add only what is missing: **A/R Aging Summary & Detail**, **A/P Aging Summary & Detail** (Current, 1–30, 31–60, 61–90, 91+; buckets configurable), **Customer / Supplier Balance Summary & Detail**, **Open Invoices**, **Unpaid Bills**. If the owner-group screens already are one of these, register an alias in the Accounts group instead of a second screen.

### Equity

**Statement of Changes in Equity** (optional, last): opening equity, owner contributions/drawings, net income, closing — ties to Balance Sheet Total Equity.

## The "Customize" panel (QuickBooks parity, shared by every statement)

Build once as `components/report/statement_toolbar.html` + a parser in `apps/finance/statements.py`; every statement uses it. All state lives in the querystring so any view is bookmarkable and exportable.

| Control | Options |
|---|---|
| Report period | existing `resolve_period` presets + add: This Quarter, Last Quarter, Last Fiscal Year, Fiscal Year to Date, Year to Date, All Dates, Custom. Balance-sheet-type reports show a single As-of date. |
| Display columns by | Total only · Months · Quarters · Years · Fiscal periods (`FiscalPeriod`) |
| Compare | Previous period (PP) · Previous year (PY) · with `Change` and/or `% Change` |
| % columns | % of Row · % of Column · % of Income · % of Expense (P&L only) |
| Rows | Active rows only (default) · Non-zero · All |
| Accounts | Collapse to level 1/2/3 · Expand all · per-row toggle (Alpine, no reload) |
| Number format | Negatives `(1,234.00)` default or `-1,234.00`; red negatives toggle; Divide by 1000; Without paisa |
| Header / footer | Company name, report title, period line, "Accrual basis", generated date+time and user — always on print/PDF/Excel |

Accounting method: **Accrual only.** Show the basis line. Cash basis needs payment-to-invoice allocation the ledger does not hold — list it as open, do not fake it.

"Memorize report" (saved customisations per user) needs a new table — **ask the user before building**; if approved: `finance_saved_reports` (user FK, report key, name, querystring, shared flag), indexes `(user, report_key)`, shipped in the creating migration.

## Drill-down (the QuickBooks feel)

- Every amount cell is a link: account row + column → that account's ledger filtered to that column's dates (`finance:account_ledger?account=..&date_from=..&date_to=..`). Computed rows (Gross Profit, Net Income, Retained Earnings) drill to the P&L for the matching range.
- Ledger rows link to the voucher detail; voucher detail links to its source document via `source_ref`.
- A "back to report" link keeps the report's querystring.

## Screen rules (from CLAUDE.md, applied here)

- Statements are **not** board screens; they use a statement layout component `components/report/statement.html`: sticky header row, right-aligned tabular-nums money columns, indentation by depth, bold total rows with top border, double underline on grand totals, light-first + `.dark` rules beneath, no CDN, `npm run build:css` after Tailwind changes, `python manage.py ui_lint` clean.
- No ledes, intro text or explainer cards. Formulas go in `title=` tooltips only.
- Money two decimals; never through weight formatting.
- Wide month views scroll horizontally inside the table container with the account column frozen; the page itself never scrolls sideways.
- Print: A4, landscape automatically when columns > 4, repeat table header each page, "Page N of M".
- Export: Excel keeps the tree as indented text + outline levels and real numbers (not strings); PDF matches print.

## Performance

- One movement query per statement + one chart read. No per-account queries, no `_descendant_leaf_codes` recursion per request (it issues one query per node — replace with a single chart read).
- Target: < 1 s locally for a 12-month P&L by month on demo data; report the `EXPLAIN` of the main query.
- Cache nothing yet; correctness first.

## Tests (`apps/finance/tests_reports.py` — extend)

Build fixtures inside the test DB only. Assert:

1. Balance sheet balances for: today, a mid-year date, a date before any data, a date after a period close.
2. P&L over a range containing a period close equals the same range computed before the close was posted.
3. Net Income on the balance sheet equals P&L (FY start → as-of).
4. Sum of month columns = total column, for P&L and cash flow.
5. Trial balance: total debits = total credits for any date.
6. Indirect cash flow end cash = balance-sheet cash + bank at end date.
7. Unposted voucher lines never move any statement figure.
8. Comparison: PP/PY columns equal the standalone report run for that range.
9. Contra revenue renders negative and reduces Total Income.
10. Query count per statement is constant across 1 vs 12 columns (`assertNumQueries`).

## Build order

0. Engine + Phase 0 defects (stop and report the unposted-lines finding before switching figures).
1. P&L (all variants) + customise panel + drill.
2. Balance Sheet (all variants) + RE/NI split.
3. Trial Balance extension.
4. General Ledger, Journal, Transaction List.
5. Cash Flow indirect.
6. A/R and A/P set (reuse first).
7. Statement of Changes in Equity; Memorize (only if approved).

Each step: Page in `apps/access_control/pages.py` + `python manage.py seed`, nav in `apps/portal/constants.py`, registry entry in `apps/core/reports.py`, URLs `<name>`, `<name>_export`, `<name>_columns`.

## Gates after every step

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.finance apps.inventory.tests
python manage.py ui_lint
npm run build:css   # only if Tailwind classes changed
```

No probe scripts against real data; anything exercised outside tests runs in `transaction.atomic()` and rolls back. Do not commit unless asked. Add the day's entry to `docs/WORKLOG.md`.

## Report back

Per step: what changed (files), figures that moved and why (especially from the posted-only switch and period-close exclusion), open questions, gates output. Stop and ask on: posted-only switch, any new field/table, cash basis, per-account section override.
