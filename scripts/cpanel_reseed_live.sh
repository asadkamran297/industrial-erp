#!/usr/bin/env bash
# One-off: dump the live database, wipe its data, and load the mill masters
# plus the demo book. Wire it in for a single deploy by pointing .cpanel.yml at
# this script with RESEED_LIVE=1, then revert to cpanel_deploy.sh.
set -o errexit

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
APPROOT="${APPROOT:-$HOME/industrial_erp}"
PASSENGER_ROOT="${PASSENGER_ROOT:-$HOME/erp_app}"
VENV="${VENV:-$HOME/virtualenv/erp_app/3.12}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"

if [ "${RESEED_LIVE:-0}" != "1" ]; then
    echo "RESEED_LIVE is not 1; refusing to wipe anything." >&2
    exit 1
fi

cd "$APPROOT"
"$VENV/bin/pip" install -r requirements-cpanel.txt >/dev/null

eval "$("$VENV/bin/python" manage.py shell -c "
from django.conf import settings
d = settings.DATABASES['default']
print('DB_ENGINE=%r' % d['ENGINE'])
print('DB_NAME=%r' % d['NAME'])
print('DB_USER=%r' % d['USER'])
print('DB_PASSWORD=%r' % d['PASSWORD'])
print('DB_HOST=%r' % (d.get('HOST') or 'localhost'))
")"
echo "TARGET DB: $DB_ENGINE $DB_NAME $DB_HOST"
case "$DB_ENGINE" in *mysql*) ;; *) echo "not mysql; abort" >&2; exit 1;; esac

mkdir -p "$BACKUP_DIR"
DUMP="$BACKUP_DIR/${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql.gz"
MYSQL_PWD="$DB_PASSWORD" mysqldump --single-transaction --quick -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" | gzip > "$DUMP"
echo "DUMP: $DUMP ($(du -h "$DUMP" | cut -f1))"

"$VENV/bin/python" manage.py migrate --no-input
"$VENV/bin/python" manage.py flush --no-input
"$VENV/bin/python" manage.py migrate --no-input
"$VENV/bin/python" manage.py seed
"$VENV/bin/python" manage.py ensure_superuser
"$VENV/bin/python" manage.py seed_demo
"$VENV/bin/python" manage.py collectstatic --no-input

mkdir -p "$PASSENGER_ROOT/tmp"
touch "$PASSENGER_ROOT/tmp/restart.txt"
echo "Reseed complete."
