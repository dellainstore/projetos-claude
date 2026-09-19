"""Eventos do escritório derivados das batidas de ponto.

Nada aqui é persistido: o "log de eventos" é uma PROJEÇÃO de `BatidaPonto`,
recalculada a cada leitura. Isso resolve de graça correção e exclusão de
batida (`PUNCH_CORRECTED` / `PUNCH_DELETED`): se a batida mudou ou sumiu, a
projeção seguinte já reflete, sem evento a processar e sem estado duplicado
para reconciliar.

O `eventId` é derivado do id da batida (`ponto_<id>`), estável entre
leituras — é o que permite ao frontend não repetir a mesma animação.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

# Fonte declarada em todo evento. Existe para o dia em que houver um segundo
# produtor (agentes, integrações); hoje é sempre o painel.
FONTE = "della_sistemas"

# Tipo da batida (apps.rh) -> nome do evento do escritório.
EVENTO_POR_TIPO = {
    "entrada": "CLOCK_IN",
    "saida_almoco": "LUNCH_START",
    "volta_almoco": "LUNCH_END",
    "saida": "CLOCK_OUT",
}

# Eventos que disparam uma transição animada quando recentes.
EVENTOS_DE_TRANSICAO = {"CLOCK_IN", "LUNCH_END", "CLOCK_OUT"}


@dataclass(frozen=True)
class Evento:
    """Evento derivado de uma batida. `employee_id` é o id do Colaborador,
    nunca o nome (nome não é chave técnica)."""

    event_id: str
    employee_id: int
    event: str
    occurred_at: datetime

    def como_dict(self) -> dict:
        return {
            "eventId": self.event_id,
            "employeeId": self.employee_id,
            "event": self.event,
            "occurredAt": timezone.localtime(self.occurred_at).isoformat(),
            "source": FONTE,
        }


def evento_da_batida(batida) -> Evento | None:
    """Converte uma `BatidaPonto` em evento. `None` se o tipo for desconhecido
    (defensivo: um tipo novo no ponto não pode quebrar a cena)."""
    nome = EVENTO_POR_TIPO.get(batida.tipo)
    if nome is None:
        return None
    return Evento(
        event_id=f"ponto_{batida.pk}",
        employee_id=batida.colaborador_id,
        event=nome,
        occurred_at=batida.momento,
    )


def eventos_das_batidas(batidas) -> list[Evento]:
    """Eventos de uma lista de batidas, em ordem cronológica."""
    eventos = [evento_da_batida(b) for b in sorted(batidas, key=lambda x: x.momento)]
    return [e for e in eventos if e is not None]


def evento_recente(
    eventos: list[Evento], agora: datetime, janela_segundos: int
) -> Evento | None:
    """Último evento de transição ocorrido há menos de `janela_segundos`.

    É isso que torna a animação determinística para qualquer cliente: quem
    abre a página 30s depois da batida vê a transição; quem abre 10 minutos
    depois vê a cena já parada no lugar certo. O cliente não precisa ter
    estado anterior nenhum."""
    if not eventos or janela_segundos <= 0:
        return None
    ultimo = eventos[-1]
    if ultimo.event not in EVENTOS_DE_TRANSICAO:
        return None
    idade = (agora - ultimo.occurred_at).total_seconds()
    if 0 <= idade <= janela_segundos:
        return ultimo
    return None


def primeiro_clock_in(eventos: list[Evento]) -> Evento | None:
    """Primeira entrada da lista — usada para detectar a abertura da loja."""
    for e in eventos:
        if e.event == "CLOCK_IN":
            return e
    return None
