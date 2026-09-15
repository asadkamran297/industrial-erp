# Claude / AI Workflow Notes

Work as a senior Django ERP engineer. The project foundation is intentionally small and clean so future agents can extend it safely.

## Before Editing

1. Inspect existing files and avoid overwriting unrelated user changes.
2. Check settings imports, app labels, and migrations when touching models.
3. Preserve the custom portal direction; Django Admin is not the product UI.
4. Put shared statuses, choice arrays, and application-wide constants in `apps/core/constants.py` and reuse them everywhere.
5. Keep the ERP module-wise: shared foundations in `apps.core`, login/profile in `apps.accounts`, IAM in `apps.access_control`, master data in `apps.configurations`, organization hierarchy in `apps.organizations`, employees in `apps.hr`, and salary/payroll in `apps.payroll`.
6. For each business module, prefer the same structure: `models.py`, `admin.py`, `forms.py`, `selectors.py`, `services.py`, `urls.py`, `views.py`, and tests when behavior matters.
7. Use clean Django model names and module-prefixed table names via `Meta.db_table`; for example `Employee` with `db_table = "hr_employees"`.
8. Every new table ships with its indexes in the same migration that creates it. Follow the indexing checklist in `docs/DATABASE_RULES.md` — composite `(filter, -date)` indexes for list screens, `(fk, -date)` for per-party history — and verify with `EXPLAIN` rather than assuming.
9. Do not create duplicate IAM login tables. Use the existing `accounts.User` model and relate assignments/roles to it.
10. Do not add narrative or justification comments in code or templates (e.g. `{# why this button exists #}`, "offered beside X because Y"). No explanatory prose on screens either. Comment only when logic is truly non-obvious (a workaround, a hidden constraint), in one short line.
11. Input fields carry a label only. No help text, hint paragraphs, explanatory placeholders, or `help_text` on form/model fields describing what the field means or why it exists. Allowed only when it states a rule the user cannot otherwise discover (a limit, a required format), kept to a few words.

## Screens and Templates

12. Screens show labels, figures and actions only. No page lede under the heading, no intro paragraphs, no explainer cards or notes. If an explanation is truly needed, use a `title=` tooltip.
13. Every list/register screen follows the board pattern (Purchase Orders board): clickable tiles counted over the filtered set, shared filter bar, sortable table, status pill, icon row-actions, page-total footer, pagination, export. Include `templates/components/table/board_theme.html`; never paste its CSS.
14. Reuse `templates/components/` (fields, buttons, back button, tables). Do not copy-paste a component's markup or styles into a screen.
15. Form validation uses native HTML `required`; no custom validation bubbles.
16. Django `{# #}` is single-line only. Never write a multi-line `{# #}` (it prints on the page); inside `<style>` use CSS comments.
17. Date inputs need at least ~11.5rem width so the year is not clipped.
18. Every style rule is light-first with its `.dark` counterpart directly beneath it.
19. No CDNs. Vendor JS lives in `static/vendor/`. After touching Tailwind classes run `npm run build:css`.
20. Weights keep three decimals (weighbridge precision); money keeps two. Do not route weight inputs through `amount-format.js`.
21. Keep an existing screen's field layout unless the user asks to change it (e.g. the wheat purchase slip mirrors the mill's paper slip).
22. User-facing wording uses the business term (e.g. "Category", not "Class"; "Impurities", not `khoot`) even when the model name differs.

## Data and Business Rules

23. Posted documents are never deleted. Correct them by reversal (mirror entries); anything referenced elsewhere can only be deactivated.
24. Purchase and sales are two documents: optional order (no ledger, no stock) and mandatory invoice (the only stock-in/financial event). Read `docs/TWO_DOCUMENT_REFACTOR.md` before changing this flow.
25. `apps.products` (flour-mill products: wheat, bardana, atta) has its own `ProductLedger`. Never post mill stock through `inventory.ItemLedger`; the only door in is `apps.products.services.post_movement`.
26. Values that drive reported figures (unit weight, rates, credit weight, yield) are snapshotted on the document when saved. Never re-derive them from masters at read time.
27. Document numbers come from per-series sequences in services (`PO-`, `PI-`, `SAL-`, ...). Never hand-type or share counters between series.
28. Any `select_for_update()` combined with `select_related()` over a nullable FK must pass `of=("self",)`.
29. Watch for N+1 queries on list screens; add `select_related`/`prefetch_related` for everything the rows render.
30. After changing page actions in `apps/access_control/pages.py`, run `python manage.py seed`.
31. Money math uses `Decimal` and quantizes to the column's decimal places before `full_clean()`.

## Verification, Git and Live

32. The user tests screens personally. Run only the gates below (plus `python manage.py test apps.inventory.tests` when Python changed), then report what changed. Do not write probe scripts or dump pages unless asked.
33. Never let any script write to real data; if something must be exercised, wrap it in `transaction.atomic()` and roll back.
34. Commit or push only when the user asks.
35. Never commit secrets. Credentials live in git-ignored `.env` / `deploy/cpanel.config`.
36. For deploy: follow `docs/DEPLOYMENT.md` and `deploy/cpanel.config`; do not re-ask host details. Live is MySQL. Override `DATABASE_URL` (not `DB_NAME`) and confirm the target database before running anything. Never run `seed_demo` or `seed all` on live. Take a DB dump before a risky deploy.
37. Add one dated entry per working day to `docs/WORKLOG.md` (Local / Live / Open).

## After Editing

Run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

When models change, create migrations and run:

```powershell
python manage.py migrate
```
