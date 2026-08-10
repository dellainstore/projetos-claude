from django import template

register = template.Library()


@register.filter
def br_int(value):
    """Formata número inteiro com separador de milhar brasileiro: 7.372"""
    try:
        return f"{int(round(float(value))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


@register.filter
def br_float(value, digits=1):
    """Formata número decimal no padrão brasileiro: 1.234,5"""
    try:
        f = float(value)
        d = int(digits)
        s = f"{f:,.{d}f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "0"
