from calendar import monthrange
from datetime import date, datetime, timedelta

from django.http import HttpRequest
from django.utils import timezone

PERIODOS = [
    ("hoje", "Hoje"),
    ("ontem", "Ontem"),
    ("7dias", "Últimos 7 dias"),
    ("mes_atual", "Mês atual"),
    ("mes_anterior", "Mês anterior"),
    ("personalizado", "Personalizado"),
]


class Periodo:
    def __init__(self, chave: str, inicio: datetime, fim: datetime, data_inicio_str: str, data_fim_str: str):
        self.chave = chave
        self.inicio = inicio
        self.fim = fim
        self.data_inicio_str = data_inicio_str
        self.data_fim_str = data_fim_str


def parse_periodo(request: HttpRequest) -> Periodo:
    """Mesmo padrao de filtro de `produtos/historico.py` (hoje/ontem/7/30/60
    dias/personalizado), agora sobre datetimes com timezone do Django."""
    hoje = timezone.localdate()
    chave = request.GET.get("periodo", "7dias")
    data_inicio_str = request.GET.get("data_inicio", "")
    data_fim_str = request.GET.get("data_fim", "")

    tz = timezone.get_current_timezone()

    def _aware(d: date, fim_do_dia: bool = False) -> datetime:
        dt = datetime(d.year, d.month, d.day, 23, 59, 59) if fim_do_dia else datetime(d.year, d.month, d.day)
        return timezone.make_aware(dt, tz)

    if chave == "hoje":
        inicio, fim = _aware(hoje), _aware(hoje, True)
    elif chave == "ontem":
        ontem = hoje - timedelta(days=1)
        inicio, fim = _aware(ontem), _aware(ontem, True)
    elif chave == "mes_atual":
        d_ini = date(hoje.year, hoje.month, 1)
        d_fim = date(hoje.year, hoje.month, monthrange(hoje.year, hoje.month)[1])
        inicio, fim = _aware(d_ini), _aware(d_fim, True)
    elif chave == "mes_anterior":
        ano_ant, mes_ant = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
        d_ini = date(ano_ant, mes_ant, 1)
        d_fim = date(ano_ant, mes_ant, monthrange(ano_ant, mes_ant)[1])
        inicio, fim = _aware(d_ini), _aware(d_fim, True)
    elif chave == "personalizado":
        try:
            d_ini = datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            d_ini = hoje - timedelta(days=6)
        try:
            d_fim = datetime.strptime(data_fim_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            d_fim = hoje
        inicio, fim = _aware(d_ini), _aware(d_fim, True)
    else:  # "7dias" e fallback
        chave = "7dias"
        inicio, fim = _aware(hoje - timedelta(days=6)), _aware(hoje, True)

    return Periodo(chave, inicio, fim, data_inicio_str, data_fim_str)
