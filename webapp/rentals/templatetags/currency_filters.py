from django import template

from rentals.utils import format_amount

register = template.Library()


@register.filter(name="money")
def money(value):
    return format_amount(value)


@register.filter(name="abs")
def abs_filter(value):
    try:
        return abs(value)
    except TypeError:
        return value
