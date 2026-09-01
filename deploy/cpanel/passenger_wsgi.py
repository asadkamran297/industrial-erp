"""Passenger entrypoint for cPanel/LiteSpeed hosting.

Upload this to APP_ROOT (outside the git checkout) so deploys never overwrite
it. See docs/DEPLOYMENT.md.
"""

import os
import sys

CHECKOUT = "/home/flouruge/industrial_erp"

sys.path.insert(0, CHECKOUT)
os.chdir(CHECKOUT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.wsgi import application  # noqa: E402
