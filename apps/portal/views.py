from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "portal/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "breadcrumbs": [("Dashboard", "")],
                "stats": [
                    {"label": "Open Requests", "value": "24", "tone": "blue"},
                    {"label": "Pending Approvals", "value": "8", "tone": "amber"},
                    {"label": "Active Employees", "value": "316", "tone": "emerald"},
                    {"label": "System Alerts", "value": "3", "tone": "rose"},
                ],
                "shortcuts": [
                    {"title": "Operations", "description": "Daily production and plant work", "url": "#"},
                    {"title": "Inventory", "description": "Stock, stores, and materials", "url": "#"},
                    {"title": "Employees", "description": "People records and attendance", "url": "#"},
                    {"title": "Reports", "description": "Management summaries and MIS", "url": "#"},
                ],
                "activities": [
                    "Shift handover summary was updated",
                    "Inventory low-stock alert reviewed",
                    "Monthly MIS report draft prepared",
                ],
                "tasks": [
                    "Approve material request",
                    "Review attendance exceptions",
                    "Confirm safety checklist",
                ],
            }
        )
        return context
