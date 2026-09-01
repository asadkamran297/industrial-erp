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

### Live — PostgreSQL attempt, and auto-deploy fixed

- Tried moving live to PostgreSQL (the project targets it). The host has the
  cPanel feature and the service runs, but it is **PostgreSQL 10.23** and
  Django 5.2 requires 14+. Reverted; live stays on MySQL. Recorded in
  `docs/DEPLOYMENT.md` so it is not retried blindly.
- Found why every deploy looked successful but changed nothing: `manage.py`
  defaults to `config.settings.local`, whose `USE_SQLITE` default is `True`, so
  deploy migrations and seeds were going into `db.sqlite3` inside the checkout
  while the served app used the real database. The deploy script now exports
  `DJANGO_SETTINGS_MODULE=config.settings.production` and logs a `TARGET DB:`
  line (commits `4c6889a`, `cdad035`).
- Auto-deploy is **working now**. `deployable` was `0` because the checkout was
  never clean: `staticfiles/` was tracked and rewritten by `collectstatic`, and
  the deploy script touched `tmp/restart.txt` inside the checkout. Both are now
  untracked/ignored and the restart trigger moved to the app root (commits
  `60e8df6`, `42830dc`, `4f01df3`).
- A full `VersionControl/update` + `VersionControlDeployment/create` cycle now
  runs pip install, migrate, collectstatic, seed and restart, and reports
  `TARGET DB: django.db.backends.mysql`.
- The empty `flouruge_erp` and `flouruge_pgtest` PostgreSQL databases and the
  `flouruge_app` role left by the attempt were dropped; the account now has no
  PostgreSQL objects. Live MySQL and the site were verified unaffected.

### Local — demo seeder

- `seed_demo` rewritten to build 50 of each: customers, employees with salary
  components and payroll, purchase orders, supplier bills, sales and vouchers
  (commit `4a65f74`). Purchase and sale documents go through the real services,
  so stock, the item ledger and the general ledger move as they do on screen.
- Verified on a fresh database: 452 records on the first run, 0 on the second
  (idempotent), GL lines balance, no negative stock, stock on hand equals
  receipts less sales.
- Two things the seeder had to work around, both by design in the app: the
  first sale to a customer rewrites `customer_code` to their chart-of-accounts
  code, so demo customers key on their email instead; and a voucher must be
  headed by a cash/bank leaf of the chart, with both sides on its lines.
- `SEED_DEMO=1` in `.cpanel.yml` now makes a deploy seed the demo book
  (commit `46dc3cd`). **Still set — take it back out after the live seeding.**

### Open

- **Demo data is not on live yet.** The seeder is pushed and the deploy is set
  to run it, but the server's brute-force protection blocked this machine's IP
  from every management port (2082/2083/2087/2096 and SSH 21098) after the
  day's logins. Port 443 is unaffected and the site is up. Retry the deploy
  once the block clears, then revert `SEED_DEMO=1` in `.cpanel.yml`.
- cPanel password was shared in plaintext during setup; rotate it.
- Local dev Postgres has a stray `admin` superuser from a probe run; delete with
  `python manage.py shell -c "from django.contrib.auth import get_user_model as g; g().objects.filter(username='admin').delete()"`.
