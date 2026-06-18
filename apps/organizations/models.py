from django.db import models

from apps.core.constants import RECORD_STATUS_CHOICES, STATUS_ACTIVE
from apps.core.models import BaseModel


class Organization(BaseModel):
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL, db_column="parent_id")
    title = models.CharField(max_length=180)
    code = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "org_organizations"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class Branch(BaseModel):
    organization = models.ForeignKey(Organization, related_name="branches", on_delete=models.PROTECT, db_column="org_organization_id")
    city = models.ForeignKey("configurations.City", null=True, blank=True, related_name="branches", on_delete=models.SET_NULL, db_column="conf_city_id")
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL, db_column="parent_id")
    title = models.CharField(max_length=180)
    code = models.CharField(max_length=60, unique=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    fax = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "org_branches"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title
