"""What the purchase order form shows, and what the site added to it.

The screen is the same for everyone, but not every site wants every box on it,
and most want one or two of their own. Both are held as one JSON record in
``SystemConfiguration`` rather than as columns, so a site changes its own form
without a migration and without a deploy.

The record looks like::

    {
      "hidden": ["quot_date", "tax_amount"],
      "extra": [
        {"code": "lc_no", "label": "LC No", "type": "text",
         "required": false, "options": []}
      ]
    }

Nothing in the books reads any of it: hiding a box only stops it being asked
for, and an extra field is carried on the order as a note. An order posts the
same either way.
"""

from dataclasses import dataclass
import re

from apps.configurations.models import SystemConfiguration

SETTING_KEY = "inventory.purchase_order_form"

# A code is what the value is filed under on the order, so it has to be stable,
# unique and safe to put in an input name.
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

EXTRA_FIELD_TYPES = (
    ("text", "Text"),
    ("number", "Number"),
    ("date", "Date"),
    ("select", "Choice list"),
)
EXTRA_FIELD_TYPE_VALUES = {value for value, _ in EXTRA_FIELD_TYPES}


@dataclass(frozen=True)
class OptionalField:
    """A box on the form the site is allowed to take off it."""

    code: str
    label: str
    group: str
    note: str = ""


# Only what the form can lose and still be a purchase order. Supplier, the item
# lines, quantity and rate are not here: without them there is nothing to save,
# so they are never on offer.
OPTIONAL_FIELDS: tuple[OptionalField, ...] = (
    OptionalField("quot_num", "Quotation No", "Header"),
    OptionalField("quot_date", "Quotation Date", "Header"),
    OptionalField("line_uom", "Unit column", "Lines",
                  "Off, every line is written in the item's own unit."),
    OptionalField("line_stock", "Stock in hand chip", "Lines"),
    OptionalField("remarks", "Narration", "Money"),
    OptionalField("discount_amount", "Discount", "Money"),
    OptionalField("tax_amount", "Tax", "Money"),
    OptionalField("amount_words", "Amount in words panel", "Money"),
)
OPTIONAL_FIELD_CODES = {field.code for field in OPTIONAL_FIELDS}

# The codes a site may not take for one of its own fields, because the form
# already posts something under each of them.
RESERVED_CODES = OPTIONAL_FIELD_CODES | {
    "supplier", "order_date", "quantity", "rate", "item_id", "csrfmiddlewaretoken",
    "save_and_print", "save_and_raise",
}


def _record():
    row = SystemConfiguration.objects.filter(key=SETTING_KEY).first()
    return row.value if row and isinstance(row.value, dict) else {}


def _clean_extra(raw):
    """One stored extra field, or None where the record is not usable.

    Read defensively: the row is JSON, so it can be edited by hand into
    something the form cannot render, and a bad entry drops out rather than
    taking the screen down with it.
    """
    if not isinstance(raw, dict):
        return None
    code = str(raw.get("code") or "").strip().lower()
    label = str(raw.get("label") or "").strip()
    kind = str(raw.get("type") or "text").strip()
    if not CODE_PATTERN.match(code) or not label or kind not in EXTRA_FIELD_TYPE_VALUES:
        return None
    options = [str(option).strip() for option in (raw.get("options") or []) if str(option).strip()]
    if kind == "select" and not options:
        return None
    return {
        "code": code,
        "label": label[:60],
        "type": kind,
        "required": bool(raw.get("required")),
        "options": options,
    }


def get_layout():
    """What the form should render, cleaned and ready for a template."""
    record = _record()
    hidden = {code for code in record.get("hidden", []) if code in OPTIONAL_FIELD_CODES}

    extra, seen = [], set()
    for raw in record.get("extra", []):
        field = _clean_extra(raw)
        if not field or field["code"] in seen:
            continue
        seen.add(field["code"])
        extra.append(field)

    return {
        # ``shown`` is what a template asks: ``{% if layout.shown.tax_amount %}``.
        "shown": {field.code: field.code not in hidden for field in OPTIONAL_FIELDS},
        "hidden": sorted(hidden),
        "extra": extra,
        "optional_fields": [
            {"code": field.code, "label": field.label, "group": field.group,
             "note": field.note, "on": field.code not in hidden}
            for field in OPTIONAL_FIELDS
        ],
    }


def _save(hidden, extra):
    SystemConfiguration.objects.update_or_create(
        key=SETTING_KEY,
        defaults={"value": {"hidden": sorted(set(hidden)), "extra": extra}},
    )


def set_hidden(codes):
    """Replace the hidden set with ``codes``, ignoring anything not on offer."""
    record = get_layout()
    _save([code for code in codes if code in OPTIONAL_FIELD_CODES], record["extra"])


def add_extra_field(*, code, label, kind, required=False, options=()):
    """Put one of the site's own fields on the form.

    Returns an error message, or None where it was added. The caller shows the
    message; nothing here raises, because this is a settings menu and a typo is
    an ordinary thing to correct rather than an exception.
    """
    code = (code or "").strip().lower().replace(" ", "_").replace("-", "_")
    label = (label or "").strip()
    if not label:
        return "Give the field a label."
    if not CODE_PATTERN.match(code):
        return "The code must start with a letter and use only letters, numbers and underscores."
    if code in RESERVED_CODES:
        return f"'{code}' is already used by the form. Pick another code."
    if kind not in EXTRA_FIELD_TYPE_VALUES:
        return "Pick a field type."

    options = [str(option).strip() for option in options if str(option).strip()]
    if kind == "select" and not options:
        return "A choice list needs at least one choice."

    record = get_layout()
    if any(field["code"] == code for field in record["extra"]):
        return f"'{code}' is already on the form."

    extra = record["extra"] + [{
        "code": code, "label": label[:60], "type": kind,
        "required": bool(required), "options": options,
    }]
    _save(record["hidden"], extra)
    return None


def remove_extra_field(code):
    """Take one of the site's own fields off the form.

    What earlier orders recorded under it is left alone: the value stays on the
    order, so a field removed by mistake loses nothing but its box.
    """
    record = get_layout()
    _save(record["hidden"], [field for field in record["extra"] if field["code"] != code])


def read_extra_values(posted, layout=None):
    """What the operator typed into the site's own fields.

    Returns (values, error). Only declared fields are read, so the query string
    cannot write anything it likes onto the order.
    """
    layout = layout or get_layout()
    values = {}
    for field in layout["extra"]:
        raw = (posted.get(f"extra__{field['code']}") or "").strip()
        if field["type"] == "select" and raw and raw not in field["options"]:
            return {}, f"{field['label']} is not one of its choices."
        if not raw:
            if field["required"]:
                return {}, f"{field['label']} is required."
            continue
        values[field["code"]] = raw
    return values, None
