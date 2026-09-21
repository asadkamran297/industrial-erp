# UI System

One design system for every screen. Check with `python manage.py ui_lint` before handing work over; it must print `ui_lint: clean`.

## Files

| File | Holds |
|---|---|
| `static/src/app.css` | Fonts and design tokens only (`:root`, then `.dark` beneath) |
| `static/src/components.css` | Every shared class. Plain CSS, tokens only, no hex |
| `static/js/ui.js` | Keyboard, modals, confirm dialog, table export, `rowFold()`, `dateRange()` |
| `apps/core/icons.py` | SVG icon set used by `{% icon %}` |
| `apps/core/templatetags/core_extras.py` | `icon`, `component`/`slot`, `capture`, `control`, `field_kind` |
| `templates/components/` | Components (only place allowed `<style>` and raw controls) |
| `templates/layouts/` | `portal.html`, `embed.html`, `print.html` |

Run `npm run build:css` after touching classes.

## Tokens

| Group | Tokens |
|---|---|
| Surface | `--app-bg` `--surface` `--surface-alt` `--surface-muted` `--surface-sunk` `--overlay` |
| Text | `--text-strong` `--text` `--text-body` `--text-soft` `--text-muted` `--text-faint` `--text-ghost` |
| Border | `--border` `--border-soft` `--border-strong` |
| Brand | `--primary` `--primary-hover` `--primary-soft` `--primary-soft-2` `--primary-line` `--ring-primary` `--on-primary` (derived from user colour on `body`) |
| Tone | `--success*` `--danger*` `--warning*` `--info*` `--violet*` `--teal*` `--neutral*` (`-soft`, `-line`, `-strong`) |
| Status | `--st-{draft,pending,posted,reversed,partial,closed}-{fg,bg}` |
| Size | `--control-h` `--control-h-sm` `--control-h-lg` `--row-h` `--topbar-h` `--date-w` |
| Spacing | `--gap-1` … `--gap-6` |
| Type | `--fs-2xs` `--fs-xs` `--fs-sm` `--fs-md` `--fs-lg` `--fs-xl` |
| Shape | `--radius-sm` `--radius` `--radius-lg` `--radius-pill` `--shadow-sm/md/lg` |
| Icon | `--icon-sm` `--icon-md` `--icon-lg` |
| Charts | `--viz-axis` `--viz-grid` `--series-*` |
| Accounts | `--type-{asset,liability,capital,revenue,expense}` (+ `-bg`) |

## Tags

```django
{% icon "edit" size="sm" %}
{% component "table/board" title="Items" %}...{% slot actions %}...{% endslot %}{% endcomponent %}
{% capture as add_url %}{% if can_add %}{% url 'app:create' %}{% endif %}{% endcapture %}
{{ form.field|control }}
```

`component` passes the body as `slot` and named slots as `slots.<name>`. Add `only` for an isolated context, but never on a component whose body or template renders `{% csrf_token %}`.

## Components

### Forms (`components/forms/`)

| Component | Use |
|---|---|
| `field.html` | Any bound Django field: label, control, error. `field= extra= label=` |
| `control.html` | Unbound control. `type` (input types, `select` with slot, `textarea`) `name id label value kind=money|weight|num size=sm cell required readonly attrs` |
| `money.html` / `weight.html` | Money (2 dp, amount-format) / weight (3 dp, no amount-format) |
| `form_grid.html` | Whole form in a grid. `form= cols=` |
| `section.html` | Titled block. `title=` + slot |
| `form_errors.html` | Non-field errors |
| `crud_form.html` | Page head + card + grid + submit bar. `title form cancel_url cols=3 narrow multipart embed show_new save_label` + slot |
| `tabbed_form.html` | Party master form: identity row, Address / Credit & Balance / Registration / Additional tabs. `name_field phone_field email_field city_field addr1_field addr2_field opening_field opening_date_field limit_field period_field registration_fields extra_fields embed` |
| `line_items.html` | Line-item grid wrapper |
| `totals_panel.html`, `totals_row.html`, `amount_words.html` | Document totals |
| `submit_bar.html` | Save / Cancel. `cancel_url label show_print show_new floating form_id embed prepared_by save_id save_name save_value save_attrs print_id` + slot for extra buttons |
| `switch.html` | Toggle |

