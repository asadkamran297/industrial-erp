"""Run Django migrations against the production database.

Loads DATABASE_URL from .env.vercel (pulled via `vercel env pull`) and
invokes `manage.py migrate` with production settings. Usage:

    python scripts/migrate_live.py
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_database_url() -> str:
    env_file = BASE_DIR / ".env.vercel"
    if not env_file.exists():
        raise SystemExit(".env.vercel not found. Run: npx vercel env pull .env.vercel --environment=production --yes")
    for line in env_file.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("DATABASE_URL not found in .env.vercel")


def main() -> None:
    url = load_database_url()
    host = url.split("@")[-1].split("/")[0]
    print(f"Migrating live database at: {host}")
    os.environ["DATABASE_URL"] = url
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
    sys.path.insert(0, str(BASE_DIR))
    import django

    django.setup()
    from django.core.management import call_command

    call_command("migrate", interactive=False)
    print("Done.")


if __name__ == "__main__":
    main()
