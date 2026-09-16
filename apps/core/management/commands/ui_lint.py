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


def is_component(rel):
    return rel.startswith(COMPONENT_DIRS)


def is_print(rel):
    name = rel.rsplit("/", 1)[-1]
    return any(marker in name for marker in PRINT_MARKERS)


def line_of(text, index):
    return text.count("\n", 0, index) + 1


class Command(BaseCommand):
    help = "Check templates against the UI system rules."

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        problems = []

        for path in sorted((base / "templates").rglob("*.html")):
            rel = path.relative_to(base / "templates").as_posix()
            text = path.read_text(encoding="utf-8")
            markup = SCRIPT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)

            for match in MULTILINE_COMMENT_RE.finditer(text):
                problems.append((rel, line_of(text, match.start()), "multi-line {# #} comment"))

            if is_component(rel) or is_print(rel):
                continue

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

        if problems:
            raise CommandError(f"ui_lint: {len(problems)} problem(s)")
        self.stdout.write(self.style.SUCCESS("ui_lint: clean"))
