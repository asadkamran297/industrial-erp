# Agent Instructions

This project is a custom Industrial ERP / MIS portal. Keep the user-facing product out of Django Admin.

## Rules

- Keep business logic out of templates.
- Prefer selectors, services, model managers, and focused class-based views for real business workflows.
- Reuse templates in `templates/components/` for buttons, cards, forms, tables, status badges, and page headers.
- Do not duplicate page-level form/table styling.
- Keep branding dynamic through `SystemSetting` wherever possible.
- Maintain custom `User` and `BaseModel` as foundational contracts.
- Prepare code for PostgreSQL even when local development uses SQLite.
- Define shared constants, reusable status values, and common choice arrays in `apps/core/constants.py`; import and reuse them throughout the application instead of redefining literals in models, forms, views, or templates.
- Use HTMX for partial reloads, live search, modal forms, and pagination when modules are added.
- Use Alpine.js only for simple UI state.