```django
{% include "components/forms/field.html" with field=form.name only %}
{% include "components/forms/control.html" with type="date" name="date_from" label="From" value=date_from only %}
{% include "components/forms/money.html" with field=form.amount only %}
```

### UI (`components/ui/`)

| Component | Use |
|---|---|
| `page_header.html` | Title, back, meta, status; `slots.fields`, `slots.actions` |
| `button.html` | `label variant=primary|secondary|ghost|danger|success size=sm|lg icon href confirm post data` |
| `icon_button.html` | `icon title tone=go|danger|success bordered href confirm post reason attrs` |
| `back_button.html` | Back link |
| `modal.html` | Alpine (`show`) or plain (`data-modal`) modal with head/body/foot |
| `confirmation_dialog.html` | Shared confirm (already in `portal.html`) |
| `tabs.html`, `tab.html`, `tab_button.html` | Tabs |
| `alert.html`, `messages.html` | Alerts / flash messages |
| `card.html` | Card |
| `detail_header.html`, `detail_grid.html`, `detail_item.html` | Detail pages |
| `stat_card.html` | Dashboard / detail figure. `label value icon tone hint mask_key negative` (tones as `tile.html`) |
| `dropdown.html`, `breadcrumb.html`, `search_box.html`, `frame_modal.html`, `icon.html` | As named |

```django
{% include "components/ui/button.html" with label="Post" variant="primary" icon="post" data="save" only %}
{% include "components/ui/icon_button.html" with icon="trash" title="Delete" tone="danger" href=delete_url confirm="Delete?" post=True only %}
```

### Tables (`components/table/`)

| Component | Use |
|---|---|
| `board.html` | Every list screen: head, tiles, filter bar, scroll table, pagination |
| `tiles.html`, `tile.html` | Status tiles (`board_tiles` from the mixin) |
| `filter_bar.html` | Search, filters, date range, columns, export |
| `sort_header.html` | Sortable `<th>` |
| `status_badge.html` | Status pill. `status label tone title` |
| `actions.html` | Row icons: `view_url edit_url print_url reverse_url deactivate_url delete_url` |
| `table_footer.html` | Page-total row. `lead value tail` |
| `empty_row.html` | Empty `<tr>`. `span label` |
| `expand_toggle.html`, `lines_row.html` | Folding line rows |
| `pagination.html`, `empty_state.html` | As named |

Tables outside a board must carry a component class: `board-table`, `data-table`, `li-table`, `lines-table`, `doc-table`.

## Screen contracts

Every screen is one of six kinds. A kind has one shape; a screen that needs something the shape lacks extends the component, never the screen. Exceptions are listed at the end of this section and nowhere else.

### MASTER LIST

- `table/board` with `title` = plural business term, `add_label` = singular, `search_placeholder` = "Search <plural>", `table_id`.
- Tiles All / Active / Inactive counted over the filtered set via `SearchFilterPaginationMixin.get_board_tiles`; every master view sets `filter_fields = {"status": "status"}` and `get_filter_specs` with `RECORD_STATUS_CHOICES`. Money-bearing masters (supplier, customer) add a balance-total tile.
- First column = name as `<a class="doc-num">` to the detail page. Every master has a detail page.
- `SortableListMixin`; `sort_header` on every field-backed column; `default_sort = "name"`.
- Status = `components/forms/switch.html` when `can_edit`, else `status_badge`. No delete action on any master (CLAUDE.md rule 23); deactivate only.
- Row actions order: view, edit, ledger (when the master has an account).
- `ColumnSet` column picker and export on every list. `table_footer` when a money column exists. Empty row "No <plural>." Search over name, code, phone, email where present.

### MASTER FORM

