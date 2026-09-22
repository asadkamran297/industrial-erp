"""Period resolution shared by every report screen.

A report reads ``?preset=month`` or ``?date_from=&date_to=`` through
``resolve_period`` and gets back one ``Period``; the previous period of the
same length comes from ``previous_period`` so comparison tiles never work the
dates out twice.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

MUND_KG = Decimal("40")
ZERO = Decimal("0")

PRESET_TODAY = "today"
PRESET_YESTERDAY = "yesterday"
PRESET_WEEK = "week"
PRESET_LAST_WEEK = "last_week"
PRESET_MONTH = "month"
PRESET_LAST_MONTH = "last_month"
PRESET_YEAR = "year"
PRESET_FISCAL = "fiscal"
PRESET_CUSTOM = "custom"

PRESET_CHOICES = (
    (PRESET_TODAY, "Today"),
    (PRESET_YESTERDAY, "Yesterday"),
    (PRESET_WEEK, "This Week"),
    (PRESET_LAST_WEEK, "Last Week"),
    (PRESET_MONTH, "This Month"),
    (PRESET_LAST_MONTH, "Last Month"),
    (PRESET_YEAR, "This Year"),
    (PRESET_FISCAL, "This Fiscal Year"),
    (PRESET_CUSTOM, "Custom"),
)

GROUP_DAY = "day"
GROUP_WEEK = "week"
GROUP_MONTH = "month"
GROUP_CHOICES = ((GROUP_DAY, "Daily"), (GROUP_WEEK, "Weekly"), (GROUP_MONTH, "Monthly"))


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str
    preset: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def query(self) -> str:
        return f"preset={self.preset}&date_from={self.start:%Y-%m-%d}&date_to={self.end:%Y-%m-%d}"


def parse_date(raw):
    try:
        return datetime.strptime((raw or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _month_end(day: date) -> date:
    following = day.replace(day=28) + timedelta(days=4)
    return following - timedelta(days=following.day)


def _fiscal_bounds(today: date):
    from apps.finance.models import FiscalYear

    fiscal = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).order_by("-start_date").first()
    if fiscal:
        return fiscal.start_date, fiscal.end_date
    start = date(today.year if today.month >= 7 else today.year - 1, 7, 1)
    return start, date(start.year + 1, 6, 30)


def preset_bounds(preset: str, today: date | None = None):
    """``(start, end)`` for a preset. Weeks start on Monday."""
    today = today or timezone.localdate()
    if preset == PRESET_TODAY:
        return today, today
    if preset == PRESET_YESTERDAY:
        day = today - timedelta(days=1)
        return day, day
    if preset == PRESET_WEEK:
        return today - timedelta(days=today.weekday()), today
    if preset == PRESET_LAST_WEEK:
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if preset == PRESET_MONTH:
        return today.replace(day=1), today
    if preset == PRESET_LAST_MONTH:
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if preset == PRESET_YEAR:
        return today.replace(month=1, day=1), today
    if preset == PRESET_FISCAL:
        return _fiscal_bounds(today)
    return None


def resolve_period(request, default: str = PRESET_MONTH) -> Period:
    """One period from the query string: a preset, or explicit dates, else ``default``."""
    today = timezone.localdate()
    preset = (request.GET.get("preset") or "").strip()
    date_from = parse_date(request.GET.get("date_from"))
    date_to = parse_date(request.GET.get("date_to"))
    labels = dict(PRESET_CHOICES)

    if preset and preset != PRESET_CUSTOM and preset_bounds(preset, today):
        start, end = preset_bounds(preset, today)
        return Period(start, end, labels[preset], preset)
    if date_from or date_to:
        start = date_from or date_to
        end = date_to or date_from
        if end < start:
            start, end = end, start
        label = f"{start:%d %b %Y}" if start == end else f"{start:%d %b %Y} – {end:%d %b %Y}"
        return Period(start, end, label, PRESET_CUSTOM)
    start, end = preset_bounds(default, today)
    return Period(start, end, labels[default], default)


def previous_period(period: Period) -> Period:
    """The stretch just before ``period``.

    Month-to-date compares with last month to the same day; a whole month with
    the whole previous month; anything else with the same number of days before.
    """
    if period.preset == PRESET_MONTH:
        end = period.start - timedelta(days=1)
        start = end.replace(day=1)
        end = min(end, start + timedelta(days=period.days - 1))
        return Period(start, end, f"{start:%b %Y} to {end:%d}", PRESET_CUSTOM)
    if period.start.day == 1 and period.end == _month_end(period.start):
        end = period.start - timedelta(days=1)
        start = end.replace(day=1)
        return Period(start, end, f"{start:%b %Y}", PRESET_CUSTOM)
    end = period.start - timedelta(days=1)
    start = end - timedelta(days=period.days - 1)
    return Period(start, end, f"{start:%d %b} – {end:%d %b %Y}", PRESET_CUSTOM)


def resolve_as_of(request) -> date:
    return parse_date(request.GET.get("as_of")) or timezone.localdate()


def resolve_group(request, default: str = GROUP_DAY) -> str:
    group = (request.GET.get("group") or "").strip()
    return group if group in dict(GROUP_CHOICES) else default


def group_by(field: str, group: str):
    """Truncation expression for ``.annotate(period=group_by("sale_date", group))``."""
    if group == GROUP_MONTH:
        return TruncMonth(field)
    if group == GROUP_WEEK:
        return TruncWeek(field)
    return TruncDay(field)


def period_label(value, group: str) -> str:
    if value is None:
        return ""
    day = value.date() if isinstance(value, datetime) else value
    if group == GROUP_MONTH:
        return f"{day:%b %Y}"
    if group == GROUP_WEEK:
        return f"Wk {day:%d %b %Y}"
    return f"{day:%d %b %Y}"


def mund(kg) -> Decimal:
    """Kilograms to mund (40 kg), three places."""
    return (Decimal(kg or 0) / MUND_KG).quantize(Decimal("0.001"))


def delta(current, previous):
    """Change against the previous period as ``{"value", "percent", "direction"}``."""
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)
    change = current - previous
    percent = (change / previous * 100).quantize(Decimal("0.1")) if previous else None
    direction = "up" if change > 0 else "down" if change < 0 else "flat"
    return {"value": change, "percent": percent, "direction": direction}


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def weight(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.001"))


# ---------------------------------------------------------------------------
# Screen, export and column views every report is built from
# ---------------------------------------------------------------------------

from django.core.paginator import Paginator  # noqa: E402
from django.shortcuts import redirect  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.views.generic import TemplateView, View  # noqa: E402

from apps.core.mixins import PagePermissionRequiredMixin, PrintContextMixin, report_sort  # noqa: E402
from apps.core.table_export import TableExportView  # noqa: E402


class ReportView(PagePermissionRequiredMixin, TemplateView):
    """One report screen: ``build()`` returns rows and totals, the base wires period, columns and export.

    ``columns`` is the screen's ``ColumnSet``; ``sort_fields`` maps sort keys to
    row keys; ``url_name`` is the screen's own route (``<url_name>_export`` and
    ``<url_name>_columns`` must exist beside it).
    """

    action = "index"
    title = ""
    columns = None
    url_name = ""
    sort_fields: dict = {}
    default_sort = ""
    default_sort_dir = "asc"
    default_preset = PRESET_MONTH
    as_of_report = False
    landscape = True
    table_id = "report-table"
    paginate_by = 100
    filter_specs: tuple = ()
    group_toggle = False
    default_group = GROUP_DAY

    def group(self) -> str:
        return resolve_group(self.request, self.default_group)

    def filters(self) -> dict:
        """``{name: value}`` for every declared filter, blank when not given."""
        return {name: (self.request.GET.get(name) or "").strip() for name, *_ in self.filter_specs}

    def filter_options(self) -> list[dict]:
        """Filter chips for the bar: ``(name, label, choices)`` where choices may be a callable."""
        current = self.filters()
        specs = []
        for name, label, choices in self.filter_specs:
            options = choices() if callable(choices) else choices
            options = list(options)
            specs.append({"name": name, "label": label, "choices": options, "value": current[name], "searchable": len(options) > 8})
        return specs

    def period(self):
        if not hasattr(self, "_period"):
            self._period = resolve_period(self.request, self.default_preset)
        return self._period

    def as_of(self):
        if not hasattr(self, "_as_of"):
            self._as_of = resolve_as_of(self.request)
        return self._as_of

    def build(self) -> dict:
        """``{"rows": [...], "totals": {...}, "tiles": [...]}`` for the current query."""
        raise NotImplementedError

    def data(self) -> dict:
        if not hasattr(self, "_data"):
            self._data = self.build()
        return self._data

    def sorted_rows(self):
        rows, sort_context = report_sort(
            self.request, list(self.data()["rows"]), self.sort_fields,
            default=self.default_sort, default_dir=self.default_sort_dir,
        )
        return rows, sort_context

    def export_rows(self):
        return self.sorted_rows()[0]

    def footer_cells(self, columns):
        """Total row for exports; a column with no ``total`` key in ``totals`` prints blank."""
        totals = self.data().get("totals") or {}
        cells = []
        for index, column in enumerate(columns):
            if index == 0 and column.key not in totals:
                cells.append("Total")
            elif column.key in totals and column.export:
                cells.append(column.export(totals))
            else:
                cells.append("")
        return cells

    def period_label(self) -> str:
        if self.as_of_report:
            return f"As of {self.as_of():%d %b %Y}"
        return self.period().label

    def filter_summary(self) -> str:
        parts = []
        for spec in self.filter_options():
            if spec["value"]:
                label = dict((str(k), v) for k, v in spec["choices"]).get(spec["value"], spec["value"])
                parts.append(f"{spec['label']}: {label}")
        return " · ".join(parts)

    def is_filtered(self) -> bool:
        return any(self.request.GET.get(key) for key in self.request.GET if key not in ("sort", "dir", "page"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows, sort_context = self.sorted_rows()
        data = self.data()
        query = self.request.GET.copy()
        for key in ("sort", "dir", "page"):
            query.pop(key, None)
        base_query = query.urlencode()
        namespace = self.url_name.split(":")[0]
        export_url = reverse(f"{self.url_name}_export")
        visible = self.columns.visible(self.request.session) if self.columns else set()
        shown = [column for column in self.columns.columns if column.key in visible] if self.columns else []
        column_specs = [
            {"column": column, "sortable": column.key in self.sort_fields, "num": column.numeric}
            for column in shown
        ]
        page_obj = paginator = None
        if self.paginate_by and len(rows) > self.paginate_by:
            paginator = Paginator(rows, self.paginate_by)
            page_obj = paginator.get_page(self.request.GET.get("page"))
            rows = list(page_obj.object_list)
        context.update(sort_context)
        context.update({
            "title": self.title,
            "rows": rows,
            "page_obj": page_obj,
            "paginator": paginator,
            "is_paginated": page_obj is not None,
            "page_query_prefix": f"{base_query}&" if base_query else "",
            "report_filters": self.filter_options(),
            "group_toggle": self.group_toggle,
            "group": self.group(),
            "group_choices": GROUP_CHOICES,
            "filters": self.filters(),
            "totals": data.get("totals") or {},
            "board_tiles": data.get("tiles") or [],
            "extra": data.get("extra") or {},
            "period": self.period(),
            "preset_choices": PRESET_CHOICES,
            "as_of": self.as_of() if self.as_of_report else None,
            "base_query": base_query,
            "export_url": export_url,
            "print_url": f"{export_url}?{base_query}&format=pdf" if base_query else f"{export_url}?format=pdf",
            "columns": visible,
            "column_specs": column_specs,
            "column_menu": self.columns.menu(self.request.session) if self.columns else [],
            "columns_url": reverse(f"{self.url_name}_columns") if self.columns else "",
            "row_span": len(visible),
            "filters_active": self.is_filtered(),
            "table_id": self.table_id,
            "namespace": namespace,
        })
        return context


class ReportExportView(PagePermissionRequiredMixin, PrintContextMixin, TableExportView):
    """Download menu of a ``ReportView``: the same rows, the same visible columns, every format."""

    action = "index"
    report_view = None
    print_template = "reports/print.html"

    def screen(self):
        if not hasattr(self, "_screen"):
            self._screen = self.report_view(request=self.request, kwargs={}, args=())
        return self._screen

    @property
    def columns(self):
        return self.report_view.columns

    @property
    def title(self):
        return self.report_view.title

    @property
    def filename(self):
        return self.report_view.url_name.split(":")[-1].replace("report_", "").replace("_", "-")

    def get_rows(self):
        return self.screen().export_rows()

    def subtitle(self, request) -> str:
        return self.screen().filter_summary()

    def _paper(self, request, header, rows):
        paper = super()._paper(request, header, rows)
        columns = self.columns.exportable(request.session)
        paper.update(self.get_print_context(request))
        paper.update({
            "period_label": self.screen().period_label(),
            "landscape": self.report_view.landscape,
            "num_cols": [i for i, column in enumerate(columns) if getattr(column, "numeric", False)],
            "footer": self.screen().footer_cells(columns) if rows else None,
        })
        return paper


class ReportColumnsView(PagePermissionRequiredMixin, View):
    action = "index"
    report_view = None

    def post(self, request, *args, **kwargs):
        self.report_view.columns.choose(request.session, request.POST.getlist("columns"))
        back = request.POST.get("back", "")
        target = reverse(self.report_view.url_name)
        return redirect(f"{target}?{back}" if back else target)
