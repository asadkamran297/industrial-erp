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
