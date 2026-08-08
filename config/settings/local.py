from .base import *  # noqa: F403

DEBUG = env_bool("LOCAL_DEBUG", default=True)  # noqa: F405
ALLOWED_HOSTS = ["*"]

# The dev server runs over plain HTTP on a LAN IP, where browsers ignore COOP and
# log a console warning. Production keeps Django's default same-origin policy.
SECURE_CROSS_ORIGIN_OPENER_POLICY = None

if env_bool("USE_SQLITE", default=True):  # noqa: F405
    DATABASES = {  # noqa: F405
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }
