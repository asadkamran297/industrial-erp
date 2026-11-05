from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from apps.core.constants import (
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_CAPITAL,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_LIABILITY,
    ACCOUNT_TYPE_REVENUE,
    GL_BANK_PATH,
    GL_CASH_PATH,
    GL_COGS_PATH,
    GL_ELECTRICITY_PATH,
    GL_FREIGHT_PATH,
    GL_OFFICE_EXPENSE_PATH,
    GL_REPAIRS_PATH,
    GL_RETAINED_EARNINGS_PATH,
    GL_SALARIES_EXPENSE_PATH,
    GL_SALARIES_PAYABLE_PATH,
    GL_SALES_DISCOUNT_PATH,
    GL_SALES_RETURN_PATH,
    GL_SALES_REVENUE_PATH,
    GL_STOCK_PATHS,
)
from apps.finance.models import AccountVoucherLine, ChartOfAccount

TREE = [
    ("ASSETS", ACCOUNT_TYPE_ASSET, [
        ("Current Assets", None, []),
        ("Non Current Assets", None, []),
    ]),
    ("LIABILITIES", ACCOUNT_TYPE_LIABILITY, [
        ("Current Liabilities", None, []),
        ("Non Current Liabilities", None, []),
    ]),
    ("CAPITAL", ACCOUNT_TYPE_CAPITAL, [
        ("Owner's Capital", None, []),
        ("Reserves & Surplus", None, []),
    ]),
    ("REVENUE", ACCOUNT_TYPE_REVENUE, [
        ("Direct Revenue", None, []),
        ("Indirect Revenue", None, []),
    ]),
    ("EXPENSES", ACCOUNT_TYPE_EXPENSE, [
        ("Direct Expenses", None, []),
        ("Indirect Expenses", None, []),
    ]),
]

LEAF_ACCOUNTS = (
    GL_CASH_PATH,
    GL_BANK_PATH,
    *GL_STOCK_PATHS.values(),
    GL_SALARIES_PAYABLE_PATH,
    GL_RETAINED_EARNINGS_PATH,
    GL_SALES_REVENUE_PATH,
    GL_SALES_DISCOUNT_PATH,
    GL_SALES_RETURN_PATH,
    GL_COGS_PATH,
    GL_FREIGHT_PATH,
    GL_ELECTRICITY_PATH,
    GL_REPAIRS_PATH,
    GL_SALARIES_EXPENSE_PATH,
    GL_OFFICE_EXPENSE_PATH,
)


class Command(BaseCommand):
    help = "Seed the Chart of Accounts headings and standard accounts (idempotent by title+parent)."

    def handle(self, *args, **options):
        from apps.finance.services import gl_account

        created = self._seed(TREE, parent=None, account_type=None)
        before = ChartOfAccount.objects.count()
        for path in LEAF_ACCOUNTS:
            gl_account(path)
        created += ChartOfAccount.objects.count() - before
        fixed = self._fix_group_flags()
        ChartOfAccount.rebuild_codes()
        self.stdout.write(self.style.SUCCESS(f"Chart of Accounts seeded. {created} nodes created, {fixed} group flags fixed."))

    def _seed(self, nodes, parent, account_type):
        created = 0
        for order, (title, node_type, children) in enumerate(nodes, start=1):
            resolved_type = node_type or account_type
            node, was_created = ChartOfAccount.objects.get_or_create(
                parent=parent,
                title=title,
                defaults={
                    "account_type": resolved_type,
                    "is_group": True,
                    "sort_order": order,
                },
            )
            created += int(was_created)
            created += self._seed(children, parent=node, account_type=resolved_type)
        return created

    def _fix_group_flags(self):
        """A node with children is a heading; a childless node that carries entries is an account."""
        has_children = Exists(ChartOfAccount.objects.filter(parent=OuterRef("pk")))
        fixed = ChartOfAccount.objects.filter(has_children, is_group=False).update(is_group=True)
        used = AccountVoucherLine.objects.values_list("account_no", flat=True).distinct()
        fixed += (
            ChartOfAccount.objects.annotate(kids=has_children)
            .filter(kids=False, is_group=True, code__in=used)
            .update(is_group=False)
        )
        fixed += (
            ChartOfAccount.objects.annotate(kids=has_children)
            .filter(kids=False, is_group=True, parent__isnull=False, parent__parent__isnull=False)
            .filter(title__in=[path[-1] for path in LEAF_ACCOUNTS])
            .update(is_group=False)
        )
        return fixed
