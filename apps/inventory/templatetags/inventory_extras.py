from django import template

register = template.Library()

@register.filter
def attr(obj, name):
    value = getattr(obj, name)
    return value() if callable(value) else value
