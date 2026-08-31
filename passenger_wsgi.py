"""Passenger entrypoint for cPanel "Setup Python App" hosting.

cPanel points Passenger at this file; it loads the same WSGI application the
rest of the deployments use.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.wsgi import application  # noqa: E402
