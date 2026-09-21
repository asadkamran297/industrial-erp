from django.db import transaction
from django.db.models import Max

from .models import NavFavourite


@transaction.atomic
def toggle_favourite(user, href: str) -> bool:
    """Add or remove ``href`` from the user's favourites; returns the new state."""
    existing = NavFavourite.objects.filter(user=user, href=href).first()
    if existing:
        existing.delete()
        return False
    last = NavFavourite.objects.filter(user=user).aggregate(m=Max("position"))["m"]
    NavFavourite.objects.create(user=user, href=href, position=(last or 0) + 1)
    return True
