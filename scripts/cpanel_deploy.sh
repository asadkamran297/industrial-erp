#!/usr/bin/env bash
# Deploy tasks run by cPanel Git Version Control (see .cpanel.yml).
# cPanel performs the git pull itself; this script only builds and migrates.
set -o errexit

APPROOT="${APPROOT:-$HOME/industrial_erp}"
# The CloudLinux Python selector owns this virtualenv and Passenger boots the
# app with its interpreter, so install into it rather than building our own.
VENV="${VENV:-$HOME/virtualenv/industrial_erp/3.12}"

cd "$APPROOT"

if [ ! -x "$VENV/bin/pip" ]; then
    echo "No virtualenv at $VENV; create the Python app in cPanel first." >&2
    exit 1
fi

"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r requirements-cpanel.txt

"$VENV/bin/python" manage.py migrate --no-input
"$VENV/bin/python" manage.py collectstatic --no-input
# Live data is users, roles and permissions only; no demo/master seeding.
"$VENV/bin/python" manage.py seed core access_control
"$VENV/bin/python" manage.py ensure_superuser

mkdir -p "$APPROOT/tmp"
touch "$APPROOT/tmp/restart.txt"
