"""Estratégia de recorrência sem depender de cron (ver plano, seção 12):

1. Regra COM fim definido (data_final ou quantidade_ocorrencias): gera todas
   as ocorrências de uma vez na criação.
2. Regra SEM fim definido: mantém uma janela futura (`janela_meses`,
   default 12) — gera tudo dentro da janela na criação.
3. `estender_janela_recorrencias()` — idempotente, para cada regra ativa sem
   fim, gera só as ocorrências que faltam até completar a janela de novo.
   Pensado para rodar via cron 1x/dia (mecanismo primário).
4. `verificar_lazy()` — chamada nos pontos de entrada do módulo (Lançamentos,
   Dashboard); só dispara a extensão quando a janela está prestes a
   terminar E faz tempo que não verifica (throttle) — rede de segurança
   caso o cron falhe, não o mecanismo primário.
5. `OcorrenciaRecorrencia` com `UniqueConstraint(regra, data_ocorrencia)` é a
   garantia final contra duplicidade, mesmo se comando e checagem lazy
   rodarem "ao mesmo tempo".
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.financeiro.models import OcorrenciaRecorrencia, RegraRecorrencia
from .datas import normalizar_data, somar_periodo
from .lancamentos import criar_lancamento

VERIFICACAO_LAZY_INTERVALO = timedelta(hours=6)
FOLGA_JANELA_MESES = 1  # só reestende quando falta menos de 1 mês pra acabar a janela


def _proxima_data(regra: RegraRecorrencia):
    ultima = regra.ocorrencias.order_by("-data_ocorrencia").values_list("data_ocorrencia", flat=True).first()
    if ultima is None:
        return regra.data_inicial
    return somar_periodo(ultima, regra.frequencia)


def _pode_gerar_mais(regra: RegraRecorrencia, proxima_data, quantidade_ja_gerada: int) -> bool:
    if regra.data_final and proxima_data > regra.data_final:
        return False
    if regra.quantidade_ocorrencias and quantidade_ja_gerada >= regra.quantidade_ocorrencias:
        return False
    return True


@transaction.atomic
def _gerar_ocorrencia(regra: RegraRecorrencia, data_ocorrencia, usuario=None):
    """Cria 1 ocorrência (lançamento de parcela única + vínculo). Idempotente
    via UniqueConstraint — se já existir para essa data, não duplica."""
    if OcorrenciaRecorrencia.objects.filter(regra=regra, data_ocorrencia=data_ocorrencia).exists():
        return None
    lancamento = criar_lancamento(
        operacao=regra.operacao, tipo=regra.tipo_lancamento, descricao=regra.descricao,
        valor_original=regra.valor, data_competencia=data_ocorrencia,
        primeiro_vencimento=data_ocorrencia, categoria=regra.categoria,
        contato=regra.contato, centro_custo=regra.centro_custo,
        conta_prevista=regra.conta_prevista, forma_pagamento=regra.forma_pagamento,
        observacoes=f"Gerado pela recorrência: {regra.descricao}",
        parcelas_qtd=1, usuario=usuario or regra.criado_por,
    )
    try:
        return OcorrenciaRecorrencia.objects.create(
            regra=regra, data_ocorrencia=data_ocorrencia, lancamento=lancamento,
        )
    except IntegrityError:
        # corrida rara (checagem lazy + comando ao mesmo tempo): o
        # lançamento duplicado fica órfão, cancela pra não sujar a tela
        lancamento.estado_estrutural = "cancelado"
        lancamento.save(update_fields=["estado_estrutural"])
        return None


def gerar_ocorrencias_ate(regra: RegraRecorrencia, ate_data, usuario=None) -> int:
    """Gera todas as ocorrências que faltam entre a última já gerada (ou
    `data_inicial`) e `ate_data`, respeitando fim/quantidade da regra."""
    if regra.pausada or not regra.ativa:
        return 0
    quantidade_ja_gerada = regra.ocorrencias.count()
    proxima = _proxima_data(regra)
    geradas = 0
    # Inclusive: quando `regra` TEM fim definido, `ate_data` é o próprio
    # `data_final` e a ocorrência exatamente nessa data deve entrar. Para
    # regra SEM fim, quem chama já passa `ate_data` como hoje+janela-1dia
    # (ver `_alvo_janela_sem_fim`), então a borda nunca sobra 1 ocorrência
    # a mais.
    while proxima <= ate_data and _pode_gerar_mais(regra, proxima, quantidade_ja_gerada):
        if _gerar_ocorrencia(regra, proxima, usuario=usuario):
            geradas += 1
            quantidade_ja_gerada += 1
        proxima = somar_periodo(proxima, regra.frequencia)
    regra.janela_gerada_ate = max(regra.janela_gerada_ate or proxima, min(proxima, ate_data))
    regra.ultima_verificacao_em = timezone.now()
    regra.save(update_fields=["janela_gerada_ate", "ultima_verificacao_em"])
    return geradas


@transaction.atomic
def criar_regra_recorrencia(*, operacao, usuario=None, **campos) -> RegraRecorrencia:
    if campos.get("data_inicial"):
        campos["data_inicial"] = normalizar_data(campos["data_inicial"])
    if campos.get("data_final"):
        campos["data_final"] = normalizar_data(campos["data_final"])
    regra = RegraRecorrencia.objects.create(operacao=operacao, criado_por=usuario, **campos)
    if regra.tem_fim_definido:
        alvo = regra.data_final or timezone.localdate().replace(year=timezone.localdate().year + 5)
    else:
        alvo = _alvo_janela_sem_fim(timezone.localdate(), regra.janela_meses)
    gerar_ocorrencias_ate(regra, alvo, usuario=usuario)
    return regra


def somar_periodo_meses(data_base, meses: int):
    from .datas import somar_meses
    return somar_meses(data_base, meses)


def _alvo_janela_sem_fim(data_base, janela_meses: int):
    """Janela de N meses = ocorrências dentro de [data_base, data_base+N
    meses) — 1 dia a menos que `somar_periodo_meses` pra não gerar 1
    ocorrência a mais bem na borda exata do N-ésimo mês."""
    return somar_periodo_meses(data_base, janela_meses) - timedelta(days=1)


def estender_janela_recorrencias(usuario=None) -> dict:
    """Comando idempotente (`manage.py estender_recorrencias`) — mecanismo
    primário, pensado pra rodar 1x/dia via cron."""
    resultado = {}
    hoje = timezone.localdate()
    regras = RegraRecorrencia.objects.filter(ativa=True, pausada=False, data_final__isnull=True)
    for regra in regras:
        alvo = _alvo_janela_sem_fim(hoje, regra.janela_meses)
        geradas = gerar_ocorrencias_ate(regra, alvo, usuario=usuario)
        if geradas:
            resultado[regra.id] = geradas
    return resultado


def verificar_lazy() -> None:
    """Chamada nos pontos de entrada do módulo (views de Lançamentos e
    Dashboard) — throttle duplo: só estende quando a janela está prestes a
    terminar E faz um tempo que não verifica essa regra especificamente.
    Nunca deve custar caro numa request comum (poucas regras, query simples)."""
    hoje = timezone.localdate()
    limite_alerta = somar_periodo_meses(hoje, FOLGA_JANELA_MESES)
    agora = timezone.now()
    candidatas = RegraRecorrencia.objects.filter(
        ativa=True, pausada=False, data_final__isnull=True,
    ).filter(
        janela_gerada_ate__lt=limite_alerta,
    )
    for regra in candidatas:
        if regra.ultima_verificacao_em and (agora - regra.ultima_verificacao_em) < VERIFICACAO_LAZY_INTERVALO:
            continue
        alvo = _alvo_janela_sem_fim(hoje, regra.janela_meses)
        gerar_ocorrencias_ate(regra, alvo)
