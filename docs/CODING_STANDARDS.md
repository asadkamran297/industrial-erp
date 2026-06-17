# Coding Standards

- Prefer clear, explicit Django code over clever abstractions.
- Use class-based views where they reduce duplication.
- Keep views thin and templates simple.
- Use type hints for service and selector functions.
- Keep shared statuses, common choice arrays, and app-wide constants in `apps/core/constants.py`.
- Do not redefine status strings or repeated choice lists inside individual models, forms, views, or templates.
- Add comments only where code intent is not obvious.
- Keep reusable UI in components.
- Avoid unused imports, dead code, and placeholder broken pages.
- Run Django checks before handing off changes.
