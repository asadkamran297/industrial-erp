# Agent Instructions

This project is a custom Industrial ERP / MIS portal. Keep the user-facing product out of Django Admin.

## Rules

- Keep business logic out of templates.
- Prefer selectors, services, model managers, and focused class-based views for real business workflows.
- Reuse templates in `templates/components/` for buttons, cards, forms, tables, status badges, and page headers.
- Do not duplicate page-level form/table styling.
- Keep branding dynamic through `SystemSetting` wherever possible.
- Maintain custom `User` and `BaseModel` as foundational contracts.
- Prepare code for MySQL/MariaDB even when local development uses SQLite.
- Use HTMX for partial reloads, live search, modal forms, and pagination when modules are added.
- Use Alpine.js only for simple UI state.
