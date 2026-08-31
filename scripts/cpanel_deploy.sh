#!/usr/bin/env bash
# Deploy/redeploy the ERP on cPanel shared hosting.
# Run from the app root with the cPanel virtualenv already activated.
set -o errexit

git pull --ff-only origin master
pip install -r requirements-cpanel.txt
python manage.py migrate --no-input
python manage.py collectstatic --no-input
python manage.py seed core access_control
python manage.py ensure_superuser
touch tmp/restart.txt
