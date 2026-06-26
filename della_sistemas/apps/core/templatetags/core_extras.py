from django import template

register = template.Library()


@register.filter
def get_perm(d, key):
    """Acessa um valor de dict por chave dinâmica em templates."""
    if isinstance(d, dict):
        return d.get(key, {})
    return {}


@register.filter
def brl(value):
    """Formata número como moeda brasileira: R$ 1.894,00"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    inteiro = int(v)
    centavos = round((v - inteiro) * 100)
    inteiro_fmt = f"{inteiro:,}".replace(",", ".")
    return f"R$ {inteiro_fmt},{centavos:02d}"
