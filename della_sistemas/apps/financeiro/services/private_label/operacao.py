"""Resolve a operação financeira ativa.

Enquanto existir só 1 operação ativa (hoje: "Private Label"), esta é a
ÚNICA função que decide isso — nenhuma view/form pergunta a operação ao
usuário. No dia em que existir uma 2ª operação ativa, esta função passa a
levantar erro pedindo escolha explícita, e o código que a chama precisa
ser adaptado — mas isso fica isolado aqui, sem tocar em telas (ver plano,
seção 1.1).
"""
from apps.financeiro.models import OperacaoFinanceira


def obter_operacao_padrao() -> OperacaoFinanceira:
    ativas = list(OperacaoFinanceira.objects.filter(status="ativa"))
    if not ativas:
        raise RuntimeError("Nenhuma OperacaoFinanceira ativa cadastrada.")
    if len(ativas) > 1:
        raise RuntimeError(
            "Mais de uma OperacaoFinanceira ativa — o módulo Private Label "
            "ainda não implementa seleção explícita de operação nas telas. "
            "Reative só uma, ou implemente o seletor antes de prosseguir."
        )
    return ativas[0]
