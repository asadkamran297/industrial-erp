# Architecture

## Layers

- `config/settings/`: environment-specific Django settings.
- `apps.accounts`: custom user and authentication.
- `apps.core`: shared models, system settings, global context.
- `apps.core.constants`: shared statuses, common choices, and application-wide constants.
- `apps.portal`: authenticated user portal.
- `templates/components`: reusable UI patterns.

## Principles

- Views orchestrate request/response only.
- Business behavior belongs in services, selectors, managers, and model methods.
- Templates render data and should not contain business decisions.
- System branding should come from `SystemSetting`.
- Soft delete and audit fields are part of the shared model foundation.
