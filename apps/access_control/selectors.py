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
        status=STATUS_ACTIVE,
        role__status=STATUS_ACTIVE,
        role__permission_links__permission__status=STATUS_ACTIVE,
    ).values_list("role__permission_links__permission__code", flat=True)

    return {code for code in permission_codes if code}


def user_has_permission(user: User, permission_code: str | None) -> bool:
    if not permission_code:
        return True
    permission_codes = get_user_permission_codes(user)
    return "*" in permission_codes or permission_code in permission_codes
