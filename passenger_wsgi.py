"""Passenger entrypoint for cPanel "Setup Python App" hosting.

public_html/.htaccess points PassengerPython at the deploy virtualenv, so this
module only has to expose the WSGI application.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.wsgi import application  # noqa: E402
