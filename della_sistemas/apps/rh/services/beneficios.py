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


def _dias_ferias_no_mes(colaborador, ano: int, mes: int) -> set[date]:
    """Datas de férias do colaborador que caem dentro do mês (um set, dia a dia)."""
    _, ultimo = calendar.monthrange(ano, mes)
    ini_mes = date(ano, mes, 1)
    fim_mes = date(ano, mes, ultimo)
    dias: set[date] = set()
    gozos = GozoFerias.objects.filter(periodo__colaborador=colaborador)
    for g in gozos:
        ini = g.data_inicio
        fim = g.data_inicio + timedelta(days=g.dias - 1)
        # interseção com o mês
        a = max(ini, ini_mes)
        b = min(fim, fim_mes)
        d = a
        while d <= b:
            dias.add(d)
            d += timedelta(days=1)
    return dias


def dias_ferias_no_mes(colaborador, ano: int, mes: int) -> int:
    """Total de dias de férias do colaborador que caem dentro do mês (corridos,
    inclui domingo/folga — não é a base do desconto de VT, ver `dias_vt_sugeridos`)."""
    return len(_dias_ferias_no_mes(colaborador, ano, mes))


def dias_vt_sugeridos(colaborador, ano: int, mes: int) -> int:
    """Dias de VT sugeridos = dias trabalhados no mês − dias de férias que caem
    num dia em que ela realmente trabalharia (mínimo 0).

    Usa a escala da colaboradora quando vinculada (dias efetivamente trabalhados);
    caso contrário, cai no genérico Seg–Sáb do mês. Um dia de férias que cai num
    domingo (ou folga da escala) não desconta o VT — esse dia já não estava na
    base de dias trabalhados, então descontar de novo subtrairia em dobro.
    """
    from apps.rh.services.escala import dias_trabalho_no_mes

    if colaborador.escala is not None:
        dias_trabalhados = {d for d, _horas in dias_trabalho_no_mes(colaborador, ano, mes)}
        base = len(dias_trabalhados)
    else:
        _, ultimo = calendar.monthrange(ano, mes)
        dias_trabalhados = {
            date(ano, mes, dia)
            for dia in range(1, ultimo + 1)
            if date(ano, mes, dia).weekday() < 6
        }
        base = len(dias_trabalhados)

    ferias_que_descontam = dias_trabalhados & _dias_ferias_no_mes(colaborador, ano, mes)
    return max(base - len(ferias_que_descontam), 0)
