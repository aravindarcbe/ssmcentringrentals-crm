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


@register.filter(name="sign_class")
def sign_class(value):
    """CSS class for a signed amount: green if > 0, red if < 0, neutral if 0."""
    try:
        if value > 0:
            return "money-positive"
        if value < 0:
            return "money-negative"
    except TypeError:
        pass
    return "money-neutral"
