from datetime import datetime
from datetime import timezone as dt_timezone

from django import template
from django.utils import timezone as dj_timezone

register = template.Library()


@register.filter(name='brl_price')
def brl_price(value):
    """
    Formata valor monetário no padrão brasileiro: 1.234,56
    Substitui o floatformat:2 nos templates de exibição de preço.
    """
    try:
        f = float(value)
        # Formata com 2 casas decimais e separador de milhar americano
        s = f'{f:,.2f}'            # "1,234.56"
        # Converte para formato brasileiro
        s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
        return s
    except (ValueError, TypeError):
        return value


@register.filter(name='datahora_br')
def datahora_br(value):
    """Formata timestamp ISO (UTC) como dd/mm/aaaa HH:MM:SS no horário de Brasília."""
    if not value:
        return value
    try:
        quando = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return value
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=dt_timezone.utc)
    return dj_timezone.localtime(quando).strftime('%d/%m/%Y %H:%M:%S')