- `crud_form.html` `cols=3` for ≤12 fields; `components/forms/tabbed_form.html` (extracted from `supplier_form.html`) for more. Embedded mode (`embed=1`) supported on both.
- Field order: identity → contact → registration → money → status, remarks.
- Submit bar: Cancel, Save & New, Save. Labels only; searchable selects; `--date-w` dates; money 2 dp, weight 3 dp.

### DOCUMENT LIST

- Same as the Purchase Orders board: status tiles, filter bar with date range, sort headers, `status_badge` (never switch), expand row for lines, actions view / edit-if-draft / print / reverse-if-posted, page-total footer, pagination, export, column picker.

### DOCUMENT FORM

- `page_header` with back, header field grid, `line_items`, `totals_panel`, `submit_bar` (Cancel, Save & Print, Save), `floating` on long forms, one page without vertical scroll.
- Document number (read-only, `strong num`, in `.head-no`) and document date sit in the `page_header` `fields` slot beside the title, never in the form body. The date carries `form_id` (or a `form=` widget attr) because the header is outside the `<form>`.
- Every party picker (supplier, customer, account) shows a balance chip under it: `select[data-balance-chip="<chip id>"]` with `data-balance-owed` / `data-balance-credit` labels, each `<option data-balance>`, `<p class="bal-chip hidden">`; `static/js/party-balance.js` paints it on load and change. Supplier lists come from `suppliers_with_balance()` / `customers_with_balance()` (`apps/inventory/views.py`), balances from the ledger account (`finance.services._party_balances`), never from the master's opening figure alone.
- Save posts and returns to the document's list with a `messages.success`; no confirm/preview modal before save.

### DETAIL

- `detail_header` (title, status pill, back, actions edit / print / ledger), `detail_grid`, then related tables as `lines-table` / `board-table`.

### DASHBOARD

- `components/ui/stat_card.html` only, tones/icons from `STATUS_TILE_TONES`, `|amount` for money.

### Adjustments from `docs/UI_AUDIT.md`

- Item Categories and Units of Measure stay two-pane screens (`class_list.html`, `uom_list.html`); they are outside MASTER LIST. Their edit panes follow MASTER FORM field rules.
- The wheat purchase slip (`wheat_purchase_form.html`) mirrors the paper slip (CLAUDE.md rule 21) and is outside DOCUMENT FORM for its body layout; the header (number + date in `page_header`), balance chip and direct save still apply.
- Documents that post on save (purchase return, account voucher) may label the submit bar Cancel, Save Draft, Save & Post in place of Save & Print.
- Salary Items has no status field: no tiles, no switch, no badge; the rest of MASTER LIST applies.
- Until a list is converted to `ColumnSet`, the browser column picker in `filter_bar.html` satisfies the column-picker rule; new lists use `ColumnSet`. Suppliers, Customers, Products and the purchase boards are on `ColumnSet`.
- Products stays a tree (headings above items) and is outside the sort rule; every other master list sorts.
- Ledgers (account ledger, daybook, item ledger, customer ledger) are chronological with a running balance and do not sort.
- POS entry (`pos_list.html`) is an entry screen with a recent-sales sub-board; the register is Sale Invoices.
- Salary Items and Payroll Runs can still be removed from an employee's record (child rows), not from the master list.

### Lint

`python manage.py ui_lint` fails on contract breaches, listed under a `contract` heading (`--lenient` reports without failing). Checks: board template without `sort_header` (chronological ledgers, the product tree, detail pages and single-purpose grids are listed in `SORT_EXEMPT`); raw `<span class="pill pill--…">` in a board (use `table/status_badge`, which takes `status`, `label`, `tone`, `title`); master list template (`MASTER_LIST_TEMPLATES`) passing `delete_url` to `table/actions`; `*form*.html` outside `components/` that uses none of `crud_form`, `tabbed_form`, `submit_bar`.

### Shared view helpers (`apps/core/views.py`, `apps/core/mixins.py`)

