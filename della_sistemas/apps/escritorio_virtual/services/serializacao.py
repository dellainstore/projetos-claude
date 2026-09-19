"""Serialização da cena para a API interna autenticada.

Esta é a ÚNICA função que monta o corpo da resposta HTTP. Ela não serializa o
objeto de projeção inteiro: constrói um dicionário novo, campo a campo, a
partir de uma lista fechada. Assim, um campo novo na projeção (ou no modelo de
ponto) não vaza por acidente — e o teste `test_api.py` trava esse contrato.

Fora do payload, de propósito:

* latitude, longitude, distância do geofence (GPS nunca sai daqui);
* saldo de horas, horas trabalhadas, jornada esperada;
* tipo do afastamento (atestado/férias/falta) e o `motivo` técnico da
  projeção, que distingue afastamento de folga;
* nome civil completo (só o primeiro nome vai, como nome de personagem);
* lista de batidas do dia (só o evento recente, quando há animação).

A visão pública sanitizada (mais restrita ainda) não existe nesta versão e
será um módulo separado quando for aprovada.
"""

from __future__ import annotations

import hashlib
import json

from django.utils import timezone

from apps.escritorio_virtual.services.projecao import Cena, EstadoPersonagem

VERSAO_CONTRATO = 1

# Estados em que faz sentido exibir "desde HH:MM". Nos demais (ausência,
# batida faltando, folga) o horário da última batida não acrescenta nada à
# cena e é informação administrativa.
_ESTADOS_COM_DESDE = {
    EstadoPersonagem.WORKING,
    EstadoPersonagem.LUNCH,
    EstadoPersonagem.ARRIVING,
    EstadoPersonagem.RETURNING_FROM_LUNCH,
    EstadoPersonagem.LEAVING,
    EstadoPersonagem.AWAY,
    EstadoPersonagem.OFF_SHIFT,
}


def _iso_minuto(dt) -> str | None:
    """ISO 8601 no fuso local, truncado no minuto (segundo exato de batida
    não é necessário para a cena)."""
    if dt is None:
        return None
    return timezone.localtime(dt).replace(second=0, microsecond=0).isoformat()


def _sala(sala) -> dict:
    return {
        "slug": sala.slug,
        "nome": sala.nome,
        "ordem": sala.ordem,
        "pos_x": sala.pos_x,
        "pos_y": sala.pos_y,
        "largura": sala.largura,
        "altura": sala.altura,
    }


def _personagem(ator) -> dict:
    evento = None
    if ator.evento_recente is not None:
        evento = {
            "eventId": ator.evento_recente.event_id,
            "event": ator.evento_recente.event,
            "occurredAt": _iso_minuto(ator.evento_recente.occurred_at),
        }
    return {
        "id": ator.personagem.pk,
        "personagem": ator.personagem.personagem,
        "nome": ator.nome_exibicao,
        "tipoAtor": ator.personagem.tipo_ator,
        "estado": ator.estado,
        "estadoEstavel": ator.estado_estavel,
        "desde": _iso_minuto(ator.desde) if ator.estado in _ESTADOS_COM_DESDE else None,
        "sala": ator.sala.slug,
        "salaTrabalho": ator.sala_trabalho.slug,
        "salaOrigem": ator.sala_trabalho.origem,
        "posX": ator.personagem.pos_x,
        "posY": ator.personagem.pos_y,
        "evento": evento,
        "inconsistencia": ator.inconsistencia,
    }


def serializar_cena(cena: Cena, preview: dict | None = None) -> dict:
    """Payload completo da API interna.

    `preview` descreve a pré-visualização em curso (data e hora escolhidas),
    ou o modo ao vivo. Entra no payload e, por consequência, no ETag: duas
    horas diferentes do mesmo dia são cenas diferentes."""
    pendencias = sum(
        1 for a in cena.atores if a.estado == EstadoPersonagem.MISSING_PUNCH
    )
    return {
        "preview": preview or {"ativo": False},
        "versao": VERSAO_CONTRATO,
        "data": cena.data.isoformat(),
        "geradoEm": _iso_minuto(cena.gerado_em),
        "pollSegundos": cena.parametros.poll_segundos,
        "loja": {
            "estado": cena.estado_loja,
            "luzesAcesas": cena.luzes_acesas,
            "portaAberta": cena.porta_aberta,
            "pendencias": pendencias,
        },
        "salas": [_sala(s) for s in cena.salas],
        "personagens": [_personagem(a) for a in cena.atores],
        "avisos": list(cena.avisos),
    }


# Campos voláteis que mudam a cada requisição sem representar mudança de cena.
# Ficam fora do ETag, senão nunca haveria um 304.
_FORA_DO_ETAG = ("geradoEm",)


def calcular_etag(payload: dict) -> str:
    """ETag determinístico: mesma cena, mesmo ETag, independente da instância
    do Gunicorn que respondeu (nada de id() nem de timestamp de processo)."""
    base = {k: v for k, v in payload.items() if k not in _FORA_DO_ETAG}
    canonico = json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonico.encode("utf-8")).hexdigest()[:32]
    return f'"{digest}"'


def etag_corresponde(cabecalho_if_none_match: str | None, etag: str) -> bool:
    """Compara o `If-None-Match` recebido com o ETag atual.

    Aceita lista separada por vírgula, `*` e o prefixo fraco `W/`."""
    if not cabecalho_if_none_match:
        return False
    def _normalizar(valor: str) -> str:
        valor = valor.strip()
        if valor.startswith("W/"):
            valor = valor[2:]
        return valor
    recebidos = {_normalizar(v) for v in cabecalho_if_none_match.split(",")}
    return "*" in recebidos or _normalizar(etag) in recebidos
