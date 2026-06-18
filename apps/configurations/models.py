from django.db import models

from apps.core.constants import (
    ALLOWANCE_DEDUCTION_TYPE_CHOICES,
    RECORD_STATUS_CHOICES,
    SCOPE_CHOICES,
    STATUS_ACTIVE,
)
from apps.core.models import BaseModel


class LookupModel(BaseModel):
    title = models.CharField(max_length=160)
    code = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.title


class SystemConfiguration(BaseModel):
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "conf_system_settings"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class Gender(LookupModel):
    class Meta:
        db_table = "conf_genders"
        ordering = ["title"]


class ExpenseType(LookupModel):
    class Meta:
        db_table = "conf_expense_types"
        ordering = ["title"]


class PaymentMethod(LookupModel):
    class Meta:
        db_table = "conf_payment_methods"
        ordering = ["title"]


class Bank(LookupModel):
    class Meta:
        db_table = "conf_banks"
        ordering = ["title"]


class Manufacturer(LookupModel):
    local_global = models.CharField(max_length=20, choices=SCOPE_CHOICES, blank=True)

    class Meta:
        db_table = "conf_manufacturers"
        ordering = ["title"]


class ImageType(LookupModel):
    class Meta:
        db_table = "conf_image_types"
        ordering = ["title"]


class City(LookupModel):
    class Meta:
        db_table = "conf_cities"
        ordering = ["title"]


class Designation(LookupModel):
    class Meta:
        db_table = "conf_designations"
        ordering = ["title"]


class Qualification(LookupModel):
    class Meta:
        db_table = "conf_qualifications"
        ordering = ["title"]


class Specialization(LookupModel):
    class Meta:
        db_table = "conf_specializations"
        ordering = ["title"]


class AllowanceDeduction(LookupModel):
    type = models.CharField(max_length=20, choices=ALLOWANCE_DEDUCTION_TYPE_CHOICES)

    class Meta:
        db_table = "conf_allowances_deductions"
        ordering = ["type", "title"]


class Salutation(LookupModel):
    class Meta:
        db_table = "conf_salutations"
        ordering = ["title"]


class Department(LookupModel):
    class Meta:
        db_table = "conf_departments"
        ordering = ["title"]


class BloodGroup(LookupModel):
    class Meta:
        db_table = "conf_blood_groups"
        ordering = ["title"]


class JobType(LookupModel):
    class Meta:
        db_table = "conf_job_types"
        ordering = ["title"]


class Religion(LookupModel):
    class Meta:
        db_table = "conf_religions"
        ordering = ["title"]


class MaritalStatus(LookupModel):
    class Meta:
        db_table = "conf_marital_statuses"
        ordering = ["title"]
