"""CDI diário (série 12 do SGS/Bacen) e rendimento automático das contas de
investimento indexadas a ele (`ContaInvestimento.percentual_cdi`).

Fluxo (cron `calcular_rendimento_investimentos`, diário):
1. `atualizar_taxas_cdi()` busca no Bacen os dias úteis que ainda não estão
   em `TaxaCDIDiaria` e grava.
2. `lancar_rendimentos_pendentes()` percorre as `ContaInvestimento` com
   `rendimento_automatico=True` e, pra cada dia útil com CDI publicado
   posterior ao último rendimento já lançado (ou à aplicação mais antiga,
   se nunca rendeu), calcula e chama `registrar_rendimento()`.

O Bacen só publica CDI pra dia útil — fim de semana/feriado simplesmente não
aparece na série, então o cron não lança nada nesses dias (igual o extrato
do banco, que só atualiza o saldo em dia útil mesmo em produtos de
liquidez diária).
"""
import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import requests
from django.db import transaction

from apps.financeiro.models import ContaInvestimento, TaxaCDIDiaria
from .investimentos import registrar_rendimento

logger = logging.getLogger(__name__)

SGS_CDI_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
TIMEOUT_SEGUNDOS = 15


def _parse_data_bacen(texto: str) -> date:
    dia, mes, ano = texto.split("/")
    return date(int(ano), int(mes), int(dia))


def buscar_cdi_bacen(data_inicio: date, data_fim: date) -> list[dict]:
    """Consulta a série 12 (CDI) do SGS/Bacen no intervalo informado.
    Retorna lista de {'data': date, 'taxa_pct_dia': Decimal}. API pública,
    sem autenticação. Levanta a exceção original em caso de erro de rede —
    o chamador decide se loga e segue (cron não deve travar por isso)."""
    params = {
        "formato": "json",
        "dataInicial": data_inicio.strftime("%d/%m/%Y"),
        "dataFinal": data_fim.strftime("%d/%m/%Y"),
    }
    resp = requests.get(SGS_CDI_URL, params=params, timeout=TIMEOUT_SEGUNDOS)
    resp.raise_for_status()
    bruto = resp.json()
    return [
        {"data": _parse_data_bacen(item["data"]), "taxa_pct_dia": Decimal(item["valor"])}
        for item in bruto
    ]


def atualizar_taxas_cdi(dias_retroativos: int = 15) -> int:
    """Busca no Bacen os últimos `dias_retroativos` dias corridos e grava em
    `TaxaCDIDiaria` os que ainda não existem localmente (idempotente —
    `update_or_create` pelo campo `data`, único). Retorna quantas taxas
    novas/atualizadas. A janela retroativa (não só 'ontem') existe pra
    cobrir o cron ter falhado ou o Bacen ter atrasado a publicação de um
    dia — sem isso um dia perdido nunca mais seria recuperado."""
    hoje = date.today()
    data_inicio = hoje - timedelta(days=dias_retroativos)
    try:
        taxas = buscar_cdi_bacen(data_inicio, hoje)
    except requests.RequestException as exc:
        logger.warning("CDI: falha ao consultar Bacen (%s) — mantendo cache local.", exc)
        return 0

    gravadas = 0
    for item in taxas:
        _, criado = TaxaCDIDiaria.objects.update_or_create(
            data=item["data"], defaults={"taxa_pct_dia": item["taxa_pct_dia"]},
        )
        gravadas += 1
    logger.info("CDI: %s taxa(s) sincronizada(s) do Bacen (%s a %s).", gravadas, data_inicio, hoje)
    return gravadas


def _calcular_rendimento_dia(saldo: Decimal, taxa_pct_dia: Decimal, percentual_cdi: Decimal) -> Decimal:
    fator = (taxa_pct_dia / Decimal("100")) * (percentual_cdi / Decimal("100"))
    return (saldo * fator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def lancar_rendimentos_pendentes(conta: ContaInvestimento, *, ate: date | None = None) -> int:
    """Lança, em ordem cronológica, o rendimento de cada dia útil pendente
    de UMA conta (dias com CDI publicado, depois do último rendimento já
    lançado — ou da aplicação mais antiga, se nunca rendeu nada). Retorna
    quantos lançamentos foram feitos. Precisa ser em ordem e um de cada vez
    porque `registrar_rendimento` usa o saldo ATUAL da conta (o rendimento
    de um dia precisa já estar refletido no saldo antes de calcular o
    próximo dia, senão perde o efeito de juros compostos)."""
    if not conta.rendimento_automatico or conta.percentual_cdi is None or conta.categoria_rendimento_id is None:
        return 0

    ate = ate or date.today() - timedelta(days=1)
    desde = conta.ultimo_rendimento_lancado()
    if desde is None:
        primeira_aplicacao = (
            conta.transacoes.filter(tipo="aplicacao", estornada=False)
            .order_by("data").values_list("data", flat=True).first()
        )
        if primeira_aplicacao is None:
            return 0
        desde = primeira_aplicacao

    dias_pendentes = list(
        TaxaCDIDiaria.objects.filter(data__gt=desde, data__lte=ate).order_by("data")
    )
    lancados = 0
    for taxa in dias_pendentes:
        saldo = conta.saldo_atual()
        if saldo <= 0:
            continue
        valor = _calcular_rendimento_dia(saldo, taxa.taxa_pct_dia, conta.percentual_cdi)
        if valor <= 0:
            continue
        registrar_rendimento(
            operacao=conta.operacao, conta_investimento=conta, categoria=conta.categoria_rendimento,
            valor=valor, data=taxa.data,
            observacao=f"Rendimento automático: {conta.percentual_cdi}% do CDI ({taxa.taxa_pct_dia}% a.d.)",
            usuario=None,
        )
        lancados += 1
    return lancados


def lancar_rendimentos_automaticos_todas_contas() -> dict:
    """Roda `lancar_rendimentos_pendentes` pra toda `ContaInvestimento` ativa
    com rendimento automático ligado. Retorna {conta_id: qtd_lancada} pra
    log/depuração do cron."""
    resultado = {}
    contas = ContaInvestimento.objects.filter(ativa=True, rendimento_automatico=True)
    for conta in contas:
        try:
            qtd = lancar_rendimentos_pendentes(conta)
        except Exception:
            logger.exception("CDI: falha ao lançar rendimento automático da conta %s (%s).", conta.id, conta.nome)
            continue
        if qtd:
            resultado[conta.id] = qtd
            logger.info("CDI: %s dia(s) de rendimento lançado(s) para '%s'.", qtd, conta.nome)
    return resultado
