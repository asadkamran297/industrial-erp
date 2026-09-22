import re
from decimal import Decimal, InvalidOperation

from django import forms, template
from django.template import Node, TemplateSyntaxError
from django.template.base import token_kwargs
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.access_control.selectors import user_has_permission
from apps.core.formatting import format_amount, format_date, format_qty
from apps.core.icons import ICONS

register = template.Library()


@register.filter(name="qty")
def qty(value):
    """Render a quantity with the app-wide fixed decimal precision."""
    return format_qty(value)


@register.filter(name="amount")
def amount(value):
    """Render an amount with thousands separators and fixed decimal precision."""
    return format_amount(value)


@register.filter(name="short_amount")
def short_amount(value):
    """An amount sized for a glance rather than for a ledger.

    A headline figure is read for its order of magnitude -- 28.5 M says what
    28,547,037.00 makes the reader count digits to work out. Anything under a
    lakh is left alone, because shortening it would lose more than it saves.
    """
    try:
        number = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return format_amount(value)

    sign = "-" if number < 0 else ""
    number = abs(number)
    for size, suffix in ((Decimal("10000000"), " Cr"), (Decimal("100000"), " Lac")):
        if number >= size:
            scaled = (number / size).quantize(Decimal("0.01"))
            text = f"{scaled:f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    return f"{sign}{format_amount(number)}"


@register.filter(name="get_item")
def get_item(value, key):
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


@register.filter(name="mund")
def mund(value):
    """Kilograms to mund (40 kg)."""
    from apps.core.reporting import mund as to_mund

    try:
        return to_mund(value)
    except Exception:
        return value


@register.filter(name="dmy")
def dmy(value):
    """Render a date the way the business writes it: DD-MM-YYYY."""
    return format_date(value)


@register.simple_tag(takes_context=True)
def has_perm(context, code):
    """True when the current user holds ``code`` (or the ``*`` wildcard).

    Usage: ``{% has_perm "inventory.items.add" as can_add %}``.
    """
    request = context.get("request")
    if request is None:
        return False
    return user_has_permission(request.user, code)


# ---------------------------------------------------------------------------
# Design system helpers (docs/UI_SYSTEM.md)
# ---------------------------------------------------------------------------

WEIGHT_NAME = re.compile(r"(weight|_kg|kgs|maund|mound|tare|gross|net_wt)", re.I)
MONEY_NAME = re.compile(
    r"(amount|price|rate|salary|wage|debit|credit|total|balance|cost|value|fee|charge|discount|tax|paid|payable|receivable)",
    re.I,
)


@register.simple_tag
def icon(name, size="", extra=""):
    """Inline SVG from the single icon set: ``{% icon "edit" %}``."""
    paths = ICONS.get(name)
    if paths is None:
        return ""
    classes = "icon"
    if size:
        classes += f" icon--{size}"
    if extra:
        classes += f" {extra}"
    return format_html(
        '<svg class="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>',
        classes,
        mark_safe(paths),
    )


def _field_kind(bound):
    widget = bound.field.widget
    if isinstance(widget, forms.HiddenInput):
        return "hidden"
    if isinstance(widget, forms.CheckboxInput):
        return "checkbox"
    if isinstance(widget, forms.RadioSelect):
        return "radio"
    if isinstance(widget, forms.CheckboxSelectMultiple):
        return "multi"
    if isinstance(widget, forms.ClearableFileInput) or isinstance(widget, forms.FileInput):
        return "file"
    if isinstance(widget, forms.Textarea):
        return "textarea"
    if isinstance(widget, forms.Select):
        return "select"
    input_type = getattr(widget, "input_type", "") or widget.attrs.get("type", "")
    if input_type == "date" or isinstance(bound.field, forms.DateField):
        return "date"
    if isinstance(bound.field, forms.DecimalField):
        places = getattr(bound.field, "decimal_places", None)
        if places == 3 or WEIGHT_NAME.search(bound.name):
            return "weight"
        if places == 2 or MONEY_NAME.search(bound.name):
            return "money"
        return "number"
    if isinstance(bound.field, (forms.IntegerField, forms.FloatField)) or input_type == "number":
        return "number"
    return "text"


@register.filter(name="field_kind")
def field_kind(bound):
    """What a bound field renders as: text, number, money, weight, date, select, ..."""
    return _field_kind(bound)


