from django.conf import settings
from django.db import models


class NavFavourite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="nav_favourites", on_delete=models.CASCADE)
    href = models.CharField(max_length=255)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "portal_nav_favourites"
        ordering = ("position", "id")
        constraints = [models.UniqueConstraint(fields=("user", "href"), name="uq_portal_nav_favourite")]
        indexes = [models.Index(fields=("user", "position"), name="ix_portal_nav_fav_user_pos")]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.href}"
