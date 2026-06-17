# Industrial ERP / MIS Portal

Production-grade Django foundation for a custom Industrial ERP and MIS portal. The user-facing system is a clean custom portal; Django Admin is retained only for developer and emergency backend use.

## Stack

- Python 3.12+
- Django 5.2 LTS
- PostgreSQL ready, SQLite enabled for local first run
- Django Templates
- Tailwind CSS CDN foundation with static CSS overrides
- HTMX
- Alpine.js for small UI state

## Quick Start

```powershell
.\.venv\Scripts\activate
python -m pip install -r requirements\base.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/accounts/login/`.

## Environment

Copy `.env.example` to `.env` and adjust values for production. Local settings default to SQLite with `USE_SQLITE=True`; set it to `False` to use PostgreSQL. You can configure PostgreSQL with either `DATABASE_URL` or the individual `DB_*` variables.

## Main Apps

- `apps.accounts`: custom user model, username/email login
- `apps.core`: base model, soft delete, system branding settings
- `apps.portal`: authenticated dashboard and portal layout
- `apps.design_system`: reusable component home for future UI patterns