CONTROL_CLASSES = {
    "checkbox": "check",
    "radio": "",
    "multi": "",
    "hidden": "",
    "date": "control control--date",
    "number": "control control--num",
    "money": "control control--money",
    "weight": "control control--weight",
}


@register.filter(name="control")
def control(bound, kind=""):
    """Render a bound field's widget with the design-system control classes.

    Widget classes are set here, once, rather than per form or per template.
    """
    kind = kind or _field_kind(bound)
    widget = bound.field.widget
    current = [c for c in widget.attrs.get("class", "").split() if c not in ("form-input", "form-select")]
    extra = CONTROL_CLASSES.get(kind, "control")
    attrs = {}
    classes = " ".join(dict.fromkeys((extra.split() if extra else []) + current))
    if classes:
        attrs["class"] = classes
    if kind == "weight":
        attrs["data-no-amount"] = ""
        attrs.setdefault("step", widget.attrs.get("step", "0.001"))
        attrs["inputmode"] = "decimal"
    elif kind == "money":
        attrs["data-amount"] = ""
        attrs["inputmode"] = "decimal"
    if widget.attrs.get("placeholder"):
        attrs["placeholder"] = False
    if bound.errors:
        attrs["aria-invalid"] = "true"
    return bound.as_widget(attrs=attrs)


class SlotNode(Node):
    def __init__(self, name, nodelist):
        self.name = name
        self.nodelist = nodelist

    def render(self, context):
        return ""


class ComponentNode(Node):
    def __init__(self, name, kwargs, nodelist, isolated=False):
        self.name = name
        self.kwargs = kwargs
        self.nodelist = nodelist
        self.isolated = isolated
        self.slots = [node for node in nodelist if isinstance(node, SlotNode)]

    def render(self, context):
        name = self.name.resolve(context)
        values = {key: value.resolve(context) for key, value in self.kwargs.items()}
        slots = {node.name: mark_safe(node.nodelist.render(context)) for node in self.slots}
        body = mark_safe(self.nodelist.render(context))
        template = context.template.engine.get_template(f"components/{name}.html")
        if self.isolated:
            return template.render(context.new({**values, "slot": body, "slots": slots}))
        with context.push(**values, slot=body, slots=slots):
            return template.render(context)


@register.tag(name="component")
def do_component(parser, token):
    """Wrap markup in a component: ``{% component "forms/section" title="Lines" %}...{% endcomponent %}``.

    The body arrives as ``slot``; ``{% slot name %}...{% endslot %}`` blocks arrive as ``slots.name``.
    A trailing ``only`` renders the component with its arguments alone, like ``include ... only``.
    """
    bits = token.split_contents()
    if len(bits) < 2:
        raise TemplateSyntaxError("component needs a template name")
    isolated = bits[-1] == "only"
    if isolated:
        bits = bits[:-1]
    name = parser.compile_filter(bits[1])
    kwargs = token_kwargs(bits[2:], parser)
    if len(kwargs) != len(bits[2:]):
        raise TemplateSyntaxError("component arguments must be key=value")
    nodelist = parser.parse(("endcomponent",))
    parser.delete_first_token()
    return ComponentNode(name, kwargs, nodelist, isolated)


@register.tag(name="slot")
def do_slot(parser, token):
    bits = token.split_contents()
    if len(bits) != 2:
        raise TemplateSyntaxError("slot needs one name")
    name = bits[1].strip("\"'")
    nodelist = parser.parse(("endslot",))
    parser.delete_first_token()
    return SlotNode(name, nodelist)


class CaptureNode(Node):
    def __init__(self, name, nodelist):
        self.name = name
        self.nodelist = nodelist

    def render(self, context):
        context[self.name] = mark_safe(self.nodelist.render(context).strip())
        return ""


@register.tag(name="capture")
def do_capture(parser, token):
    """Render a block into a variable: ``{% capture as attrs %}data-pk="{{ pk }}"{% endcapture %}``."""
    bits = token.split_contents()
    if len(bits) != 3 or bits[1] != "as":
        raise TemplateSyntaxError("usage: {% capture as name %}...{% endcapture %}")
    nodelist = parser.parse(("endcapture",))
    parser.delete_first_token()
    return CaptureNode(bits[2], nodelist)
