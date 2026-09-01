# Work Log

One entry per working day. **Local** = changes in the repo/dev environment.
**Live** = what actually reached the production host. Newest entry on top.

---

## 2026-09-01

### Local

- `config/settings/base.py`: `STATIC_ROOT` now reads from the environment, so a
  host can collect static outside the git checkout (commit `284b595`).
- `config/settings/production.py`: `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
  now merge hosts from the environment; custom domains no longer need a code
  edit.
- `config/__init__.py`: installs PyMySQL as MySQLdb when present (shared hosting
  has no libmysqlclient).
- Added `passenger_wsgi.py`, `requirements-cpanel.txt`, `.cpanel.yml`,
  `scripts/cpanel_deploy.sh`, `.env.cpanel.example`.
- Added `docs/DEPLOYMENT.md`, `deploy/cpanel.config.example`,
  `deploy/cpanel/passenger_wsgi.py`, `deploy/cpanel/htaccess`.
- Restored a dev `.env` after it was accidentally overwritten with production
  values; the original `SECRET_KEY` was not recoverable and is a placeholder.

### Live — https://flourorbit.com (first deployment)

- Repo cloned to `/home/flouruge/industrial_erp` (branch `master`).
- MySQL `flouruge_erp` created with its own user and full privileges.
- Python 3.12 app created via the CloudLinux selector at
  `/home/flouruge/erp_app`; dependencies installed into its virtualenv.
- All migrations applied to MySQL.
- Seeded **users, roles and permissions only**: 182 permissions, 507 roles.
  Superuser `admin` created. No demo or master data.
- `collectstatic` → `/home/flouruge/staticfiles` (153 files).
- Verified: `/` → 302 `/portal/`, login page 200, real login POST → `/portal/`
  200, `/static/dist/app.css` 200.

### Live — TLS

- Let's Encrypt certificate issued for `flourorbit.com` and
  `www.flourorbit.com` (HTTP-01, challenge files pushed through the cPanel API
  with a patched `acme-tiny`) and installed via `SSL/install_ssl`.
  Valid until **2026-11-29**; renewal steps in `docs/DEPLOYMENT.md`.
- `config/settings/production.py`: `SECURE_SSL_REDIRECT` now comes from the
  environment (commit `a98459e`); HTTP 301s to HTTPS on the live host.
- Verified without `-k`: `https://flourorbit.com/` 302 → `/portal/`,
  `https://flourorbit.com/accounts/login/` 200, `https://www.flourorbit.com/`
  200, `http://` → 301 to `https://`.

### Local + Live — database indexing

- `BaseModel` now indexes `created_at` and `deleted_at`, so all 58 existing
  tables and every future one are covered (commit `6e11d9e`). `deleted_at` was
  in the WHERE clause of every `ActiveManager` query with nothing indexing it.
- Composite indexes added for the real access paths: `(status, -date)` on
  purchase orders, bills, sales and returns; `(supplier, -date)`,
  `(customer, -date)`, `(inventory_item, -transaction_date)` for per-party
  history; `(ref_table, ref_id)` on the item ledger; `(account_no,
  -voucher_date)`, `(voucher_type, -voucher_date)`, `(posted, -voucher_date)`
  on vouchers and voucher lines.
- Verified with `EXPLAIN QUERY PLAN`: voucher list, account ledger, stock card
  and purchase order list all seek an index instead of scanning.
- Migrations applied to the dev database and to live MySQL.
- Standing rule written into `docs/DATABASE_RULES.md` and `CLAUDE.md`: every new
  table ships its indexes in the migration that creates it.

### Open

- Auto-deploy (`push` → live) is not active: cPanel reports `deployable: 0`
  because 136 tracked files under `staticfiles/` are modified in the checkout.
  Until that is cleaned, redeploys go through `VersionControl/update` +
  restart.
- cPanel password was shared in plaintext during setup; rotate it.
- Local dev Postgres has a stray `admin` superuser from a probe run; delete with
  `python manage.py shell -c "from django.contrib.auth import get_user_model as g; g().objects.filter(username='admin').delete()"`.
