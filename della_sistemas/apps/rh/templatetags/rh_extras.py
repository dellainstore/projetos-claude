from django import template

from apps.rh.services.ponto import formatar_horas_hm

register = template.Library()


@register.filter
def horas_hm(valor):
    """Filtro de template: horas decimais → 'H:MM' (ex.: 8.5 → '08:30')."""
    return formatar_horas_hm(valor)


@register.filter
def num_br(valor):
    """Número no padrão BR (milhar com ponto, decimal com vírgula), sem prefixo —
    para <input type="text"> de valores editáveis (o servidor já aceita os dois
    formatos via services.utils.parse_decimal). Ex.: 1234.5 → '1.234,50'."""
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return "0,00"
    s = f"{f:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")
