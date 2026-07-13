from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update a superuser from environment variables (idempotent)."

    def handle(self, *args, **options):
        from decouple import config

        username = config("DJANGO_SUPERUSER_USERNAME", default="")
        password = config("DJANGO_SUPERUSER_PASSWORD", default="")
        email = config("DJANGO_SUPERUSER_EMAIL", default="")

        if not username or not password:
            self.stdout.write(
                "DJANGO_SUPERUSER_USERNAME/PASSWORD not set; skipping superuser creation."
            )
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        user.email = email or user.email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} superuser '{username}'."))
