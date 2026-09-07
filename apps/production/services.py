"""Writes. Every grinding and conversion voucher is saved through here.

Saving a voucher is one transaction: the header, its lines, and the product
ledger rows that move the stock. An edit reverses everything the voucher wrote
and writes it again, rather than trying to patch the difference -- a patch has
to be right about what changed, and being wrong leaves stock that no screen can
explain.

If the mill ever moves to perpetual costing, ``post_grinding_stock`` is the one
function that gains a journal entry. Nothing else here touches value.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.constants import (
    PRD_LEDGER_PACKING_OUT,
    PRD_LEDGER_PRODUCTION_IN,
    PRD_LEDGER_PRODUCTION_OUT,
)
from apps.products.models import ProductLedger

from .models import GrindingOutput, GrindingVoucher, ProductConversion, ProductConversionLine

ZERO = Decimal("0")


def _stamp(instance, user):
    if user is not None and getattr(user, "is_authenticated", False):
        if instance.pk is None:
            instance.created_by = user
        instance.updated_by = user
    return instance


def _dec(value) -> Decimal:
    if value in (None, ""):
        return ZERO
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Yield
# ---------------------------------------------------------------------------
def compute_yield(disposal_wheat, output_lines) -> dict:
    """The four figures the screen shows live and the voucher stores.

    ``output_lines`` is anything with ``quantity`` and ``unit_weight`` -- saved
    rows, unsaved rows, or plain dicts from the posted form -- because the entry
    screen needs this before anything has been written.
    """
    disposal_wheat = _dec(disposal_wheat)
    total_output = ZERO
    for line in output_lines:
        if isinstance(line, dict):
            quantity, unit_weight = _dec(line.get("quantity")), _dec(line.get("unit_weight"))
        else:
            quantity, unit_weight = _dec(line.quantity), _dec(line.unit_weight)
        total_output += quantity * unit_weight

    shortage = disposal_wheat - total_output
    if disposal_wheat > ZERO:
        yield_percent = total_output / disposal_wheat * Decimal("100")
        shortage_percent = shortage / disposal_wheat * Decimal("100")
    else:
        # No wheat consumed is not a divide-by-zero to report; it is a voucher
        # that has not been filled in yet, and the screen shows dashes.
        yield_percent = shortage_percent = ZERO

    return {
        "total_output_kg": total_output.quantize(Decimal("0.001")),
        "yield_percent": yield_percent.quantize(Decimal("0.001")),
        "shortage_kg": shortage.quantize(Decimal("0.001")),
        "shortage_percent": shortage_percent.quantize(Decimal("0.001")),
    }


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
def clear_stock(reference: str, sources) -> int:
    """Remove every ledger row a document wrote. Hard delete, not soft.

    A soft-deleted row still sums into stock unless every reader remembers to
    exclude it, so a reversal that only hides rows is a reversal that does not
    reverse.
    """
    deleted, _ = ProductLedger.all_objects.filter(reference=reference, source__in=sources).delete()
    return deleted


GRINDING_SOURCES = (PRD_LEDGER_PRODUCTION_OUT, PRD_LEDGER_PRODUCTION_IN, PRD_LEDGER_PACKING_OUT)


def post_grinding_stock(voucher: GrindingVoucher, user=None) -> list[ProductLedger]:
    """Move the quantities the voucher describes. No accounting entry.

    Four kinds of row, all dated on the voucher and all tagged with its number,
    which is what lets the whole document be reversed by reference alone.
    """
    rows: list[ProductLedger] = []

    def add(product, quantity, source, remarks):
        if product is None or not quantity:
            return
        entry = ProductLedger(
            product=product,
            entry_date=voucher.date,
            source=source,
            reference=voucher.voucher_no,
            quantity=quantity,
            rate=ZERO,
            remarks=remarks,
            godown=voucher.godown,
        )
        _stamp(entry, user)
        rows.append(entry)

    add(voucher.wheat_item, -_dec(voucher.disposal_wheat), PRD_LEDGER_PRODUCTION_OUT, "Wheat ground")
    add(voucher.bag_item, -_dec(voucher.disposal_bag_qty), PRD_LEDGER_PRODUCTION_OUT, "Sacks emptied")

    for line in voucher.outputs.select_related("product", "pack_product"):
        add(line.product, _dec(line.quantity), PRD_LEDGER_PRODUCTION_IN, "Production")
        add(line.pack_product, -_dec(line.pack_qty), PRD_LEDGER_PACKING_OUT, "Packed output")

    ProductLedger.objects.bulk_create(rows)
    return rows


# ---------------------------------------------------------------------------
# Grinding voucher
# ---------------------------------------------------------------------------
@transaction.atomic
def save_grinding_voucher(voucher: GrindingVoucher, lines: list[dict], user=None) -> GrindingVoucher:
    """Save header, replace lines, repost stock. One transaction.

    ``lines`` is a list of dicts: ``product``, ``quantity``, ``unit_weight``,
    ``pack_product``, ``pack_qty``. Unit weight is passed in rather than read
    here, because the form has already snapshotted it off the master and a
    second read could disagree with what the operator saw.
    """
    if not lines:
        raise ValueError("A grinding voucher needs at least one output line.")

    voucher.ensure_number()
    voucher.standard_yield_percent = _dec(getattr(voucher.wheat_item, "standard_yield_percent", 0))
    totals = compute_yield(voucher.disposal_wheat, lines)
    for field, value in totals.items():
        setattr(voucher, field, value)

    voucher.full_clean(validate_unique=False)
    _stamp(voucher, user)
    voucher.save()

    # Lines are rewritten wholesale: matching posted rows against stored rows
    # would need an identity the grid does not carry, and a wrong match silently
    # moves stock between two products.
    GrindingOutput.all_objects.filter(voucher=voucher).delete()
    for index, line in enumerate(lines, start=1):
        output = GrindingOutput(
            voucher=voucher,
            line_number=index,
            product=line["product"],
            quantity=_dec(line.get("quantity")),
            unit_weight=_dec(line.get("unit_weight")),
            pack_product=line.get("pack_product"),
            pack_qty=_dec(line.get("pack_qty")),
        )
        output.full_clean(validate_unique=False)
        _stamp(output, user)
        output.save()

    clear_stock(voucher.voucher_no, GRINDING_SOURCES)
    post_grinding_stock(voucher, user)
    return voucher


@transaction.atomic
def delete_grinding_voucher(voucher: GrindingVoucher, user=None) -> None:
    """Reverse the stock, then retire the document. The number is never reused."""
    clear_stock(voucher.voucher_no, GRINDING_SOURCES)
    for line in GrindingOutput.all_objects.filter(voucher=voucher):
        line.soft_delete(user)
    voucher.soft_delete(user)


# ---------------------------------------------------------------------------
# Product conversion
# ---------------------------------------------------------------------------
CONVERSION_SOURCES = (PRD_LEDGER_PRODUCTION_OUT, PRD_LEDGER_PRODUCTION_IN, PRD_LEDGER_PACKING_OUT)


def post_conversion_stock(conversion: ProductConversion, user=None) -> list[ProductLedger]:
    rows: list[ProductLedger] = []

    def add(product, quantity, source, remarks):
        if product is None or not quantity:
            return
        entry = ProductLedger(
            product=product,
            entry_date=conversion.date,
            source=source,
            reference=conversion.voucher_no,
            quantity=quantity,
            rate=ZERO,
            remarks=remarks,
            godown=conversion.godown,
        )
        _stamp(entry, user)
        rows.append(entry)

    add(conversion.source_product, -_dec(conversion.source_quantity), PRD_LEDGER_PRODUCTION_OUT, "Repacked out")
    for line in conversion.outputs.select_related("product", "pack_product"):
        add(line.product, _dec(line.quantity), PRD_LEDGER_PRODUCTION_IN, "Repacked in")
        add(line.pack_product, -_dec(line.pack_qty), PRD_LEDGER_PACKING_OUT, "Repack packing")

    ProductLedger.objects.bulk_create(rows)
    return rows


@transaction.atomic
def save_conversion(conversion: ProductConversion, lines: list[dict], user=None) -> ProductConversion:
    if not lines:
        raise ValueError("A conversion needs at least one output line.")

    conversion.ensure_number()
    conversion.total_output_kg = compute_yield(0, lines)["total_output_kg"]
    conversion.full_clean(validate_unique=False)
    _stamp(conversion, user)
    conversion.save()

    ProductConversionLine.all_objects.filter(conversion=conversion).delete()
    for index, line in enumerate(lines, start=1):
        row = ProductConversionLine(
            conversion=conversion,
            line_number=index,
            product=line["product"],
            quantity=_dec(line.get("quantity")),
            unit_weight=_dec(line.get("unit_weight")),
            pack_product=line.get("pack_product"),
            pack_qty=_dec(line.get("pack_qty")),
        )
        row.full_clean(validate_unique=False)
        _stamp(row, user)
        row.save()

    clear_stock(conversion.voucher_no, CONVERSION_SOURCES)
    post_conversion_stock(conversion, user)
    return conversion


@transaction.atomic
def delete_conversion(conversion: ProductConversion, user=None) -> None:
    clear_stock(conversion.voucher_no, CONVERSION_SOURCES)
    for line in ProductConversionLine.all_objects.filter(conversion=conversion):
        line.soft_delete(user)
    conversion.soft_delete(user)


def next_grinding_number() -> str:
    """Advisory only: the number is allocated in ``save()``, so a voucher saved
    between this preview and the save takes it and the next one moves up."""
    last = GrindingVoucher.all_objects.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
    return f"WG-{last + 1:04d}"


def next_conversion_number() -> str:
    last = ProductConversion.all_objects.order_by("-seq_num").values_list("seq_num", flat=True).first() or 0
    return f"PC-{last + 1:04d}"


def today():
    return timezone.localdate()
