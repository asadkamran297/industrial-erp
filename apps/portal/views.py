from django.db.models import Count, Sum
from django.views.generic import TemplateView

from apps.core.mixins import PagePermissionRequiredMixin

from apps.finance.models import AccountConfiguration, AccountVoucher
from apps.hr.models import Employee
from apps.inventory.models import POSDetail, PurchaseOrderItem
from apps.organizations.models import Branch, Organization
from apps.payroll.models import Payroll


class DashboardView(PagePermissionRequiredMixin, TemplateView):
    page = "dashboard"
    template_name = "portal/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payroll_totals = Payroll.objects.aggregate(
            net=Sum("net_salary"),
            allowances=Sum("total_allowances"),
            deductions=Sum("total_deductions"),
            base=Sum("base_salary"),
        )
        voucher_totals = AccountVoucher.objects.aggregate(
            debit=Sum("debit_amount"),
            credit=Sum("credit_amount"),
        )
        active_employees = Employee.objects.filter(status="active").count()
        total_employees = Employee.objects.count()
        pending_payrolls = Payroll.objects.filter(status="pending").count()
        total_payrolls = Payroll.objects.count()

        department_chart = [
            {"name": item["department__title"] or "Unassigned", "y": item["count"]}
            for item in Employee.objects.values("department__title").annotate(count=Count("id")).order_by("-count")
        ]
        account_chart = [
            {"name": item["account_type"].title(), "y": item["count"]}
            for item in AccountConfiguration.objects.values("account_type").annotate(count=Count("id")).order_by("-count")
        ]
        payroll_chart = [
            {"name": "Base Salary", "y": float(payroll_totals["base"] or 0)},
            {"name": "Allowances", "y": float(payroll_totals["allowances"] or 0)},
            {"name": "Deductions", "y": float(payroll_totals["deductions"] or 0)},
        ]
        voucher_chart = [
            {"name": "Debit", "y": float(voucher_totals["debit"] or 0)},
            {"name": "Credit", "y": float(voucher_totals["credit"] or 0)},
        ]
        monthly_payroll_chart = [
            {"name": f"{item['month']}/{item['year']}", "y": float(item["net"] or 0)}
            for item in Payroll.objects.values("month", "year").annotate(net=Sum("net_salary")).order_by("year", "month")
        ]

        from apps.inventory.models import POSMaster, PurchaseMaster
        from apps.core.constants import STATUS_POSTED, YES
        total_sales = POSMaster.objects.filter(status=STATUS_POSTED).aggregate(t=Sum("net_amount"))["t"] or 0
        total_purchases = PurchaseMaster.objects.aggregate(t=Sum("total_amount"))["t"] or 0
        trending_sale_items = (
            POSDetail.objects.filter(pos_master__status=STATUS_POSTED)
            .values("item_name", "item_code")
            .annotate(total_qty=Sum("quantity"), total_amt=Sum("net_total"))
            .order_by("-total_qty")[:8]
        )
        trending_purchase_items = (
            PurchaseOrderItem.objects.filter(total_receive_qty__gt=0)
            .values("descr", "inventory_item__code")
            .annotate(total_qty=Sum("total_receive_qty"), total_amt=Sum("retail_price"))
            .order_by("-total_qty")[:8]
        )

        context.update(
            {
                "breadcrumbs": [("Dashboard", "")],
                "stats": [
                    {"label": "Active Employees", "value": active_employees, "detail": f"{total_employees} total workforce"},
                    {"label": "Payroll Net", "value": f"{payroll_totals['net'] or 0:,.0f}", "detail": "Current generated payroll"},
                    {"label": "Voucher Flow", "value": f"{(voucher_totals['debit'] or 0) + (voucher_totals['credit'] or 0):,.0f}", "detail": "Debit + credit movement"},
                    {"label": "Pending Payrolls", "value": pending_payrolls, "detail": f"{total_payrolls} payroll records"},
                ],
                "ops_score": min(98, 72 + active_employees * 2),
                "organization_count": Organization.objects.count(),
                "branch_count": Branch.objects.count(),
                "account_count": AccountConfiguration.objects.count(),
                "voucher_count": AccountVoucher.objects.count(),
                "payroll_totals": payroll_totals,
                "voucher_totals": voucher_totals,
                "recent_vouchers": AccountVoucher.objects.order_by("-voucher_date", "-id")[:5],
                "recent_payrolls": Payroll.objects.select_related("employee").order_by("-year", "-month", "employee__full_name")[:5],
                "department_chart": department_chart,
                "account_chart": account_chart,
                "payroll_chart": payroll_chart,
                "voucher_chart": voucher_chart,
                "monthly_payroll_chart": monthly_payroll_chart,
                "shortcuts": [
                    {"title": "Employees", "description": "Workforce profile and service record", "url": "/hr/employees/"},
                    {"title": "Chart of Accounts", "description": "General and subsidiary account control", "url": "/finance/accounts/"},
                    {"title": "Vouchers", "description": "Payment and receipt voucher flow", "url": "/finance/vouchers/"},
                    {"title": "Payroll", "description": "Monthly salary generation and approval", "url": "/payroll/payrolls/"},
                ],
                "total_sales": total_sales,
                "total_purchases": total_purchases,
                "trending_sale_items": trending_sale_items,
                "trending_purchase_items": trending_purchase_items,
                "tasks": [
                    "Verify pending payrolls",
                    "Review unposted vouchers",
                    "Confirm branch-wise employee assignments",
                ],
            }
        )
        return context