| Helper | Use |
|---|---|
| `ToggleStatusView` | Master activate/deactivate. `model page success_url_name` |
| `MasterDetailView` | DETAIL page from `detail_fields = (("Label", "attr"[, "money"\|"weight"\|"wide"]), …)`; `kind title_attr subtitle_attr list_url_name edit_url_name`; extend `core/master_detail.html` block `related` for tables |
| `SaveAndNewMixin` | Save & New on create views (reopens the blank form) |
| `report_sort(request, rows, fields, default)` | Sort dict/object report rows and return the `sort_header` context |
| `PartyColumnsMixin` (inventory) | `ColumnSet` menu, export url, `row_span`, footer lead/tail for party lists |

## List screen skeleton (MASTER LIST)

View: `SortableListMixin, SearchFilterPaginationMixin`, `filter_fields = {"status": "status"}`, `search_fields`, `sort_fields`, `default_sort = "name"`, `get_filter_specs` with `RECORD_STATUS_CHOICES`; a `ToggleStatusView` and a `MasterDetailView` per master.

```django
{% extends "layouts/portal.html" %}
{% block content %}
{% capture as add_url %}{% if can_add %}{% url 'app:thing_create' %}{% endif %}{% endcapture %}
{% component "table/board" title="Things" add_url=add_url add_label="Thing" search_placeholder="Search things" table_id="thing-table" %}
  <thead><tr>
    {% include "components/table/sort_header.html" with label="Name" field="name" %}
    {% include "components/table/sort_header.html" with label="Code" field="code" %}
    <th>Phone</th><th>Status</th><th class="actions-col">Actions</th>
  </tr></thead>
  <tbody>
    {% for row in object_list %}
    <tr>
      <td><a class="doc-num" href="{% url 'app:thing_detail' row.pk %}">{{ row.name }}</a></td>
      <td>{{ row.code }}</td>
      <td>{{ row.phone }}</td>
      <td>
        {% if can_edit %}{% url 'app:thing_toggle_status' row.pk as toggle_url %}{% capture as is_on %}{% if row.status == 'active' %}1{% endif %}{% endcapture %}{% include "components/forms/switch.html" with url=toggle_url checked=is_on title="Active" %}
        {% else %}{% include "components/table/status_badge.html" with status=row.status label=row.get_status_display only %}{% endif %}
      </td>
      <td class="actions-col">
        {% url 'app:thing_detail' row.pk as view_url %}
        {% capture as edit_url %}{% if can_edit %}{% url 'app:thing_update' row.pk %}{% endif %}{% endcapture %}
        {% include "components/table/actions.html" with view_url=view_url edit_url=edit_url only %}
      </td>
    </tr>
    {% empty %}
    {% include "components/table/empty_row.html" with span=5 label="No things." only %}
    {% endfor %}
  </tbody>
{% endcomponent %}
{% endblock %}
```

## List screen skeleton (DOCUMENT LIST)

Same view mixins plus `date_filters = [{"field": "date"}]`; `default_sort` = the date field, `default_sort_dir = "desc"`.

```django
{% component "table/board" title="Things" add_url=add_url add_label="Thing" search_placeholder="Search things" table_id="thing-table" %}
  <thead><tr>
    <th></th>
    {% include "components/table/sort_header.html" with label="Number" field="number" %}
    {% include "components/table/sort_header.html" with label="Date" field="date" %}
    <th>Party</th><th class="num">Amount</th><th>Status</th><th class="actions-col">Actions</th>
  </tr></thead>
  <tbody>
    {% for row in object_list %}
    <tr>
      <td>{% include "components/table/expand_toggle.html" with pk=row.pk only %}</td>
      <td><a class="doc-num" href="{% url 'app:thing_detail' row.pk %}">{{ row.number }}</a></td>
      <td>{{ row.date|date:"d M Y" }}</td>
      <td>{{ row.party }}</td>
      <td class="num">{{ row.amount|amount }}</td>
      <td>{% include "components/table/status_badge.html" with status=row.status label=row.get_status_display only %}</td>
      <td class="actions-col">
        {% url 'app:thing_detail' row.pk as view_url %}
        {% capture as edit_url %}{% if can_edit and row.status == 'draft' %}{% url 'app:thing_update' row.pk %}{% endif %}{% endcapture %}
        {% url 'app:thing_print' row.pk as print_url %}
        {% capture as reverse_url %}{% if can_edit and row.status == 'posted' %}{% url 'app:thing_reverse' row.pk %}{% endif %}{% endcapture %}
        {% include "components/table/actions.html" with view_url=view_url edit_url=edit_url print_url=print_url reverse_url=reverse_url only %}
      </td>
    </tr>
    {% include "components/table/lines_row.html" with pk=row.pk lines=row.lines.all span=7 only %}
    {% empty %}
    {% include "components/table/empty_row.html" with span=7 label="No things." only %}
    {% endfor %}
  </tbody>
  {% if object_list %}{% include "components/table/table_footer.html" with lead=4 value=page_total|amount tail=2 only %}{% endif %}
{% endcomponent %}
```

