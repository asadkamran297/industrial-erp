"""Purchase accounts for the bought products, and the links to them.

The chart of accounts numbers itself by position (``ChartOfAccount.rebuild_codes``),
so the accounts are created and then matched by title rather than by a code
typed in here that the rebuild would be free to disagree with. Under a normal
seed the wheat account lands on 05-01-001-0001 and the bags account on
05-01-004-0001, which is what the mill's own paperwork calls them.
"""

from apps.core.constants import (
    ACCOUNT_TYPE_EXPENSE,
    PRD_SPEC_FINISH_PACKING,
    PRD_SPEC_RAW_ITEM,
    PRD_SPEC_RAW_PACKING,
)
from apps.finance.models import ChartOfAccount
from apps.products.models import ProductAccountLink, ProductNode

WHEAT_ACCOUNT = "Wheat Purchase (Pvt) A/c"
BARDANA_ACCOUNT = "PP & Jute Bags Purchase Exp."

# specification -> the account everything of that kind is charged to
SPEC_ACCOUNTS = {
    PRD_SPEC_RAW_ITEM: WHEAT_ACCOUNT,
    PRD_SPEC_RAW_PACKING: BARDANA_ACCOUNT,
    PRD_SPEC_FINISH_PACKING: BARDANA_ACCOUNT,
}


def _direct_expenses() -> ChartOfAccount | None:
    return ChartOfAccount.objects.filter(title="Direct Expenses", account_type=ACCOUNT_TYPE_EXPENSE).first()


def seed_account_links() -> int:
    parent = _direct_expenses()
    if parent is None:
        # No chart of accounts yet. Nothing to link to, and inventing a root
        # here would put the mill's expenses outside the tree the books use.
        return 0

    created = 0
    accounts = {}
    for title in (WHEAT_ACCOUNT, BARDANA_ACCOUNT):
        account, made = ChartOfAccount.objects.get_or_create(
            parent=parent,
            title=title,
            defaults={"account_type": ACCOUNT_TYPE_EXPENSE, "is_group": False},
        )
        accounts[title] = account
        created += int(made)
    if created:
        ChartOfAccount.rebuild_codes()

    for product in ProductNode.objects.filter(specification__in=SPEC_ACCOUNTS):
        account = accounts[SPEC_ACCOUNTS[product.specification]]
        _, made = ProductAccountLink.objects.get_or_create(
            product=product, defaults={"purchase_account": account}
        )
        created += int(made)

    return created
