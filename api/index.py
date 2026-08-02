import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django

django.setup()
from django.core.management import call_command

try:
    call_command("migrate", interactive=False)
except Exception:
    call_command("migrate", "finance", "0007", fake=True, interactive=False)
    call_command("migrate", interactive=False)

call_command("collectstatic", interactive=False, verbosity=0)

from config.wsgi import application

app = application
