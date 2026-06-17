from django.contrib import admin

from .models import Employee, EmployeeExperience, EmployeeQualification


class EmployeeExperienceInline(admin.TabularInline):
    model = EmployeeExperience
    extra = 0


class EmployeeQualificationInline(admin.TabularInline):
    model = EmployeeQualification
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "cnic", "department", "designation", "organization", "branch", "status")
    search_fields = ("full_name", "cnic", "email", "contact", "att_machine_code")
    list_filter = ("department", "designation", "organization", "branch", "status")
    inlines = (EmployeeExperienceInline, EmployeeQualificationInline)
