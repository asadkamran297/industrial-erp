# AI Workflow

## Build Pattern

1. Read the nearby code before changing it.
2. Keep changes focused to the requested foundation or module.
3. Create migrations for model changes.
4. Run checks and migrations.
5. Run `python manage.py seed` when new default master data or roles are added.
6. Document commands and important files changed.

## Future Module Pattern

- Add models to the relevant app.
- Add selectors for read/query logic.
- Add services for writes and workflows.
- Add forms for validation.
- Add views for request handling.
- Add templates using existing components.
- Add tests for business rules and permissions.