## Form screen skeleton (MASTER FORM)

≤12 fields:

```django
{% extends embed_layout|default:"layouts/portal.html" %}
{% block content %}
{% url 'app:thing_list' as cancel_url %}
{% include "components/forms/crud_form.html" with title=page_title form=form cancel_url=cancel_url cols=3 show_new=True embed=embed %}
{% endblock %}
```

More than 12 fields:

```django
{% extends embed_layout|default:"layouts/portal.html" %}
{% block content %}
{% url 'app:thing_list' as cancel_url %}
{% component "forms/tabbed_form" title=page_title form=form cancel_url=cancel_url tabs=tabs show_new=True embed=embed %}
  {% slot tab_address %}...{% endslot %}
  {% slot tab_credit %}...{% endslot %}
{% endcomponent %}
{% endblock %}
```

## Form screen skeleton (DOCUMENT FORM)

```django
{% extends "layouts/portal.html" %}
{% block content %}
{% url 'app:thing_list' as cancel_url %}
<form method="post" class="form-stack">{% csrf_token %}
  {% component "ui/page_header" title=page_title back=True back_url=cancel_url %}
    {% slot fields %}{% include "components/forms/control.html" with id="number" label="No" value=next_number readonly=True only %}{% include "components/forms/control.html" with type="date" name="date" label="Date" value=date_value required=True only %}{% endslot %}
  {% endcomponent %}
  {% include "components/forms/form_errors.html" with form=form only %}
  <div class="card"><div class="card-body form-grid form-grid--cols-3 doc-head-fields--compact">
    {% include "components/forms/field.html" with field=form.party only %}
  </div></div>
  {% component "forms/line_items" %}...{% endcomponent %}
  {% include "components/forms/totals_panel.html" with totals=totals only %}
  {% include "components/forms/submit_bar.html" with cancel_url=cancel_url show_print=True floating=True only %}
</form>
{% endblock %}
```

Print screens extend `layouts/print.html` (blocks `title`, `toolbar`, `print_header`, `watermark`, `print_content`, `print_footer`).

## Rules

- Tokens only in `app.css`; no hex anywhere else.
- No `<style>` outside `components/` and `layouts/`.
- No raw `<input>`, `<button>`, `<select>`, `<textarea>` outside components (hidden inputs allowed).
- Every list screen uses `table/board`.
- Light rule first, `.dark` rule directly beneath.
- Labels only: no help text, placeholders that explain, or page ledes.
- Dates use `--date-w`; weights 3 dp, money 2 dp.
- `{# #}` single-line only.
- Keyboard: Enter moves to next field (opt out with `data-own-keys`), Ctrl+S clicks `[data-save]`, `/` focuses `[data-board-search]`, Esc closes modals.

## ui_lint

`python manage.py ui_lint` fails on: `<style>` outside components/layouts, raw controls, hex colours in templates or `components.css`, tables without board or component class, multi-line `{# #}`. Print documents (`*print*`, `*receipt*`) are exempt from all but the comment check. Contract checks (see Screen contracts, Lint) fail the build; `--lenient` only reports them.
