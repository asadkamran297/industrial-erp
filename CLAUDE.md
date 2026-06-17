# Claude / AI Workflow Notes

Work as a senior Django ERP engineer. The project foundation is intentionally small and clean so future agents can extend it safely.

## Before Editing

1. Inspect existing files and avoid overwriting unrelated user changes.
2. Check settings imports, app labels, and migrations when touching models.
3. Preserve the custom portal direction; Django Admin is not the product UI.

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
