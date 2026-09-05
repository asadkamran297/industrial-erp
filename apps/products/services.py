"""Writes. Every change to a product or its links goes through here."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.constants import (
    PRD_LEDGER_OPENING,
    PRD_SPEC_RULES,
    STATUS_ACTIVE,
    STATUS_CLOSED,
    STATUS_INACTIVE,
)

from .models import (
    FinishBardanaLink,
    ProductAccountLink,
    ProductLedger,
    ProductNode,
    ProductOpeningBalance,
    ProductRate,
    RawBardanaLink,
)


def _stamp(instance, user):
    if user is not None and getattr(user, "is_authenticated", False):
        if instance.pk is None:
            instance.created_by = user
        instance.updated_by = user
    return instance


@transaction.atomic
def save_product(product: ProductNode, user=None) -> ProductNode:
    product.full_clean(exclude=None, validate_unique=False)
    _stamp(product, user)
    product.save()
    return product


@transaction.atomic
def set_status(product: ProductNode, status: str, user=None) -> ProductNode:
    """Products are never deleted. Closed is final; inactive can be undone."""
    if product.status == STATUS_CLOSED and status != STATUS_CLOSED:
        raise ValueError("A closed product stays closed.")
    product.status = status
    _stamp(product, user)
    product.save(update_fields=["status", "updated_by", "updated_at"])
    return product


def toggle_status(product: ProductNode, user=None) -> ProductNode:
    if product.status == STATUS_CLOSED:
        raise ValueError("A closed product stays closed.")
    return set_status(product, STATUS_INACTIVE if product.status == STATUS_ACTIVE else STATUS_ACTIVE, user)


@transaction.atomic
def link_purchase_account(product: ProductNode, account, user=None):
    """Set or clear the purchase account a bought product is charged to."""
    if not PRD_SPEC_RULES.get(product.specification, {}).get("can_buy"):
        raise ValueError(f"{product.name} is never bought, so it takes no purchase account.")
    if account is None:
        ProductAccountLink.objects.filter(product=product).delete()
        return None
    link, _ = ProductAccountLink.objects.get_or_create(product=product, defaults={"purchase_account": account})
    link.purchase_account = account
    link.full_clean(validate_unique=False)
    _stamp(link, user)
    link.save()
    return link


@transaction.atomic
def link_raw_bardana(wheat_item: ProductNode, bardana_item, user=None):
    if bardana_item is None:
        RawBardanaLink.objects.filter(wheat_item=wheat_item).delete()
        return None
    link, _ = RawBardanaLink.objects.get_or_create(wheat_item=wheat_item, defaults={"bardana_item": bardana_item})
    link.bardana_item = bardana_item
    link.full_clean(validate_unique=False)
    _stamp(link, user)
    link.save()
    return link


@transaction.atomic
def link_finish_bardana(finish_item: ProductNode, bag_item, user=None):
    if bag_item is None:
        FinishBardanaLink.objects.filter(finish_item=finish_item).delete()
        return None
    link, _ = FinishBardanaLink.objects.get_or_create(finish_item=finish_item, defaults={"bag_item": bag_item})
    link.bag_item = bag_item
    link.full_clean(validate_unique=False)
    _stamp(link, user)
    link.save()
    return link


@transaction.atomic
def set_opening_balance(product: ProductNode, quantity, as_of_date=None, rate=None, user=None):
    """Record the opening and move its ledger row with it.

    The opening is one ledger entry, rewritten in place. Writing a second row
    each time the grid was saved would double the stock of every product an
    operator corrected.
    """
    quantity = Decimal(quantity or 0)
    as_of_date = as_of_date or timezone.localdate()
    rate = Decimal(rate or 0)

    if not product.keeps_stock:
        raise ValueError(f"{product.name} carries no stock, so it has no opening balance.")

    opening, _ = ProductOpeningBalance.objects.get_or_create(
        product=product,
        defaults={"as_of_date": as_of_date, "quantity": quantity, "rate": rate},
    )
    opening.as_of_date = as_of_date
    opening.quantity = quantity
    opening.rate = rate
    _stamp(opening, user)
    opening.save()

    entry = ProductLedger.objects.filter(product=product, source=PRD_LEDGER_OPENING).first()
    if entry is None:
        entry = ProductLedger(product=product, source=PRD_LEDGER_OPENING)
    entry.entry_date = as_of_date
    entry.quantity = quantity
    entry.rate = rate
    entry.reference = "OPENING"
    _stamp(entry, user)
    entry.save()
    return opening


@transaction.atomic
def set_rate(product: ProductNode, rate, effective_date=None, user=None):
    """New rate, old one demoted. History is never overwritten."""
    rate = Decimal(rate or 0)
    effective_date = effective_date or timezone.localdate()

    current = ProductRate.objects.filter(product=product, is_current=True).first()
    if current and current.rate == rate and current.effective_date == effective_date:
        return current

    ProductRate.objects.filter(product=product, is_current=True).update(is_current=False)
    new_rate = ProductRate(product=product, rate=rate, effective_date=effective_date, is_current=True)
    _stamp(new_rate, user)
    new_rate.save()
    return new_rate


@transaction.atomic
def post_movement(product: ProductNode, quantity, source: str, entry_date=None, reference="", rate=0, remarks="", user=None):
    """The one door into the ledger. Signed quantity: in positive, out negative.

    Every other module posts stock through this, so the rule that a service or
    wage item never reaches the ledger is enforced once rather than in each
    caller.
    """
    if not product.keeps_stock:
        raise ValueError(f"{product.name} carries no stock and cannot be posted to the ledger.")
    entry = ProductLedger(
        product=product,
        entry_date=entry_date or timezone.localdate(),
        source=source,
        reference=reference,
        quantity=Decimal(quantity),
        rate=Decimal(rate or 0),
        remarks=remarks,
    )
    _stamp(entry, user)
    entry.save()
    return entry
