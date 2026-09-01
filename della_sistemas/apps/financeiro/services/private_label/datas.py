"""Aritmética de datas para parcelas/recorrências — sem dependência nova
(usa só `calendar`/`datetime` da stdlib, evita adicionar python-dateutil
sem necessidade comprovada)."""
import calendar
from datetime import date, timedelta

MESES_POR_FREQUENCIA = {
    "mensal": 1,
    "trimestral": 3,
    "semestral": 6,
    "anual": 12,
}


def somar_periodo(data_base: date, frequencia: str) -> date:
    """Soma 1 período (semanal/mensal/trimestral/semestral/anual) à data,
    preservando o dia quando possível (cai pro último dia do mês se o mês de
    destino for mais curto — ex.: 31/01 mensal -> 28 ou 29/02)."""
    if frequencia == "semanal":
        return data_base + timedelta(weeks=1)
    meses = MESES_POR_FREQUENCIA.get(frequencia)
    if meses is None:
        raise ValueError(f"Frequência desconhecida: {frequencia}")
    return somar_meses(data_base, meses)


def normalizar_data(valor) -> date:
    """Aceita `date` ou string ISO ('YYYY-MM-DD', o que vem de
    `request.POST`/`<input type="date">`) e sempre devolve um `date` de
    verdade — necessário porque Django só coage string->date na hora de
    salvar no banco, não antes, e os services fazem aritmética de data
    (somar_periodo) com o valor ainda em memória."""
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def somar_meses(data_base: date, meses: int) -> date:
    total_mes = data_base.month - 1 + meses
    ano = data_base.year + total_mes // 12
    mes = total_mes % 12 + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)
