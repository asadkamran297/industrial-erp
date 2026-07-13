from django.contrib.auth import get_user_model

from apps.core.constants import STATUS_ACTIVE

from .models import UserAssignment

User = get_user_model()


def get_user_permission_codes(user: User) -> set[str]:
    if not user.is_authenticated:
        return set()
    if user.is_superuser:
        return {"*"}

    permission_codes = UserAssignment.objects.filter(
        user=user,
        deleted_at__isnull=True,
        status=STATUS_ACTIVE,
        role__deleted_at__isnull=True,
        role__status=STATUS_ACTIVE,
        role__permission_links__permission__deleted_at__isnull=True,
        role__permission_links__permission__status=STATUS_ACTIVE,
    ).values_list("role__permission_links__permission__code", flat=True)

    return {code for code in permission_codes if code}


def user_has_permission(user: User, permission_code: str | None) -> bool:
    # Fail closed: a view that cannot resolve a permission code must not be
    # silently public. Every guarded view sets ``page``; a missing code is a
    # configuration bug, so deny rather than grant.
    if not permission_code:
        return False
    permission_codes = get_user_permission_codes(user)
    return "*" in permission_codes or permission_code in permission_codes
