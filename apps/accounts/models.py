from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class UserType(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        OPERATOR = "operator", "Operator"
        VIEWER = "viewer", "Viewer"

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    avatar = models.ImageField(upload_to="users/avatars/", blank=True)
    designation = models.CharField(max_length=120, blank=True)
    user_type = models.CharField(max_length=20, choices=UserType.choices, default=UserType.VIEWER)

    objects = UserManager()

    def display_name(self) -> str:
        return self.get_full_name() or self.username
