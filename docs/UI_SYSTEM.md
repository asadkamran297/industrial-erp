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
| `crud_form.html` | Page head + card + grid + submit bar. `title form cancel_url cols narrow multipart` + slot |
| `line_items.html` | Line-item grid wrapper |
| `totals_panel.html`, `totals_row.html`, `amount_words.html` | Document totals |
| `submit_bar.html` | Save / Cancel. `cancel_url label show_print show_new floating form_id` |
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
| `dropdown.html`, `breadcrumb.html`, `search_box.html`, `stat_card.html`, `frame_modal.html`, `icon.html` | As named |

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
| `status_badge.html` | Status pill. `status label` |
| `actions.html` | Row icons: `view_url edit_url print_url reverse_url deactivate_url delete_url` |
| `table_footer.html` | Page-total row. `lead value tail` |
| `empty_row.html` | Empty `<tr>`. `span label` |
| `expand_toggle.html`, `lines_row.html` | Folding line rows |
| `pagination.html`, `empty_state.html` | As named |

Tables outside a board must carry a component class: `board-table`, `data-table`, `li-table`, `lines-table`, `doc-table`.

## List screen skeleton

View uses `SearchFilterPaginationMixin` (gives `board_tiles`, `filters_active`, `base_query`, `page_total` when set).

```django
{% extends "layouts/portal.html" %}
{% block content %}
{% capture as add_url %}{% if can_add %}{% url 'app:thing_create' %}{% endif %}{% endcapture %}
{% component "table/board" title="Things" add_url=add_url add_label="Thing" table_id="thing-table" %}
  <thead><tr>
    {% include "components/table/sort_header.html" with label="Number" field="number" %}
    <th>Party</th><th class="num">Amount</th><th>Status</th><th class="actions-col">Actions</th>
  </tr></thead>
  <tbody>
    {% for row in object_list %}
    <tr>
      <td class="doc-num">{{ row.number }}</td>
      <td>{{ row.party }}</td>
      <td class="num">{{ row.amount|amount }}</td>
      <td>{% include "components/table/status_badge.html" with status=row.status label=row.get_status_display only %}</td>
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
  {% if object_list %}{% include "components/table/table_footer.html" with lead=2 value=page_total|amount tail=2 only %}{% endif %}
{% endcomponent %}
{% endblock %}
```

## Form screen skeleton

Simple:

```django
{% extends "layouts/portal.html" %}
{% block content %}
{% url 'app:thing_list' as cancel_url %}
{% include "components/forms/crud_form.html" with title=page_title form=form cancel_url=cancel_url cols=3 %}
{% endblock %}
```

Custom layout:

```django
{% extends "layouts/portal.html" %}
{% block content %}
{% url 'app:thing_list' as cancel_url %}
<form method="post" class="form-stack">{% csrf_token %}
  {% include "components/ui/page_header.html" with title=page_title back=True back_url=cancel_url only %}
  {% include "components/forms/form_errors.html" with form=form only %}
  <div class="card"><div class="card-body form-grid form-grid--cols-3">
    {% include "components/forms/field.html" with field=form.number only %}
    {% include "components/forms/field.html" with field=form.date only %}
    {% include "components/forms/money.html" with field=form.amount only %}
  </div></div>
  {% include "components/forms/submit_bar.html" with cancel_url=cancel_url only %}
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

`python manage.py ui_lint` fails on: `<style>` outside components/layouts, raw controls, hex colours in templates or `components.css`, tables without board or component class, multi-line `{# #}`. Print documents (`*print*`, `*receipt*`) are exempt from all but the comment check.
