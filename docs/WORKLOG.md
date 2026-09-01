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

### Open

- Auto-deploy (`push` → live) is not active: cPanel reports `deployable: 0`
  because 136 tracked files under `staticfiles/` are modified in the checkout.
  Until that is cleaned, redeploys go through `VersionControl/update` +
  restart.
- No TLS certificate — the account has no AutoSSL feature. Install the free
  PositiveSSL from cPanel → *Namecheap SSL*.
- cPanel password was shared in plaintext during setup; rotate it.
- Local dev Postgres has a stray `admin` superuser from a probe run; delete with
  `python manage.py shell -c "from django.contrib.auth import get_user_model as g; g().objects.filter(username='admin').delete()"`.
