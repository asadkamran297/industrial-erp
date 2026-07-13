#!/usr/bin/env bash
# Render build script
set -o errexit

pip install -r requirements-render.txt
python manage.py collectstatic --no-input
python manage.py migrate
