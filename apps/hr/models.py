from django.db import models

from apps.core.constants import (
    COMPLETION_STATUS_CHOICES,
    QUALIFICATION_TYPE_CHOICES,
    RECORD_STATUS_CHOICES,
    STATUS_ACTIVE,
)
from apps.core.models import BaseModel


class Employee(BaseModel):
    designation = models.ForeignKey("configurations.Designation", null=True, blank=True, on_delete=models.SET_NULL)
    department = models.ForeignKey("configurations.Department", null=True, blank=True, on_delete=models.SET_NULL)
    salutation = models.ForeignKey("configurations.Salutation", null=True, blank=True, on_delete=models.SET_NULL)
    gender = models.ForeignKey("configurations.Gender", null=True, blank=True, on_delete=models.SET_NULL)
    blood_group = models.ForeignKey("configurations.BloodGroup", null=True, blank=True, on_delete=models.SET_NULL)
    job_type = models.ForeignKey("configurations.JobType", null=True, blank=True, on_delete=models.SET_NULL)
    religion = models.ForeignKey("configurations.Religion", null=True, blank=True, on_delete=models.SET_NULL)
    marital_status = models.ForeignKey("configurations.MaritalStatus", null=True, blank=True, on_delete=models.SET_NULL)
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, related_name="employees", on_delete=models.SET_NULL
    )
    branch = models.ForeignKey("organizations.Branch", null=True, blank=True, related_name="employees", on_delete=models.SET_NULL)
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    full_name = models.CharField(max_length=240)
    email = models.EmailField(blank=True)
    father_husband_name = models.CharField(max_length=160, blank=True)
    cnic = models.CharField(max_length=30, unique=True)
    dob = models.DateField(null=True, blank=True)
    doj = models.DateField("date of joining", null=True, blank=True)
    contact = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="employees/avatars/", blank=True)
    joining_date = models.DateField(null=True, blank=True)
    bank = models.CharField(max_length=120, blank=True)
    account_number = models.CharField(max_length=80, blank=True)
    spouse_name = models.CharField(max_length=160, blank=True)
    nok = models.CharField("next of kin", max_length=160, blank=True)
    nok_cnic = models.CharField("next of kin CNIC", max_length=30, blank=True)
    emergency_contact = models.CharField(max_length=40, blank=True)
    att_machine_code = models.CharField(max_length=80, blank=True)
    salary = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "hr_employees"
        ordering = ["full_name"]

    def __str__(self) -> str:
        return self.full_name


class EmployeeExperience(BaseModel):
    employee = models.ForeignKey(Employee, related_name="experiences", on_delete=models.CASCADE)
    organization = models.CharField(max_length=180)
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    leave_reason = models.TextField(blank=True)
    salary = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "hr_employee_experiences"
        ordering = ["employee", "-from_date"]

    def __str__(self) -> str:
        return f"{self.employee} - {self.organization}"


class EmployeeQualification(BaseModel):
    employee = models.ForeignKey(Employee, related_name="qualifications", on_delete=models.CASCADE)
    qualification = models.ForeignKey("configurations.Qualification", related_name="employee_links", on_delete=models.PROTECT)
    specialization = models.ForeignKey(
        "configurations.Specialization", null=True, blank=True, related_name="employee_qualifications", on_delete=models.SET_NULL
    )
    qualification_type = models.CharField(max_length=30, choices=QUALIFICATION_TYPE_CHOICES)
    institute = models.CharField(max_length=180, blank=True)
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=COMPLETION_STATUS_CHOICES, default="completed")

    class Meta:
        db_table = "hr_employee_qualifications"
        ordering = ["employee", "-to_date"]

    def __str__(self) -> str:
        return f"{self.employee} - {self.qualification}"
