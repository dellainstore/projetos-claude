"""Estorno automático quando uma corrida Lalamove termina em "Problema na
Coleta" (status bruto EXPIRED ou REJECTED) — nesses dois casos ninguém saiu
com o pacote, e a Lalamove devolve o valor cheio sozinha, sem que a gente
peça. Confirmado ao vivo em 2026-09-10 comparando o saldo real da carteira
(via webhook WALLET_BALANCE_CHANGED, logado em motoqueiro.log) com o saldo
do nosso ledger: a corrida #17 expirou, debitou R$ 16,54 na criação e nunca
foi creditada de volta — mas o saldo real da Lalamove pulou +R$ 16,54 no
exato segundo em que o webhook EXPIRED chegou.

Ao contrário do cancelamento manual (`_consultar_taxa_cancelamento` em
views/relatorio.py, usado quando é a PESSOA que cancela depois que o motoboy
já aceitou — aí pode ter taxa retida), aqui NÃO existe um campo tipo
`cancellationFee` no GET /v3/orders/{id} pra confirmar o estorno — o
`priceBreakdown.total` continua mostrando o valor cheio mesmo depois da
Lalamove já ter devolvido o dinheiro. Por isso este estorno assume sempre
100% (comportamento real observado), sem tentar confirmar um valor parcial
contra a API.
"""
from decimal import Decimal

from ..models import MovimentoSaldoLalamove, SolicitacaoEntrega


def creditar_estorno_problema_coleta(solicitacao: SolicitacaoEntrega, status_raw: str) -> None:
    """Credita de volta o valor debitado da corrida e zera `valor` — mesmo
    critério do próprio painel da Lalamove, que mostra R$ 0,00 pra essas
    corridas. Idempotente na prática porque quem chama só invoca isto na
    PRIMEIRA vez que o status novo é "problema_coleta" (ver checagem contra
    `status_anterior` em webhook.py e em `_ressincronizar_status`)."""
    if solicitacao.plataforma != SolicitacaoEntrega.PLATAFORMA_LALAMOVE:
        return
    if solicitacao.valor <= 0:
        return

    valor_debitado = solicitacao.valor
    MovimentoSaldoLalamove.objects.create(
        tipo=MovimentoSaldoLalamove.TIPO_CREDITO,
        origem=MovimentoSaldoLalamove.ORIGEM_CORRIDA,
        valor=valor_debitado,
        descricao=(
            f"Estorno automático — corrida #{solicitacao.id} terminou em "
            f"\"Problema na Coleta\" ({status_raw or '?'}); a Lalamove não cobra "
            "quando ninguém aceita/recusa a coleta."
        ),
        solicitacao=solicitacao,
    )
    solicitacao.valor = Decimal("0.00")
