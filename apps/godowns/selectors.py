"""Reads. Nothing here writes."""

from django.db.models import QuerySet

from apps.core.constants import STATUS_ACTIVE

from .models import Godown


def godowns() -> QuerySet[Godown]:
    return Godown.objects.all()


def active_godowns() -> QuerySet[Godown]:
    return godowns().filter(status=STATUS_ACTIVE)


def default_godown() -> Godown | None:
    """What a new document opens on when the operator has not chosen yet."""
    return active_godowns().first()
