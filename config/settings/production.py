from .base import *  # noqa: F403

DEBUG = False

ALLOWED_HOSTS = [".railway.app", ".onrender.com", ".pythonanywhere.com", "localhost"]
CSRF_TRUSTED_ORIGINS = [
    "https://*.railway.app",
    "https://*.onrender.com",
    "https://*.pythonanywhere.com",
]

# Render injects the external hostname at runtime.
RENDER_EXTERNAL_HOSTNAME = config("RENDER_EXTERNAL_HOSTNAME", default="")  # noqa: F405
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = False  # Railway handles HTTPS termination
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
