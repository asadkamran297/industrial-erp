from decouple import Csv

from .base import *  # noqa: F403

DEBUG = False

if config("VERCEL", default="", cast=str):  # noqa: F405
    STATIC_ROOT = "/tmp/staticfiles"

ALLOWED_HOSTS = [
    ".railway.app",
    ".onrender.com",
    ".pythonanywhere.com",
    ".vercel.app",
    "localhost",
]
CSRF_TRUSTED_ORIGINS = [
    "https://*.railway.app",
    "https://*.onrender.com",
    "https://*.pythonanywhere.com",
    "https://*.vercel.app",
]

# Render injects the external hostname at runtime.
RENDER_EXTERNAL_HOSTNAME = config("RENDER_EXTERNAL_HOSTNAME", default="")  # noqa: F405
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# Custom domains (cPanel and friends) come from the environment.
for host in config("ALLOWED_HOSTS", default="", cast=Csv()):  # noqa: F405
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)
    origin = f"https://{host.lstrip('.')}"
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = False  # Railway handles HTTPS termination
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
