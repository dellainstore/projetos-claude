"""Constantes do módulo analytics."""

from datetime import date, datetime

from django.utils import timezone

# Em 28/06/2026 removemos do site os acessos de bots/scans. Dados anteriores a
# essa data poluem as métricas (tráfego inflado, origens erradas), então todos
# os relatórios — dashboard e resumo semanal — passam a considerar apenas
# tráfego a partir desse dia. Para voltar a incluir o histórico, basta recuar
# esta data (os dados continuam no banco; só ficam ocultos, não foram apagados).
DATA_CORTE_ANALYTICS = date(2026, 6, 28)


def inicio_corte_aware() -> datetime:
    """Início do dia de corte como datetime aware no fuso atual."""
    return timezone.make_aware(
        datetime.combine(DATA_CORTE_ANALYTICS, datetime.min.time())
    )
