from django.core.management.base import BaseCommand

from apps.core.constants import (
    ACCOUNT_TYPE_ASSET,
    ACCOUNT_TYPE_CAPITAL,
    ACCOUNT_TYPE_EXPENSE,
    ACCOUNT_TYPE_LIABILITY,
    ACCOUNT_TYPE_REVENUE,
)
from apps.finance.models import ChartOfAccount

# (title, account_type, [children]). Five fixed roots, each with two sub-headings.
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


class Command(BaseCommand):
    help = "Seed the sample Chart of Accounts tree (idempotent by title+parent)."

    def handle(self, *args, **options):
        created = self._seed(TREE, parent=None, account_type=None)
        ChartOfAccount.rebuild_codes()
        self.stdout.write(self.style.SUCCESS(f"Chart of Accounts seeded. {created} nodes created."))

    def _seed(self, nodes, parent, account_type):
        created = 0
        for order, (title, node_type, children) in enumerate(nodes, start=1):
            resolved_type = node_type or account_type
            node, was_created = ChartOfAccount.objects.get_or_create(
                parent=parent,
                title=title,
                defaults={
                    "account_type": resolved_type,
                    "is_group": bool(children),
                    "sort_order": order,
                },
            )
            created += int(was_created)
            created += self._seed(children, parent=node, account_type=resolved_type)
        return created
