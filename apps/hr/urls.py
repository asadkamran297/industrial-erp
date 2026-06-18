from django.urls import path

from .views import EmployeeCreateView, EmployeeDeleteView, EmployeeListView, EmployeeUpdateView

app_name = "hr"

urlpatterns = [
    path("employees/", EmployeeListView.as_view(), name="employee_list"),
    path("employees/new/", EmployeeCreateView.as_view(), name="employee_create"),
    path("employees/<int:pk>/edit/", EmployeeUpdateView.as_view(), name="employee_update"),
    path("employees/<int:pk>/delete/", EmployeeDeleteView.as_view(), name="employee_delete"),
]
