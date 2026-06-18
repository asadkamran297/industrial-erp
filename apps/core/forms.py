from django import forms


class AutoSelectSingleChoiceMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound:
            return

        for name, field in self.fields.items():
            if self.initial.get(name) or self.initial.get(name) == 0:
                continue
            if isinstance(field, forms.ModelChoiceField):
                choices = list(field.queryset[:2])
                if len(choices) == 1:
                    self.initial[name] = choices[0].pk
            elif isinstance(field, forms.ChoiceField):
                choices = [(value, label) for value, label in field.choices if value not in ("", None)]
                if len(choices) == 1:
                    self.initial[name] = choices[0][0]
