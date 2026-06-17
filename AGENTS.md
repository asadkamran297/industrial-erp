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

## Module Structure

Build the ERP module-wise so shared foundations stay centralized and every business area remains neat and easy to continue.

Recommended apps:

- `apps.core`: `BaseModel`, `SystemSetting`, constants, shared managers, mixins, validators, utilities.
- `apps.accounts`: Django custom `User`, authentication, profile/account behavior.
- `apps.access_control`: roles, permissions, role permissions, user assignments.
- `apps.configurations`: all `conf_*` master data such as departments, designations, cities, genders, qualifications, salutations, blood groups, religions, marital statuses, job types, expense types, payment methods, manufacturers, image types, allowance/deduction types, and specializations.
- `apps.organizations`: organizations and branches.
- `apps.hr`: employees, employee qualifications, employee experiences, employment profile data.
- `apps.payroll`: salary structures, salary structure items, payrolls, payroll items.
- `apps.portal`: dashboard, shell, navigation, and authenticated portal views.
- `apps.design_system`: reusable UI component patterns and design-system support.

Each business module should follow this internal pattern when needed:

- `models.py`: database schema only.
- `admin.py`: emergency/developer admin registration.
- `forms.py`: form validation and widgets.
- `selectors.py`: read/query logic.
- `services.py`: write/business workflow logic.
- `urls.py`: module routes.
- `views.py`: request/response orchestration.
- `tests.py` or `tests/`: important business and permission tests.

Use clean Django model names such as `Employee`, `Department`, and `Organization`; keep database table names module-prefixed through `Meta.db_table`, such as `hr_employees`, `conf_departments`, and `org_organizations`.

Do not create a separate duplicate login table like `iams_users`. Extend or relate to the existing `accounts.User` model for IAM behavior.
