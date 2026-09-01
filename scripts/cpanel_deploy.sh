#!/usr/bin/env bash
# Deploy tasks run by cPanel Git Version Control (see .cpanel.yml).
# cPanel performs the git pull itself; this script only builds and migrates.
# Each .cpanel.yml task runs in its own shell, so exports there do not reach
# this script - override these by editing the defaults, not the yml.
set -o errexit

# The git checkout.
APPROOT="${APPROOT:-$HOME/industrial_erp}"
# The Passenger application root, deliberately outside the checkout so deploys
# never overwrite passenger_wsgi.py and its restart trigger never dirties the
# working tree.
PASSENGER_ROOT="${PASSENGER_ROOT:-$HOME/erp_app}"
# Owned by the CloudLinux Python selector; Passenger boots the app with it.
VENV="${VENV:-$HOME/virtualenv/erp_app/3.12}"

cd "$APPROOT"

if [ ! -x "$VENV/bin/pip" ]; then
    echo "No virtualenv at $VENV; create the Python app in cPanel first." >&2
    exit 1
fi

"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r requirements-cpanel.txt

# Say which database is being migrated; a stale .env is otherwise silent.
"$VENV/bin/python" -c "import django; django.setup(); from django.conf import settings; d = settings.DATABASES['default']; print('TARGET DB:', d['ENGINE'], d['NAME'], d.get('HOST'))"

"$VENV/bin/python" manage.py migrate --no-input
"$VENV/bin/python" manage.py collectstatic --no-input
# Live data is users, roles and permissions only; no demo/master seeding.
"$VENV/bin/python" manage.py seed core access_control
"$VENV/bin/python" manage.py ensure_superuser

mkdir -p "$PASSENGER_ROOT/tmp"
touch "$PASSENGER_ROOT/tmp/restart.txt"
