# Deployment Runbook — cPanel Shared Hosting (LiteSpeed + CloudLinux)

Read this before any "make it live" request. Host-specific values live in
`deploy/cpanel.config` (git-ignored, see `deploy/cpanel.config.example`), so
switching hosting accounts means editing that one file, not this document.

## Topology

| Piece | Location |
|---|---|
| Passenger entrypoint | `$APP_ROOT/passenger_wsgi.py` (outside the checkout) |
| Code (git clone) | `$CHECKOUT` |
| Virtualenv | `$HOME/virtualenv/<app-root>/<python-version>` |
| Static files | `$STATIC_ROOT` (outside the checkout) |
| Web server config | `$HOME/public_html/.htaccess` |
| Database | MySQL, credentials in `$CHECKOUT/.env` |

The entrypoint is kept **outside** the git checkout so deploys never overwrite
it, and because the CloudLinux selector rewrites `passenger_wsgi.py` inside any
directory it manages.

## Database: MySQL, not PostgreSQL

The project targets PostgreSQL, and cPanel offers it here, but the host runs
**PostgreSQL 10.23** while Django 5.2 requires 14 or later
(`NotSupportedError: PostgreSQL 14 or later is required (found 10.23)`).
Live therefore runs on **MySQL** through PyMySQL. Do not spend time trying to
switch it again without first checking the server's PostgreSQL version.

## Constraints on this class of host

0. **`manage.py` defaults to `config.settings.local`**, whose `USE_SQLITE`
   default is `True`. Any deploy command that forgets
   `DJANGO_SETTINGS_MODULE=config.settings.production` silently migrates and
   seeds `db.sqlite3` inside the checkout while the served app uses the real
   database — the deploy reports success and changes nothing. The deploy script
   exports it; keep it that way, and trust the `TARGET DB:` line it logs.
1. **SSH shell is disabled** (`Shell access is not enabled on your account!`).
   Everything is done through the cPanel API over HTTPS.
2. **LiteSpeed only routes to the app** when `.htaccess` carries
   `PassengerAppType wsgi` **and** `PassengerStartupFile`. The stock CloudLinux
   block (AppRoot/BaseURI/Python only) silently serves the parking page or 404.
3. **The CloudLinux selector owns the virtualenv.** Passenger boots the app with
   that interpreter, so packages must be installed into it — a hand-built venv
   is never on its path, and `python3 -m venv` fails there anyway
   (`Unable to symlink '/usr/bin/python3'`; needs `--copies`).
4. **`Fileman/save_file_content` rewrites files as CRLF.** Use
   `Fileman/upload_files` for anything inside the git checkout, or the working
   tree goes dirty and cPanel sets `deployable: 0`.
5. **`VersionControl/update` only pulls when `branch` is passed.** Without it the
   call succeeds and does nothing.

## cPanel API access

```bash
# 1. Log in, keep the cookie jar, capture the security token.
curl -sS -c cpj.txt -d "user=$CPANEL_USER" --data-urlencode "pass=$CPANEL_PASS" \
  "https://$CPANEL_HOST:2083/login/?login_only=1&goto_uri=%2F"
# -> {"security_token":"/cpsessXXXXXXXXXX", ...}

# 2. UAPI calls hang off that token.
B="https://$CPANEL_HOST:2083$TOKEN/execute"
curl -sS -b cpj.txt "$B/VersionControl/retrieve"
```

Sessions expire in roughly 15–30 minutes; re-login when responses stop being
JSON. On Git Bash, export `MSYS2_ARG_CONV_EXCL='*'` and `MSYS_NO_PATHCONV=1`
first or curl arguments starting with `/` get mangled into Windows paths.

### CloudLinux Python selector

Not exposed through UAPI. Its CGI takes **form fields**, with nested arguments
in `params[key]=value` form (a JSON `params` blob is rejected):

```bash
CGI="https://$CPANEL_HOST:2083$TOKEN/3rdparty/cloudlinux/cloudlinux-selector.cgi?cgiaction=sendRequest"
curl -sS -b cpj.txt -X POST "$CGI" \
  -d 'command=cloudlinux-selector' -d 'method=get' \
  --data-urlencode 'params[interpreter]=python'
```

Useful methods: `get`, `create`, `destroy`, `start`, `stop`, `restart`,
`install-modules` (takes `params[requirements-file]`).

## First-time setup

1. **Database** — `Mysql/create_database`, `Mysql/create_user`,
   `Mysql/set_privileges_on_database` (`privileges=ALL PRIVILEGES`).
2. **Clone** — `VersionControl/create` with `type=git`,
   `repository_root=$CHECKOUT`, and
   `source_repository={"url":"<repo>"}` (the key is `url`, not `remote_url`).
3. **Python app** — selector `create` with `interpreter=python`,
   `app-root=<app dir>`, `app-uri=/`, `version=<3.12>`,
   `startup-file=passenger_wsgi.py`, `domain=<domain>`.
4. **Dependencies** — selector `install-modules` pointing at
   `$CHECKOUT/requirements-cpanel.txt`.
