"""Forms for the two conversion documents.

The output grid is not a formset. Its rows are added and removed on the client,
carry no identity of their own, and are rewritten wholesale on save -- a formset
would buy management-form bookkeeping and give nothing back, so the lines are
parsed out of the posted lists here and handed to the service as dicts.
"""

from decimal import Decimal, InvalidOperation

from django import forms

from apps.core.constants import PRD_PACKABLE_SPECS
from apps.godowns.selectors import active_godowns
from apps.products.models import ProductNode

from . import selectors
from .models import GrindingVoucher, ProductConversion

ZERO = Decimal("0")


class GrindingVoucherForm(forms.ModelForm):
    class Meta:
        model = GrindingVoucher
        fields = [
            "date",
            "production_from",
            "production_to",
            "wheat_item",
            "disposal_wheat",
            "bag_item",
            "disposal_bag_qty",
            "godown",
            "issue_area",
            "description",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "production_from": forms.TimeInput(attrs={"type": "time"}),
            "production_to": forms.TimeInput(attrs={"type": "time"}),
            "issue_area": forms.TextInput(attrs={"placeholder": "Silo / hodi / godown"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wheat_item"].queryset = selectors.wheat_options()
        self.fields["bag_item"].queryset = selectors.bag_options()
        self.fields["godown"].queryset = active_godowns()
        self.fields["bag_item"].required = False
        self.fields["issue_area"].required = False
        self.fields["description"].required = False


class ProductConversionForm(forms.ModelForm):
    class Meta:
        model = ProductConversion
        fields = ["date", "source_product", "source_quantity", "godown", "description"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_product"].queryset = selectors.output_options()
        self.fields["godown"].queryset = active_godowns()
        self.fields["description"].required = False


def _decimal(raw) -> Decimal:
    try:
        return Decimal(str(raw).strip() or "0")
    except (InvalidOperation, AttributeError):
        return ZERO


def parse_output_lines(post) -> tuple[list[dict], list[str]]:
    """Turn the posted grid into the dicts the service takes.

    Unit weight is read off the master here rather than trusted from the form:
    the browser sends it so the operator can see the weight while typing, but a
    figure that decides stock is not something a posted field gets to set.
    """
    products = post.getlist("line_product")
    quantities = post.getlist("line_quantity")
    pack_products = post.getlist("line_pack_product")
    pack_quantities = post.getlist("line_pack_qty")

    ids = [int(value) for value in products + pack_products if value]
    catalogue = {node.pk: node for node in ProductNode.objects.filter(pk__in=ids)}

    lines, errors = [], []
    for index, raw_product in enumerate(products):
        if not raw_product:
            continue
        product = catalogue.get(int(raw_product))
        if product is None:
            errors.append(f"Line {index + 1}: product not found.")
            continue
        # Caught here as well as on the model, so a tampered post says which
        # line is wrong rather than failing the whole voucher anonymously.
        if product.specification not in PRD_PACKABLE_SPECS:
            errors.append(f"Line {index + 1}: {product.name} is not produced by the mill.")
            continue
        quantity = _decimal(quantities[index] if index < len(quantities) else 0)
        if quantity <= ZERO:
            errors.append(f"Line {index + 1}: enter a quantity.")
            continue

        raw_pack = pack_products[index] if index < len(pack_products) else ""
        pack_product = catalogue.get(int(raw_pack)) if raw_pack else None
        raw_pack_qty = pack_quantities[index] if index < len(pack_quantities) else ""
        # Blank means "same as the output", which is what packing normally is.
        # Loose output posts a zero, and consumes no sack.
        pack_qty = _decimal(raw_pack_qty) if str(raw_pack_qty).strip() != "" else quantity
        if pack_product is None:
            pack_qty = ZERO

        lines.append(
            {
                "product": product,
                "quantity": quantity,
                "unit_weight": product.effective_unit_weight,
                "pack_product": pack_product,
                "pack_qty": pack_qty,
            }
        )

    if not lines and not errors:
        errors.append("Add at least one output line.")
    return lines, errors
