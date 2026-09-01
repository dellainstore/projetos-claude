from django import template

from apps.financeiro.models import rotulo_situacao

register = template.Library()


@register.simple_tag
def rotulo_situacao_tag(tipo, situacao):
    """{% rotulo_situacao_tag lancamento.tipo sit %} — "Pago"/"Recebido" em
    vez de "quitado" genérico, "A pagar"/"A receber" em vez de "pendente"/
    "previsto". Ver `models.rotulo_situacao`."""
    return rotulo_situacao(tipo, situacao)
