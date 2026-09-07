"""Writes."""

from django.db import transaction

from apps.core.constants import STATUS_ACTIVE, STATUS_INACTIVE

from .models import Godown


def _stamp(instance, user):
    if user is not None and getattr(user, "is_authenticated", False):
        if instance.pk is None:
            instance.created_by = user
        instance.updated_by = user
    return instance


@transaction.atomic
def save_godown(godown: Godown, user=None) -> Godown:
    godown.full_clean(validate_unique=False)
    _stamp(godown, user)
    godown.save()
    return godown


@transaction.atomic
def toggle_status(godown: Godown, user=None) -> Godown:
    """Godowns are never deleted: documents point at them for good."""
    godown.status = STATUS_INACTIVE if godown.status == STATUS_ACTIVE else STATUS_ACTIVE
    _stamp(godown, user)
    godown.save(update_fields=["status", "updated_by", "updated_at"])
    return godown
