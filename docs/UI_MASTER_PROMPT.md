# UI/UX Consistency — Master Prompt

Paste everything below the line into a new session. Run it one phase at a time; do not start a phase until the previous one is approved.

---

You are a principal frontend engineer and UI/UX lead (30+ years, dense data-entry ERP systems). This is a Django + Tailwind ERP (`templates/`, `static/src/app.css`, `static/src/components.css`, `templates/components/`). Read `CLAUDE.md` first; every rule there still applies (no prose on screens, no narrative comments, light-first + `.dark` pair, no CDNs, `npm run build:css`, weights 3dp / money 2dp).

## Goal

One design system for the whole app. Every input, button, icon, table, row action, filter, modal, tab, status pill, totals panel and page header comes from a single component. Change it in one place → every screen changes. No screen owns its own look.

The reference is the Purchase Order work: `templates/inventory/purchase_order_list.html` (board) and `templates/inventory/purchase_order_form.html` (document form). Every list and every form must end up looking and behaving like those two — but built from shared components, not from their inline `<style>` blocks.

## Known problems (verified)

- `purchase_order_list.html` carries ~180 lines of inline `<style>`; `purchase_order_form.html` ~220 lines; `_purchase_theme.html`, `_master_detail_css.html`, `_amount_panel.html` and ~16 templates hold private CSS.
- ~55 table screens (finance, hr, payroll, organizations, access_control, configurations, products, production, most of inventory) do not use `components/table/board_theme.html`.
- ~40 templates write raw `<input>` markup instead of `components/forms/*`.
- `components/forms/input.html` hard-codes long Tailwind strings, `mb-5` spacing and renders `help_text` (conflicts with CLAUDE.md rule 11).
- Buttons, icons and row actions are mixed: some via `components/ui/button.html`, some raw `<a class="...">`, icons as HTML entities in different sizes.
- Pages scroll where they should not: full-page scroll wrapping a table that also scrolls, oversized padding, stacked cards with gaps.

## Phase 1 — Audit (read-only, no edits)

Produce `docs/UI_AUDIT.md` with one table per module:

| Template | Type (list / form / detail / print / report) | Inline `<style>` lines | Raw inputs | Raw buttons | Uses board_theme | Scroll issues | Notes |

Plus: a list of every distinct visual variant found (input heights, radii, font sizes, button styles, icon sources, spacing values, colors not from tokens). This list is what Phase 2 collapses. Stop and wait for approval.

## Phase 2 — Design tokens (single source)

In `static/src/app.css` define CSS variables under `:root` and override under `.dark`:

