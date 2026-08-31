"""Passenger entrypoint for cPanel "Setup Python App" hosting.

cPanel registers the app against the system interpreter, which cannot see the
virtualenv the deploy script builds, so re-exec into the venv interpreter
before Django is imported.
"""

import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
INTERPRETER = os.environ.get(
    "PASSENGER_PYTHON",
    os.path.join(os.path.expanduser("~"), "virtualenv", "industrial_erp", "bin", "python"),
)

if os.path.exists(INTERPRETER) and os.path.realpath(sys.executable) != os.path.realpath(INTERPRETER):
    os.execl(INTERPRETER, INTERPRETER, *sys.argv)

sys.path.insert(0, APP_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.wsgi import application  # noqa: E402
