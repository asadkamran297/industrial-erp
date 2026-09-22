"""Which columns a list screen shows, chosen per person and remembered.

A screen declares its table once as a ``ColumnSet``. From that one declaration
come the burger menu's tick list, what the table renders, and what an export
writes -- so the three can never drift apart, and adding a column to a screen is
a single line rather than an edit in three places.

Held in the session, not the database: which columns somebody wants to look at
is their own business and must not change what anyone else sees.

    COLUMNS = ColumnSet("inventory.grn", (
        Column("purchase_num", "Order #", locked=True, export=lambda o: o.purchase_num),
        Column("supplier", "Supplier", export=lambda o: o.supplier.name),
        Column("buyer", "Raised by", default=False, export=...),
    ))

``locked`` columns are never on offer -- a row without its identity or its
action button is not a row. ``default=False`` starts a column switched off:
worth having, not worth the width on a first look.
"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    locked: bool = False
    default: bool = True
    export: Optional[Callable] = None
    numeric: bool = False
    kind: str = "text"
    link: str = ""
    link_key: str = "pk"
    total: bool = False
    places: int = 0
    tone_key: str = ""


class ColumnSet:
    """One screen's columns, and the session state that goes with them."""

    def __init__(self, name, columns):
        self.name = name
        self.columns = tuple(columns)
        self.session_key = f"table_columns.{name}"
        self.keys = [column.key for column in self.columns]
        self.locked = {column.key for column in self.columns if column.locked}
        self.default_on = {column.key for column in self.columns if column.default or column.locked}

    def visible(self, session):
        """The keys on show, as a set the template can ask with ``in``."""
        stored = session.get(self.session_key)
        if not isinstance(stored, list):
            return set(self.default_on)
        return {key for key in stored if key in self.keys} | self.locked

    def choose(self, session, keys):
        """Remember what to show. Locked columns go back in regardless."""
        wanted = set(keys)
        session[self.session_key] = [
            key for key in self.keys if key in wanted or key in self.locked
        ]

    def menu(self, session):
        """The columns as the burger menu needs them."""
        shown = self.visible(session)
        return [
            {"key": column.key, "label": column.label,
             "locked": column.locked, "on": column.key in shown}
            for column in self.columns
        ]

    def exportable(self, session):
        """The visible columns that can be written to a cell, in table order."""
        shown = self.visible(session)
        return [column for column in self.columns if column.key in shown and column.export]

    def span(self, session, extra=0):
        """How many cells a full-width row must span.

        ``extra`` counts anything the table draws outside the column set -- an
        expander handle, an action cell -- so a footer or an empty-state row
        still lines up when columns are switched off.
        """
        return len(self.visible(session) - self.locked_without_cells) + extra

    locked_without_cells: set = frozenset()


def _exporter(key, kind, places):
    from decimal import Decimal

    from apps.core.formatting import format_amount

    def get(row):
        return row.get(key) if isinstance(row, dict) else getattr(row, key, None)

    if kind == "money":
        return lambda row: format_amount(get(row)) if get(row) is not None else ""
    if kind == "qty":
        return lambda row: f"{Decimal(get(row) or 0):,.{places}f}" if get(row) is not None else ""
    if kind == "pct":
        return lambda row: f"{Decimal(get(row)):.2f}" if get(row) is not None else ""
    if kind == "int":
        return lambda row: "" if get(row) is None else str(get(row))
    if kind == "date":
        return lambda row: f"{get(row):%d-%m-%Y}" if get(row) else ""
    if kind == "time":
        return lambda row: f"{get(row):%H:%M}" if get(row) else ""
    if kind == "status":
        return lambda row: (row.get("status_label") if isinstance(row, dict) else getattr(row, "status_label", "")) or ""
    return lambda row: "" if get(row) is None else str(get(row))


def col(key, label, kind="text", *, locked=False, default=True, total=False, places=0, link="", link_key="pk", tone_key="", export=None):
    """A report column whose export and on-screen rendering follow from ``kind``."""
    return Column(
        key, label, locked=locked, default=default, export=export or _exporter(key, kind, places),
        numeric=kind in ("money", "qty", "pct", "int"), kind=kind, link=link, link_key=link_key, total=total, places=places, tone_key=tone_key,
    )