5. **Entrypoint** — upload `deploy/cpanel/passenger_wsgi.py` to the app root
   (it overwrites the selector's "It works!" stub).
6. **`.env`** — upload to `$CHECKOUT/.env`; see `.env.cpanel.example`. Must set
   `STATIC_ROOT` outside the checkout.
7. **`.htaccess`** — upload `deploy/cpanel/htaccess` to `$HOME/public_html`,
   with the paths substituted.
8. **Migrate and seed** — see below.

## Routine redeploy

```bash
B="https://$CPANEL_HOST:2083$TOKEN/execute"
curl -sS -b cpj.txt --data-urlencode "repository_root=$CHECKOUT" -d 'branch=master' "$B/VersionControl/update"
curl -sS -b cpj.txt --data-urlencode "repository_root=$CHECKOUT" "$B/VersionControlDeployment/create"
```

`VersionControlDeployment/create` runs `.cpanel.yml`, which calls
`scripts/cpanel_deploy.sh` (pip install, migrate, collectstatic, seed, restart).
Watch it with `VersionControlDeployment/retrieve`; read the build log with
`Fileman/get_file_content` on the returned `log_path`.

If the response is `{"data": null}` and `retrieve` shows no new deploy, the repo
is not deployable — check `VersionControl/retrieve` for `deployable: 0`, which
means the working tree is dirty (see constraint 4).

**Restart without a deploy:** write `$APP_ROOT/tmp/restart.txt`, or call the
selector's `restart`. A running process does *not* pick up an edited
`passenger_wsgi.py` until one of those happens.

## Running a management command without shell access

There is no remote exec on these accounts. To run a one-off `migrate`, `seed` or
`collectstatic`, temporarily wrap the entrypoint so it runs the command once at
process start, guarded by a marker file, and writes output to a log:

```python
if not os.path.exists(MARKER):
    with open(LOG, "a") as fh:
        django.setup()
        call_command("migrate", no_input=True, stdout=fh, stderr=fh)
        open(MARKER, "w").write("done\n")
```

Restart, hit any URL, read the log, then upload the clean entrypoint again.

## Seeding policy for this project

Live data is **users, roles and permissions only**:

```
python manage.py seed core access_control
python manage.py ensure_superuser
```

Never run `seed_demo` or the full `seed all` against live — those add
inventory, suppliers, customers and other master data.

## Debugging a 500

`DEBUG` stays off. Point `DJANGO_SETTINGS_MODULE` at a small overlay module in
the app root that imports `config.settings.production` and adds a `LOGGING`
config with a `FileHandler`, then read that file. Do not flip `DEBUG=True` on a
public domain.

## TLS certificate (Let's Encrypt, manual ACME)

The account has **no AutoSSL feature**, and the *Namecheap SSL* plugin only
installs certificates bought from Namecheap. The certificate in place is issued
from Let's Encrypt with a patched `acme-tiny`, using HTTP-01 validation with the
challenge files pushed to the document root through the cPanel API.

Everything needed lives in `deploy/ssl/` (git-ignored): `account.key` (ACME
account — keep it, reuse it), `flourorbit.key`, `flourorbit.csr`,
`acme_tiny.py`, `upload_challenge.sh`.

Two patches to stock `acme-tiny`, both needed on Windows:

1. An `ACME_UPLOAD_HOOK` env var — after writing a challenge file it runs the
   hook, which uploads that file to
   `public_html/.well-known/acme-challenge/` before validation is triggered.
2. The SAN regex accepts CRLF and OpenSSL 3's trailing space; otherwise only the
   first domain is picked up and the order fails with *"CSR does not specify
   same identifiers as Order"*.

`upload_challenge.sh` logs in fresh each call into its own cookie jar, and runs
paths through `cygpath -w` — with `MSYS_NO_PATHCONV=1` set, curl cannot open
POSIX-style paths and the upload fails silently with a login page.

### Renewal (certificate expires 2026-11-29)

```bash
cd deploy/ssl
export MSYS2_ARG_CONV_EXCL='*' MSYS_NO_PATHCONV=1
export ACME_UPLOAD_HOOK='"C:/Program Files/Git/bin/bash.exe" <abs path>/upload_challenge.sh'
mkdir -p acme_dir
python acme_tiny.py --account-key account.key --csr flourorbit.csr \
  --acme-dir acme_dir --contact mailto:smwaseemt@gmail.com > flourorbit.crt
```

Split the chain (first block is the leaf, the rest is the CA bundle) and
install:

```bash
curl -sS -b jar.txt -X POST "https://$CPANEL_HOST:2083$TOKEN/execute/SSL/install_ssl" \
  --data-urlencode "domain=$DOMAIN" --data-urlencode "cert@leaf.pem" \
  --data-urlencode "key@flourorbit.key" --data-urlencode "cabundle@bundle.pem"
```

Then check `https://$DOMAIN/` with curl **without** `-k`. Set
`SECURE_SSL_REDIRECT=True` in the server `.env` so Django 301s HTTP to HTTPS.

## Keeping deployment enabled

cPanel sets `deployable: 0` whenever the checkout's working tree is not clean,
and then `VersionControlDeployment/create` returns `{"data": null}` and does
nothing. Anything a deploy writes inside the checkout must therefore be
untracked and git-ignored: `staticfiles/` (collected output — `STATIC_ROOT`
points outside the checkout anyway) and `tmp/` (the Passenger restart trigger,
which now lives under the app root instead).

If a pull reports *"local changes would be overwritten"*, the named files are
the culprits. Restore them with the committed bytes — `git show <commit>:<path>`
— and upload through `Fileman/upload_files`; do **not** upload the Windows
working copy, whose CRLF endings make git see a difference.

## Known gaps on the current account

- No AutoSSL; the certificate is renewed by hand (see above).
- PostgreSQL is too old to use, so production runs on MySQL while local
  development runs on PostgreSQL.
