"""Cálculo de VT: dias úteis do mês (Seg–Sáb) menos dias de férias no período."""

import calendar
from datetime import date, timedelta

from apps.rh.models import GozoFerias


def dias_uteis_mes(ano: int, mes: int) -> int:
    """Conta dias Seg–Sáb do mês (weekday 0–5; domingo=6 fora)."""
    _, ultimo = calendar.monthrange(ano, mes)
    return sum(
        1
        for dia in range(1, ultimo + 1)
        if date(ano, mes, dia).weekday() < 6
    )


def dias_ferias_no_mes(colaborador, ano: int, mes: int) -> int:
    """Total de dias de férias do colaborador que caem dentro do mês."""
    _, ultimo = calendar.monthrange(ano, mes)
    ini_mes = date(ano, mes, 1)
    fim_mes = date(ano, mes, ultimo)
    total = 0
    gozos = GozoFerias.objects.filter(periodo__colaborador=colaborador)
    for g in gozos:
        ini = g.data_inicio
        fim = g.data_inicio + timedelta(days=g.dias - 1)
        # interseção com o mês
        a = max(ini, ini_mes)
        b = min(fim, fim_mes)
        if a <= b:
            total += (b - a).days + 1
    return total


def dias_vt_sugeridos(colaborador, ano: int, mes: int) -> int:
    """Dias de VT sugeridos = dias trabalhados no mês − dias de férias (mínimo 0).

    Usa a escala da colaboradora quando vinculada (dias efetivamente trabalhados);
    caso contrário, cai no genérico Seg–Sáb do mês.
    """
    from apps.rh.services.escala import dias_uteis_escala

    base = dias_uteis_escala(colaborador, ano, mes)
    if base is None:
        base = dias_uteis_mes(ano, mes)
    return max(base - dias_ferias_no_mes(colaborador, ano, mes), 0)
