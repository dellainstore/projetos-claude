from django import template

register = template.Library()


@register.filter
def brl(value):
    """Formata número como moeda brasileira: R$ 1.234,56"""
    try:
        f = float(value)
        s = f"{f:,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    except (TypeError, ValueError):
        return "R$ 0,00"


@register.filter
def pct_css(value):
    """Percentual como string com ponto decimal — para uso em CSS width (nunca vírgula)."""
    try:
        f = min(max(float(value), 0.0), 100.0)
        return f"{f:.1f}"
    except (TypeError, ValueError):
        return "0"


@register.filter
def pct_de(value, total):
    """Retorna percentual (0–100) de value/total como string com ponto — para CSS width."""
    try:
        t = float(total)
        if t <= 0:
            return "0"
        return f"{min(float(value) / t * 100, 100):.1f}"
    except (TypeError, ValueError, ZeroDivisionError):
        return "0"
