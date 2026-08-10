"""Resolução da escala de trabalho por colaboradora.

Determina, dia a dia, se a colaboradora trabalha e quantas horas são esperadas,
resolvendo a alternância de sábado (variante A = sem sábado / B = com sábado) por
paridade de semanas a partir de uma âncora, com exceções manuais para trocas.

Usado por:
- Benefícios (VT): contagem de dias trabalhados no mês.
- Ponto: horas esperadas por dia no banco de horas.
"""

import calendar
from datetime import date, time, timedelta
from decimal import Decimal

from apps.rh.models import EscalaDia, EscalaExcecao


def _segunda_da_semana(d: date) -> date:
    """Segunda-feira da semana de `d`."""
    return d - timedelta(days=d.weekday())


def variante_da_semana(colaborador, segunda: date) -> str:
    """'A' ou 'B' para a semana cuja segunda-feira é `segunda`.

    Ordem de precedência: exceção manual > paridade da âncora > 'A'.
    Escala sem alternância sempre retorna 'A'.
    """
    escala = colaborador.escala
    if escala is None or not escala.alterna_sabado:
        return "A"

    exc = EscalaExcecao.objects.filter(
        colaborador=colaborador, semana_segunda=segunda
    ).first()
    if exc:
        return exc.variante

    ancora = colaborador.escala_ancora_b
    if not ancora:
        return "A"
    ancora_seg = _segunda_da_semana(ancora)
    semanas = (segunda - ancora_seg).days // 7
    # A semana da âncora é uma semana COM sábado (B); alterna a cada semana.
    return "B" if semanas % 2 == 0 else "A"


def _dias_por_variante(escala) -> dict[tuple[str, int], EscalaDia]:
    return {
        (d.variante, d.dia_semana): d
        for d in escala.dias.all()
    }


def dias_trabalho_no_mes(colaborador, ano: int, mes: int) -> list[tuple[date, Decimal]]:
    """Lista de (data, horas_esperadas) dos dias trabalhados no mês conforme a escala.

    Sem escala vinculada → lista vazia (o chamador decide o fallback).
    """
    escala = colaborador.escala
    if escala is None:
        return []

    mapa = _dias_por_variante(escala)
    _, ultimo = calendar.monthrange(ano, mes)
    resultado: list[tuple[date, Decimal]] = []
    for dia in range(1, ultimo + 1):
        d = date(ano, mes, dia)
        variante = variante_da_semana(colaborador, _segunda_da_semana(d))
        ed = mapa.get((variante, d.weekday()))
        if ed and ed.trabalha:
            resultado.append((d, ed.horas()))
    return resultado


def dias_uteis_escala(colaborador, ano: int, mes: int) -> int | None:
    """Quantidade de dias trabalhados no mês pela escala (base do VT).

    Retorna None quando não há escala vinculada (chamador usa o fallback genérico).
    """
    if colaborador.escala is None:
        return None
    return len(dias_trabalho_no_mes(colaborador, ano, mes))


def horas_esperadas_no_dia(colaborador, d: date) -> Decimal | None:
    """Horas esperadas em uma data específica pela escala (None se sem escala)."""
    escala = colaborador.escala
    if escala is None:
        return None
    variante = variante_da_semana(colaborador, _segunda_da_semana(d))
    ed = EscalaDia.objects.filter(
        escala=escala, variante=variante, dia_semana=d.weekday()
    ).first()
    if ed and ed.trabalha:
        return ed.horas()
    return Decimal("0")


def batidas_esperadas_no_dia(colaborador, d: date) -> int | None:
    """Nº de batidas esperadas no dia pela escala: 2 (dia configurado sem horário
    de almoço, ex.: sábado só entrada/saída) ou 4 (com almoço). None se não há
    escala vinculada ou o dia não é de trabalho pela escala (chamador usa o
    padrão de 4 batidas)."""
    escala = colaborador.escala
    if escala is None:
        return None
    variante = variante_da_semana(colaborador, _segunda_da_semana(d))
    ed = EscalaDia.objects.filter(
        escala=escala, variante=variante, dia_semana=d.weekday()
    ).first()
    if not ed or not ed.trabalha:
        return None
    return 4 if (ed.hora_saida_almoco and ed.hora_volta_almoco) else 2


def tempos_esperados_no_dia(colaborador, d: date) -> dict[str, time | None] | None:
    """Horário esperado de cada batida (entrada, saída almoço, volta almoço,
    saída) nesse dia pela escala. None se não há escala vinculada ou o dia não
    é de trabalho — usado para saber qual batida um afastamento parcial (por
    horas) dispensa."""
    escala = colaborador.escala
    if escala is None:
        return None
    variante = variante_da_semana(colaborador, _segunda_da_semana(d))
    ed = EscalaDia.objects.filter(
        escala=escala, variante=variante, dia_semana=d.weekday()
    ).first()
    if not ed or not ed.trabalha:
        return None
    return {
        "entrada": ed.hora_entrada,
        "saida_almoco": ed.hora_saida_almoco,
        "volta_almoco": ed.hora_volta_almoco,
        "saida": ed.hora_saida,
    }
