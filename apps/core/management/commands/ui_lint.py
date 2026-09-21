import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.S | re.I)
STYLE_RE = re.compile(r"<style\b", re.I)
RAW_CONTROL_RE = re.compile(r"<(input|button|select|textarea)\b([^>]*)>", re.I)
HIDDEN_RE = re.compile(r"""type\s*=\s*["']?hidden""", re.I)
HEX_RE = re.compile(r"(?<![&\w])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b(?!;)")
TABLE_RE = re.compile(
    r"<table\b(?![^>]*class=[\"'][^\"']*\b(?:board-table|data-table|li-table|lines-table|doc-table|order-pick-lines|wp-tbl|wp-eff)\b)",
    re.I,
)
MULTILINE_COMMENT_RE = re.compile(r"\{#(?:(?!#\}).)*\n", re.S)

COMPONENT_DIRS = ("components/", "layouts/")
PRINT_MARKERS = ("print", "receipt", "export_doc", "pdf")
BOARD_MARKERS = ('component "table/board"', "components/table/board.html", "components/table/table.html")
BOARD_TAG = 'component "table/board"'
FORM_RE = re.compile(r"<form\s[^>]*method\s*=\s*[\"']post", re.I)
FORM_SHELLS = ("components/forms/crud_form.html", 'component "forms/crud_form"', "components/forms/tabbed_form.html", 'component "forms/tabbed_form"', "components/forms/submit_bar.html", 'component "forms/submit_bar"')
RAW_PILL_RE = re.compile(r'<span class="pill pill--(?:draft|pending|posted|reversed|partial|closed|danger)"')
DELETE_ACTION_RE = re.compile(r"components/table/actions\.html[^%]*\sdelete_url=")

# Master list screens from docs/UI_AUDIT.md; these may never carry a delete action.
MASTER_LIST_TEMPLATES = (
    "inventory/supplier_list.html",
    "inventory/simple_list.html",
    "inventory/item_list.html",
    "products/product_list.html",
    "godowns/godown_list.html",
    "hr/employee_list.html",
    "organizations/organization_list.html",
    "organizations/branch_list.html",
    "access_control/role_list.html",
    "access_control/permission_list.html",
    "access_control/user_assignment_list.html",
    "configurations/master_list.html",
    "finance/account_configuration_list.html",
    "finance/fiscal_year_list.html",
    "payroll/employee_salary_list.html",
)
# Boards that are not registers (detail pages, dashboard, single-purpose grids) need no sort header.
SORT_EXEMPT = (
    "_detail.html", "portal/dashboard.html", "products/link_grid.html", "products/opening_balances.html", "products/rate_update.html",
    "inventory/manual_transaction.html", "inventory/pos_list.html", "products/product_list.html",
    # Chronological ledgers carry a running balance; reordering them would make the balance column meaningless.
    "finance/account_ledger.html", "finance/daybook.html", "inventory/ledger_list.html", "inventory/customer_ledger_list.html",
)
# Forms outside the contract by decision (docs/UI_SYSTEM.md, Screen contracts).
FORM_EXEMPT = ("auth/login.html", "inventory/wheat_purchase_form.html")


def is_component(rel):
    return rel.startswith(COMPONENT_DIRS)


def is_form_template(rel):
    name = rel.rsplit("/", 1)[-1]
    return "form" in name and not name.startswith("_")


def is_print(rel):
    name = rel.rsplit("/", 1)[-1]
    return any(marker in name for marker in PRINT_MARKERS)


def line_of(text, index):
    return text.count("\n", 0, index) + 1


class Command(BaseCommand):
    help = "Check templates against the UI system rules."

    def add_arguments(self, parser):
        parser.add_argument("--lenient", action="store_true", help="Report screen-contract breaches without failing.")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        problems = []
        contract = []

        for path in sorted((base / "templates").rglob("*.html")):
            rel = path.relative_to(base / "templates").as_posix()
            text = path.read_text(encoding="utf-8")
            markup = SCRIPT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)

            for match in MULTILINE_COMMENT_RE.finditer(text):
                problems.append((rel, line_of(text, match.start()), "multi-line {# #} comment"))

            if is_component(rel) or is_print(rel):
                continue

            if BOARD_TAG in text and not rel.endswith(SORT_EXEMPT) and "components/table/sort_header.html" not in text:
                contract.append((rel, line_of(text, text.index(BOARD_TAG)), "board without sort_header"))

            if BOARD_TAG in text and not rel.endswith("_detail.html"):
                for match in RAW_PILL_RE.finditer(text):
                    contract.append((rel, line_of(text, match.start()), "raw status pill; use table/status_badge"))

            if rel in MASTER_LIST_TEMPLATES:
                for match in DELETE_ACTION_RE.finditer(text):
                    contract.append((rel, line_of(text, match.start()), "delete action on a master list"))

            form_match = FORM_RE.search(markup) if is_form_template(rel) else None
            if form_match and rel not in FORM_EXEMPT and not any(shell in text for shell in FORM_SHELLS):
                contract.append((rel, line_of(markup, form_match.start()), "form without crud_form / tabbed_form / submit_bar"))

            for match in STYLE_RE.finditer(markup):
                problems.append((rel, line_of(markup, match.start()), "<style> outside components"))

            for match in RAW_CONTROL_RE.finditer(markup):
                if HIDDEN_RE.search(match.group(2)):
                    continue
                problems.append((rel, line_of(markup, match.start()), f"raw <{match.group(1).lower()}>"))

            for match in HEX_RE.finditer(markup):
                problems.append((rel, line_of(markup, match.start()), f"hex colour {match.group(0)}"))

            if not any(marker in text for marker in BOARD_MARKERS):
                for match in TABLE_RE.finditer(markup):
                    problems.append((rel, line_of(markup, match.start()), "<table> without board or component class"))

        css = base / "static" / "src" / "components.css"
        css_text = css.read_text(encoding="utf-8")
        for match in HEX_RE.finditer(css_text):
            problems.append(("static/src/components.css", line_of(css_text, match.start()), f"hex colour {match.group(0)}"))

        for rel, line, message in problems:
            self.stdout.write(f"{rel}:{line}: {message}")

        if contract:
            self.stdout.write(self.style.WARNING(f"contract ({len(contract)} breach(es))"))
            for rel, line, message in contract:
                self.stdout.write(f"  {rel}:{line}: {message}")

        if problems or (contract and not options["lenient"]):
            raise CommandError(f"ui_lint: {len(problems)} problem(s), {len(contract)} contract breach(es)")
        self.stdout.write(self.style.SUCCESS("ui_lint: clean" + (f" ({len(contract)} contract breach(es))" if contract else "")))
