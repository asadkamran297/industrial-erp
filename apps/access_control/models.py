from django.conf import settings
from django.db import models

from apps.core.constants import RECORD_STATUS_CHOICES, STATUS_ACTIVE
from apps.core.models import BaseModel


class Role(BaseModel):
    title = models.CharField(max_length=120, unique=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "iams_roles"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class Permission(BaseModel):
    title = models.CharField(max_length=160, unique=True)
    code = models.CharField(max_length=120, unique=True)
    seq = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "iams_permissions"
        ordering = ["seq", "title"]

    def __str__(self) -> str:
        return self.title


class RolePermission(models.Model):
    permission = models.ForeignKey(Permission, related_name="role_links", on_delete=models.CASCADE, db_column="iams_permission_id")
    role = models.ForeignKey(Role, related_name="permission_links", on_delete=models.CASCADE, db_column="iams_role_id")

    class Meta:
        db_table = "iams_permission_role"
        unique_together = ("permission", "role")

    def __str__(self) -> str:
        return f"{self.role} - {self.permission}"


class UserAssignment(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="assignments", on_delete=models.CASCADE, db_column="iams_user_id")
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, related_name="user_assignments", on_delete=models.SET_NULL, db_column="org_organization_id"
    )
    branch = models.ForeignKey(
        "organizations.Branch", null=True, blank=True, related_name="user_assignments", on_delete=models.SET_NULL, db_column="org_branch_id"
    )
    role = models.ForeignKey(Role, related_name="user_assignments", on_delete=models.PROTECT, db_column="iams_role_id")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "iams_user_assignments"
        ordering = ["user_id", "-is_primary", "-start_date"]

    def __str__(self) -> str:
        return f"{self.user} - {self.role}"
