"""Where stock physically sits.

A godown is its own module rather than a column on a document because more than
one module needs it -- grinding draws wheat from one, the product ledger records
which one a movement happened in, and sales will ship out of one -- and none of
them should own it.
"""

from django.db import models

from apps.core.constants import (
    GODOWN_STATUS_CHOICES,
    GODOWN_TYPE_CHOICES,
    GODOWN_TYPE_STORE,
    STATUS_ACTIVE,
)
from apps.core.models import BaseModel


class Godown(BaseModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=160)
    godown_type = models.CharField(max_length=20, choices=GODOWN_TYPE_CHOICES, default=GODOWN_TYPE_STORE)
    location = models.CharField(max_length=200, blank=True)
    incharge = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=GODOWN_STATUS_CHOICES, default=STATUS_ACTIVE)
    remarks = models.CharField(max_length=240, blank=True)

    class Meta:
        db_table = "godowns"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(deleted_at__isnull=True),
                name="godown_unique_code",
            ),
        ]
        indexes = [
            # Every picker on every document reads exactly this.
            models.Index(fields=["status", "code"], name="godown_status_code_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
