from django import template

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