- Color: `--primary`, `--primary-hover`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--danger`, `--success`, `--warning`, `--info`, plus status colors used by pills.
- Size: `--control-h` (one height for inputs, selects, buttons: 2.25rem), `--control-h-sm` (1.875rem, table/filter bar), `--radius`, `--radius-sm`.
- Spacing scale: `--gap-1..--gap-6` (4/8/12/16/20/24px). No other spacing values in components.
- Type: `--fs-xs`, `--fs-sm` (base for data), `--fs-md`, `--fs-lg` (page title). Numbers use `font-variant-numeric: tabular-nums`, right-aligned.
- Icon: `--icon-sm` (14px), `--icon-md` (16px), `--icon-lg` (20px).

Density: compact ERP. Body 13–14px, table rows ~36px, form field vertical gap 12px, no card padding above 16px.

Every component class below uses only these tokens. Delete hard-coded hex values and ad-hoc Tailwind colors from components.

## Phase 3 — Component library

Move every shared rule into `static/src/components.css` as `@layer components` classes. One class family per component, BEM-light names: `.field`, `.field__label`, `.control`, `.btn`, `.btn--primary`, `.icon-btn`, `.board`, `.board-table`, `.pill`, `.tabs`, `.modal`, `.totals`.

Build or refactor these templates (each takes parameters via `{% include ... with ... only %}`; no screen passes raw classes except an optional `extra`):

**Forms** — `templates/components/forms/`
- `field.html` — auto-picks the widget (text, number, money, weight, date, select, searchable select, textarea, checkbox, file) from the bound field. Label + control + error. No help text unless `rule=` is passed (few words, e.g. "Max 20 chars").
- `input.html`, `select.html`, `date.html`, `textarea.html`, `checkbox.html`, `radio.html`, `file_upload.html` — thin, all using `.control`.
- `money.html` (2dp, `amount-format.js`) and `weight.html` (3dp, never `amount-format.js`).
- `form_grid.html` — responsive grid: `cols=2|3|4|6`; fields flow in; no manual `grid-cols-*` on screens.
- `section.html` — titled group with a hairline border, no card shadow, no description text.
- `line_items.html` — the editable item table from the PO form (add row, delete row, keyboard Enter → next cell, totals footer).
- `totals_panel.html` — replaces `inventory/_amount_panel.html` for all documents.
- `submit_bar.html` — sticky bottom bar: Cancel (ghost) · secondary actions · primary on the right. Same order on every form.
- Tailwind default class strings on Django widgets set once (form mixin in `apps/core/forms.py` or a template filter in `core_extras.py`), not per template.

**Buttons & icons** — `templates/components/ui/`
- `button.html` — variants: primary, secondary, ghost, danger; sizes: sm, md. Always `--control-h`.
- `icon_button.html` — square, `title=` tooltip required, used for all row actions and toolbar icons.
- `icon.html` — one icon set only (inline SVG sprite in `static/vendor/` or a single `icons/` template folder). Parameter `name=`. Replace all HTML entities and emojis used as icons.
- `page_header.html` — back button (optional) + title + right-side actions slot. No subtitle/lede.
- `modal.html`, `confirmation_dialog.html`, `tabs.html`, `dropdown.html`, `toast`, `alert` — one of each.

**Tables** — `templates/components/table/`
- `board_theme.html` stays the only board stylesheet include; all PO-list inline CSS that is generic moves into it (or into `components.css`).
- `board.html` — wrapper: tiles row + filter bar + table + footer + pagination. A list screen should be mostly this include plus its column definitions.
- `tiles.html` — clickable count tiles over the filtered set, active state.
- `filter_bar.html`, `sort_header.html`, `status_badge.html` (→ `.pill`), `actions.html` (icon row actions: view, edit, print, reverse, deactivate — same order and icons everywhere), `pagination.html`, `empty_state.html`, `bulk_actions.html`, export.
- `table_footer.html` — page totals, numeric columns right-aligned.
- Column visibility (the PO `columns` pattern) as a reusable mixin/selector, not per view.

**Detail & print**
- `detail_header.html` (document no, date, party, status pill, action buttons) and `detail_grid.html` (label/value pairs).
- One print base (`layouts/print.html`) that all `*_print.html` / receipts extend.

Rule: if two screens need the same markup, it becomes a component. If a component needs a variant, add a parameter — never copy it.

## Phase 4 — Layout & scroll rules

- One scroll container per page. App shell (sidebar + topbar) fixed; the content area scrolls. Tables inside a board scroll horizontally only (`overflow-x:auto`); no nested vertical scroll unless it is a line-items grid with a sticky header.
- Forms fit a 1366×768 laptop without scrolling for header fields; line items scroll inside, submit bar is sticky.
- Table header sticky. Long text truncates with `title=`.
- No empty space: no page lede, no hero cards on work screens, max content padding 16px, gap between sections 12–16px.
- Date inputs ≥ 11.5rem. Numeric inputs right-aligned.
- Mobile ≥ 400px: form grid collapses to 1 column, board table scrolls horizontally, submit bar stays sticky.

## Phase 5 — UX behavior (same everywhere)

- Keyboard: `Enter` moves to the next field in forms/line items; `Ctrl+S` saves; `Esc` closes modal; `/` focuses search on boards.
- Autofocus the first editable field on forms.
- Same labels and order for actions: Cancel · Save & Print · Save & New · Save.
- Destructive actions (reverse, deactivate) always go through `confirmation_dialog.html`.
- Native `required` only; server errors render under the field and a single toast at top.
- Status colors mean the same thing on every screen (draft=slate, pending=amber, approved/posted=green, reversed/cancelled=rose, partial=blue).
- Business terms in labels (CLAUDE.md rule 22).

## Phase 6 — Migration, module by module

Order: inventory (purchase → sales → POS → items/suppliers) → finance → products/production/godowns → hr/payroll → organizations/access_control/configurations → portal dashboard.

For each screen:
1. Replace markup with components; delete its `<style>` block (keep only truly screen-specific rules, ≤ ~20 lines, and justify in the PR, not in code).
2. Keep field layout unless told otherwise (CLAUDE.md rule 21; wheat purchase slip stays as-is).
3. Keep all `x-data` / JS behavior working; do not change views, forms logic or URLs unless a component needs a context value.
4. Add missing `select_related` if the new board renders more columns.
5. `npm run build:css`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py test apps.inventory.tests`.
6. Update `docs/UI_AUDIT.md` row to done. Report the screen list per batch; the user tests in the browser.

Batch size: one module per session. Never mix component changes and screen migrations in the same batch without saying so.

## Phase 7 — Guard rails

- Write `docs/UI_SYSTEM.md`: tokens, component list with include examples, list-screen and form-screen skeletons (copy-ready), do/don't table.
- Add a check (`apps/core/management/commands/ui_lint.py`) that fails on: `<style` in non-component templates, raw `<input`/`<button` outside `components/`, hex colors outside `app.css`, templates with `<table` not including the board component, multi-line `{# #}`.
- Add a line to `CLAUDE.md` pointing to `docs/UI_SYSTEM.md` and the lint command.

## Definition of done

- Every list screen = board component. Every form = form_grid + fields + submit_bar. Every detail = detail_header + detail_grid. Every print extends the print base.
- `ui_lint` passes with zero exceptions (or an explicit, short allow-list).
- Changing `--control-h`, `--primary` or `button.html` visibly changes every screen.
- No double scrollbars; no screen needs page scroll just to reach the header fields.
