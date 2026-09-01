# Database Rules

- Use the custom `apps.accounts.User` model from day one.
- Use `BaseModel` for business models unless there is a strong reason not to.
- Keep soft-deleted records by setting `deleted_at` rather than hard deleting operational history.
- Include audit fields for created/updated ownership where useful.
- Use explicit field names and choices.
- Plan production for PostgreSQL.

## Indexing

Every new table must ship with its indexes in the same migration that creates
it. A table is not finished until this list has been walked.

- `BaseModel` already indexes `created_at` and `deleted_at`, so every model
  inheriting it gets those for free. Do not repeat them per model.
- Django indexes `ForeignKey` columns automatically. Do not add a single-column
  index on a plain FK; it is already there.
- Add a **composite index for every list screen**, ordered
  `(filter field, -date field)` — the same order the screen filters and sorts
  in. `(status, -purchase_date)` serves `WHERE status = ... ORDER BY
  purchase_date DESC` in one pass; two single-column indexes do not.
- Add a composite `(fk, -date)` for any "history of one party" view: customer
  statement, supplier history, item stock card.
- Index the columns a document is looked up by outside its primary key —
  document numbers, transaction ids, external references.
- For a document traced back to its source, index the pair, e.g.
  `(ref_table, ref_id)`.
- Do not index a lone low-cardinality flag (a boolean, a yes/no char). It earns
  its place only as the first column of a composite.
- Unique constraints already create an index; do not shadow them.

Confirm the work rather than assuming it: run the screen's query under
`EXPLAIN` (`EXPLAIN QUERY PLAN` on SQLite) and check the plan names the index
instead of scanning the table.
- Seeders must be idempotent. Use `update_or_create` or `get_or_create` so running `python manage.py seed` multiple times does not duplicate master data.
