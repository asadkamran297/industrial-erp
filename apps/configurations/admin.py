from django.contrib import admin

from . import models


for model in (
    models.SystemConfiguration,
    models.Gender,
    models.ExpenseType,
    models.PaymentMethod,
    models.Manufacturer,
    models.ImageType,
    models.City,
    models.Designation,
    models.Qualification,
    models.Specialization,
    models.AllowanceDeduction,
    models.Salutation,
    models.Department,
    models.BloodGroup,
    models.JobType,
    models.Religion,
    models.MaritalStatus,
):
    admin.site.register(model)
