#!/usr/bin/env bash
# One-off: build the demo database (flouruge_erpdemo) with a full migrate and
# the demo book, leaving the live database alone.
#
# Wire it in for a single deploy by pointing .cpanel.yml at this script instead
# of cpanel_deploy.sh, then revert.
#
# DB_NAME alone does not work: config/settings/base.py reads DATABASE_URL first
# and ignores DB_* whenever it is set, which is how an earlier attempt seeded
# the live database instead. So derive the demo URL from the live one and hand
# it over as DATABASE_URL.
set -o errexit

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
APPROOT="${APPROOT:-$HOME/industrial_erp}"
VENV="${VENV:-$HOME/virtualenv/erp_app/3.12}"
LIVE_DB="${LIVE_DB:-flouruge_erp}"
DEMO_DB="${DEMO_DB:-flouruge_erpdemo}"

cd "$APPROOT"

live_url="$(sed -n 's/^DATABASE_URL=//p' "$APPROOT/.env" | head -n 1 | tr -d '\r"'"'")"
if [ -z "$live_url" ]; then
    echo "No DATABASE_URL in $APPROOT/.env; refusing to guess." >&2
    exit 1
fi

case "$live_url" in
    */"$LIVE_DB")
        DATABASE_URL="${live_url%/$LIVE_DB}/$DEMO_DB"
        ;;
    *)
        echo "DATABASE_URL does not end in /$LIVE_DB; refusing to rewrite it." >&2
        exit 1
        ;;
esac
export DATABASE_URL

# Last line of defence: never run against the live database name.
"$VENV/bin/python" manage.py shell -c "
from django.conf import settings
name = settings.DATABASES['default']['NAME']
print('TARGET DB:', name)
assert name == '$DEMO_DB', 'refusing to seed %s' % name
"

"$VENV/bin/python" manage.py migrate --no-input
"$VENV/bin/python" manage.py seed
# seed_demo stamps its documents with a user, so the superuser has to exist
# before it runs, not after.
"$VENV/bin/python" manage.py ensure_superuser
"$VENV/bin/python" manage.py seed_demo

echo "Demo database $DEMO_DB is ready."
