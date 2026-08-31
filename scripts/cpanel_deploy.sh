#!/usr/bin/env bash
# Deploy tasks run by cPanel Git Version Control (see .cpanel.yml).
# cPanel performs the git pull itself; this script only builds and migrates.
set -o errexit

APPROOT="${APPROOT:-$HOME/industrial_erp}"
VENV="$HOME/virtualenv/industrial_erp"

cd "$APPROOT"

# CloudLinux blocks symlinking the interpreter, so the venv copies it.
PYBIN="${PYBIN:-/usr/bin/python3}"
for candidate in /opt/alt/python313/bin/python3 /opt/alt/python312/bin/python3 /opt/alt/python311/bin/python3; do
    [ -x "$candidate" ] && PYBIN="$candidate" && break
done
"$PYBIN" -V

# A half-built venv from a failed run has bin/python but no pip; rebuild it.
if [ ! -x "$VENV/bin/pip" ]; then
    rm -rf "$VENV"
    "$PYBIN" -m venv --copies "$VENV"
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
