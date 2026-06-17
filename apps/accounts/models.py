from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.constants import RECORD_STATUS_CHOICES, STATUS_ACTIVE

from .managers import UserManager


class User(AbstractUser):
    class UserType(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        OPERATOR = "operator", "Operator"
        VIEWER = "viewer", "Viewer"

    name = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True, null=True, unique=True)
    employee = models.ForeignKey("hr.Employee", null=True, blank=True, related_name="users", on_delete=models.SET_NULL)
    phone = models.CharField(max_length=40, blank=True, unique=True, null=True)
    whatsapp = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    cnic = models.CharField(max_length=30, blank=True)
    avatar = models.ImageField(upload_to="users/avatars/", blank=True)
    designation = models.CharField(max_length=120, blank=True)
    user_type = models.CharField(max_length=20, choices=UserType.choices, default=UserType.VIEWER)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)
    last_login_timestamp = models.DateTimeField(null=True, blank=True)
    last_password_changed = models.DateTimeField(null=True, blank=True)
    temp_pwd = models.CharField(max_length=255, blank=True)

    objects = UserManager()

    class Meta:
        db_table = "iams_users"

    def save(self, *args, **kwargs):
        if self.email == "":
            self.email = None
        if self.phone == "":
            self.phone = None
        super().save(*args, **kwargs)

    def display_name(self) -> str:
        return self.name or self.get_full_name() or self.username
