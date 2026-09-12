from django import template

register = template.Library()


@register.filter(name="initials")
def initials(value):
    words = (value or "").split()
    letters = "".join(w[0].upper() for w in words if w)[:3]
    return letters or "?"
