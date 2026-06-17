from .base import *  # noqa: F403

DEBUG = env_bool("DEBUG", default=True)  # noqa: F405
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,[::1],testserver", cast=Csv())  # noqa: F405

if env_bool("USE_SQLITE", default=True):  # noqa: F405
    DATABASES = {  # noqa: F405
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }
