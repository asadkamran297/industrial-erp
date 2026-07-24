from django.db import transaction

from apps.core.constants import ACCOUNT_TYPE_ASSET
from .models import ChartOfAccount


def _get_or_create_group(*, parent, title, account_type, user=None):
    """Fetch or create a heading node (is_group=True) under ``parent``."""
    node = ChartOfAccount.objects.filter(parent=parent, title=title).first()
    if node:
        return node
    next_order = (
        ChartOfAccount.objects.filter(parent=parent).order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    ) + 1
    return ChartOfAccount.objects.create(
        parent=parent,
        title=title,
        account_type=account_type if parent is None else parent.account_type,
        is_group=True,
        sort_order=next_order,
        created_by=user,
        updated_by=user,
    )


def get_receivables_group(*, user=None):
    """Ensure ASSETS > Current Assets > Receivables headings exist; return the leaf group."""
    assets = _get_or_create_group(parent=None, title="ASSETS", account_type=ACCOUNT_TYPE_ASSET, user=user)
    current = _get_or_create_group(parent=assets, title="Current Assets", account_type=ACCOUNT_TYPE_ASSET, user=user)
    return _get_or_create_group(parent=current, title="Receivables", account_type=ACCOUNT_TYPE_ASSET, user=user)


@transaction.atomic
def create_customer_receivable_account(*, customer, user=None):
    """Create a postable Receivables account for a new customer (idempotent by title)."""
    receivables = get_receivables_group(user=user)
    existing = ChartOfAccount.objects.filter(parent=receivables, title=customer.customer_name).first()
    if existing:
        return existing
    next_order = (
        ChartOfAccount.objects.filter(parent=receivables).order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    ) + 1
    node = ChartOfAccount.objects.create(
        parent=receivables,
        title=customer.customer_name,
        account_type=receivables.account_type,
        is_group=False,
        sort_order=next_order,
        created_by=user,
        updated_by=user,
    )
    ChartOfAccount.rebuild_codes()
    return node
