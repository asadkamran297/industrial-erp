# Database Rules

- Use the custom `apps.accounts.User` model from day one.
- Use `BaseModel` for business models unless there is a strong reason not to.
- Keep soft-deleted records by setting `deleted_at` rather than hard deleting operational history.
- Include audit fields for created/updated ownership where useful.
- Use explicit field names and choices.
- Plan production for PostgreSQL.
- Add indexes intentionally for search, filters, and reporting once modules are introduced.
