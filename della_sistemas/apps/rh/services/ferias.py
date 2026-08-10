"""Cálculos de férias: dias proporcionais (CLT 1/12 por mês), saldo, abono e
limite para gozo. Gera o próximo período aquisitivo automaticamente quando o
período corrente completa."""

import calendar
import math
from datetime import date, timedelta

from apps.rh.models import PeriodoAquisitivo


def data_fim_gozo(data_inicio: date, dias: int) -> date:
    """Último dia de um período de férias que começa em `data_inicio` e dura
    `dias` dias corridos."""
    return data_inicio + timedelta(days=dias - 1)


def data_retorno_gozo(colaborador, data_fim: date) -> date:
    """Primeiro dia de volta ao trabalho após o fim das férias: sempre o dia
    útil seguinte. Domingo e feriado são sempre pulados; sábado só conta como
    dia útil se a escala do colaborador determinar que ele trabalha naquele
    sábado (variante B) — sem escala vinculada, sábado é sempre pulado."""
    from apps.rh.services.calendario import feriados
    from apps.rh.services.escala import horas_esperadas_no_dia

    d = data_fim + timedelta(days=1)
    while True:
        if d.weekday() == 6 or d in feriados(d.year):
            d += timedelta(days=1)
            continue
        if d.weekday() == 5 and not horas_esperadas_no_dia(colaborador, d):
            d += timedelta(days=1)
            continue
        return d


def _add_meses(d: date, meses: int) -> date:
    """Soma `meses` a uma data, ajustando o dia ao último dia do mês quando necessário."""
    total = d.month - 1 + meses
    ano = d.year + total // 12
    mes = total % 12 + 1
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(d.day, ultimo_dia))


def meses_trabalhados(inicio: date, fim: date, hoje: date | None = None) -> int:
    """Meses completos do período aquisitivo já decorridos (CLT: fração ≥ 15 dias
    conta como mês inteiro). Limitado a 12."""
    hoje = hoje or date.today()
    ate = min(hoje, fim)
    if ate < inicio:
        return 0
    meses = (ate.year - inicio.year) * 12 + (ate.month - inicio.month)
    if ate.day < inicio.day:
        meses -= 1
    meses = max(meses, 0)
    # Fração restante após os meses completos: ≥ 15 dias vira mais um mês (CLT).
    resto_inicio = _add_meses(inicio, meses)
    if (ate - resto_inicio).days >= 15:
        meses += 1
    return min(meses, 12)


def resumo_periodo(periodo: PeriodoAquisitivo, hoje: date | None = None) -> dict:
    """Resumo de um período aquisitivo.

    - meses: meses aquisitivos já trabalhados (0–12)
    - completo: período concluído → direito a 30 dias cheios (libera férias/abono)
    - dias_proporcionais: dias de direito acumulados até hoje (proporcional)
    - dias_gozados: soma das férias já lançadas
    - abono: dias vendidos à empresa (abate do saldo)
    - saldo: direito − gozados − abono
    - limite_gozo: fim do período concessivo = fim do aquisitivo + 11 meses (CLT)
    """
    from apps.rh.services.afastamentos import dias_ferias_gozados

    hoje = hoje or date.today()
    gozos = list(periodo.gozos.all())
    afastamentos = list(periodo.afastamentos.filter(tipo="ferias").order_by("data_inicio"))
    dias_gozados = dias_ferias_gozados(periodo)

    meses = meses_trabalhados(periodo.inicio, periodo.fim, hoje)
    completo = hoje >= periodo.fim
    if completo:
        direito_atual = periodo.dias_direito
    else:
        direito_atual = math.ceil(meses * periodo.dias_direito / 12)

    abono = periodo.abono_dias or 0
    saldo = direito_atual - dias_gozados - abono
    limite_gozo = _add_meses(periodo.fim, 11)
    return {
        "periodo": periodo,
        "gozos": gozos,
        "afastamentos": afastamentos,
        "meses": meses,
        "completo": completo,
        "dias_proporcionais": direito_atual,
        "dias_gozados": dias_gozados,
        "abono": abono,
        "saldo": saldo,
        "limite_gozo": limite_gozo,
        "vencido": completo and hoje > limite_gozo and saldo > 0,
    }


def garantir_proximo_periodo(colaborador, hoje: date | None = None) -> PeriodoAquisitivo | None:
    """Cria automaticamente o próximo período aquisitivo quando o último já completou
    e ainda não há um período começando depois dele. Regra fixa: 12 meses a partir do
    dia seguinte ao fim do período anterior. Retorna o período criado (ou None)."""
    hoje = hoje or date.today()
    periodos = list(colaborador.periodos_ferias.order_by("inicio"))
    if not periodos:
        return None
    ultimo = periodos[-1]
    if hoje < ultimo.fim:
        return None  # ainda em andamento
    inicio = ultimo.fim + timedelta(days=1)
    fim = _add_meses(inicio, 12) - timedelta(days=1)
    return PeriodoAquisitivo.objects.create(
        colaborador=colaborador, inicio=inicio, fim=fim,
        dias_direito=ultimo.dias_direito,
    )
