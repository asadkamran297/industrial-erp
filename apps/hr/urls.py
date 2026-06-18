from django.urls import path

from .views import (
    EmployeeCreateView,
    EmployeeDeleteView,
    EmployeeDetailView,
    EmployeeExperienceCreateView,
    EmployeeExperienceDeleteView,
    EmployeeListView,
    EmployeeQualificationCreateView,
    EmployeeQualificationDeleteView,
    EmployeeUpdateView,
)

app_name = "hr"

urlpatterns = [
    path("employees/", EmployeeListView.as_view(), name="employee_list"),
    path("employees/new/", EmployeeCreateView.as_view(), name="employee_create"),
    path("employees/<int:pk>/", EmployeeDetailView.as_view(), name="employee_detail"),
    path("employees/<int:pk>/edit/", EmployeeUpdateView.as_view(), name="employee_update"),
    path("employees/<int:pk>/delete/", EmployeeDeleteView.as_view(), name="employee_delete"),
    path("employees/<int:employee_pk>/experiences/new/", EmployeeExperienceCreateView.as_view(), name="employee_experience_create"),
    path("employees/<int:employee_pk>/experiences/<int:pk>/delete/", EmployeeExperienceDeleteView.as_view(), name="employee_experience_delete"),
    path("employees/<int:employee_pk>/qualifications/new/", EmployeeQualificationCreateView.as_view(), name="employee_qualification_create"),
    path("employees/<int:employee_pk>/qualifications/<int:pk>/delete/", EmployeeQualificationDeleteView.as_view(), name="employee_qualification_delete"),
]
