"""Document numbers: one series per document type, prefix / start / padding set in General Settings.

Each document keeps its own counter column (``seq_num`` and friends); a series
only decides where that counter starts and how the number is written. A
number, once given, is never rewritten.
"""

from dataclasses import dataclass

SERIES_PURCHASE_ORDER = "purchase_order"
SERIES_PURCHASE_INVOICE = "purchase_invoice"
SERIES_PURCHASE_RETURN = "purchase_return"
SERIES_SALES_ORDER = "sales_order"
SERIES_SALE_INVOICE = "sale_invoice"
SERIES_SALE_RETURN = "sale_return"
SERIES_CASH_PAYMENT = "cash_payment"
SERIES_CASH_RECEIPT = "cash_receipt"
SERIES_BANK_PAYMENT = "bank_payment"
SERIES_BANK_RECEIPT = "bank_receipt"
SERIES_JOURNAL = "journal"


@dataclass(frozen=True)
class SeriesDefault:
    code: str
    label: str
    prefix: str
    padding: int
    start_number: int = 1


DEFAULTS: tuple[SeriesDefault, ...] = (
    SeriesDefault(SERIES_PURCHASE_ORDER, "Purchase Order", "PO", 0),
    SeriesDefault(SERIES_PURCHASE_INVOICE, "Purchase Invoice", "PI", 6),
    SeriesDefault(SERIES_PURCHASE_RETURN, "Purchase Return", "PR", 0),
    SeriesDefault(SERIES_SALES_ORDER, "Sales Order", "SO", 6),
    SeriesDefault(SERIES_SALE_INVOICE, "Sale Invoice", "SAL", 0),
    SeriesDefault(SERIES_SALE_RETURN, "Sale Return", "SR", 0),
    SeriesDefault(SERIES_CASH_PAYMENT, "Cash Payment", "CP", 0),
    SeriesDefault(SERIES_CASH_RECEIPT, "Cash Receipt", "CR", 0),
    SeriesDefault(SERIES_BANK_PAYMENT, "Bank Payment", "BP", 0),
    SeriesDefault(SERIES_BANK_RECEIPT, "Bank Receipt", "BR", 0),
    SeriesDefault(SERIES_JOURNAL, "Journal Voucher", "JV", 0),
)
DEFAULT_MAP = {series.code: series for series in DEFAULTS}


def series(code: str):
    """The stored series, created from its default the first time it is asked for."""
    from .models import DocumentSeries

    default = DEFAULT_MAP[code]
    row, _ = DocumentSeries.objects.get_or_create(
        code=code,
        defaults={"label": default.label, "prefix": default.prefix, "padding": default.padding, "start_number": default.start_number},
    )
    return row


def next_seq(code: str, last) -> int:
    """The counter after ``last`` (None when the series is empty), never below the starting number."""
    start = series(code).start_number
    return start if last is None else max(last + 1, start)


def format_number(code: str, seq: int, row=None) -> str:
    row = row or series(code)
    return f"{row.prefix}-{str(seq).zfill(row.padding)}"


def preview(code: str, last) -> str:
    row = series(code)
    seq = row.start_number if last is None else max(last + 1, row.start_number)
    return format_number(code, seq, row)


_COUNTERS = {
    SERIES_PURCHASE_ORDER: ("inventory", "PurchaseOrder", "seq_num"),
    SERIES_PURCHASE_INVOICE: ("inventory", "PurchaseInvoice", "seq_num"),
    SERIES_PURCHASE_RETURN: ("inventory", "PurchaseReturnMaster", "return_seq_num"),
    SERIES_SALES_ORDER: ("inventory", "SalesOrder", "seq_num"),
    SERIES_SALE_INVOICE: ("inventory", "POSMaster", "sale_seq_num"),
    SERIES_SALE_RETURN: ("inventory", "POSReturnMaster", "return_seq_num"),
}


def last_used(code: str):
    """The highest counter already given in this series, or None."""
    import re

    from django.apps import apps
    from django.db.models import Max

    if code in _COUNTERS:
        app_label, model_name, field = _COUNTERS[code]
        model = apps.get_model(app_label, model_name)
        return model.all_objects.aggregate(top=Max(field))["top"]
    voucher = apps.get_model("finance", "AccountVoucher")
    prefix = series(code).prefix
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    numbers = [int(match.group(1)) for number in voucher.all_objects.filter(voucher_no__startswith=f"{prefix}-").values_list("voucher_no", flat=True) if (match := pattern.match(number or ""))]
    return max(numbers) if numbers else None


def all_series() -> list:
    return [series(default.code) for default in DEFAULTS]
