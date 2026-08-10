"""Dias úteis e feriados (nacionais + bancários móveis + São Paulo capital/estado).

Usado para ajustar datas de pagamento: quando um pagamento cai em sábado, domingo
ou feriado, antecipa para o dia útil anterior. Também usado no ponto: dia de
feriado não cobra batida nem gera pendência de correção.
"""

import calendar
import functools
from datetime import date, timedelta

from dateutil.easter import easter


@functools.lru_cache(maxsize=None)
def feriados(ano: int) -> frozenset[date]:
    pascoa = easter(ano)
    fixos = {
        date(ano, 1, 1),    # Confraternização
        date(ano, 4, 21),   # Tiradentes
        date(ano, 5, 1),    # Dia do Trabalho
        date(ano, 9, 7),    # Independência
        date(ano, 10, 12),  # N. Sra. Aparecida
        date(ano, 11, 2),   # Finados
        date(ano, 11, 15),  # Proclamação da República
        date(ano, 11, 20),  # Consciência Negra (nacional desde 2024)
        date(ano, 12, 25),  # Natal
        date(ano, 1, 25),   # Aniversário de São Paulo (capital)
        date(ano, 7, 9),    # Revolução Constitucionalista de 1932 (estadual SP)
    }
    moveis = {
        pascoa - timedelta(days=48),  # Carnaval (segunda)
        pascoa - timedelta(days=47),  # Carnaval (terça)
        pascoa - timedelta(days=2),   # Sexta-feira Santa
        pascoa + timedelta(days=60),  # Corpus Christi
    }
    return frozenset(fixos | moveis)


def eh_dia_util(d: date) -> bool:
    """Dia útil = segunda a sexta e não feriado."""
    return d.weekday() < 5 and d not in feriados(d.year)


def dia_util_anterior_ou_mesmo(d: date) -> date:
    """Retorna o próprio dia se for útil; senão, o dia útil imediatamente anterior."""
    while not eh_dia_util(d):
        d -= timedelta(days=1)
    return d


def enesimo_dia_util(ano: int, mes: int, n: int) -> date | None:
    """N-ésimo dia útil do mês (ex.: 5º dia útil para o salário)."""
    ultimo = calendar.monthrange(ano, mes)[1]
    contador = 0
    for dia in range(1, ultimo + 1):
        d = date(ano, mes, dia)
        if eh_dia_util(d):
            contador += 1
            if contador == n:
                return d
    return None
