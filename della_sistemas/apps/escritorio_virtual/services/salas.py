"""Resolução da sala virtual de uma personagem.

Regra (aprovada no plano):

1. loja da batida válida mais recente do dia;
2. sala mapeada para essa loja (`SalaEscritorio.loja`);
3. sala padrão da personagem;
4. fallback seguro (entrada da loja, ou nada) + aviso técnico.

O vínculo loja -> sala mora em `SalaEscritorio`, não na personagem: quem sabe
onde a pessoa está é a batida (`BatidaPonto.loja`), e quem sabe o que aquela
loja representa no mapa é a sala. A comparação é por chave estrangeira, nunca
por texto do nome da loja.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from apps.escritorio_virtual.models import SalaEscritorio

logger = logging.getLogger(__name__)

# Slugs com papel fixo no cenário.
SLUG_ENTRADA    = "store-entrance"
SLUG_REFEITORIO = "cafeteria"

# Origem da resolução — exposta na API e no comando de diagnóstico para deixar
# explícito se a sala veio do dado real (loja) ou de um fallback.
ORIGEM_LOJA        = "loja"
ORIGEM_SALA_PADRAO = "sala_padrao"
ORIGEM_FALLBACK    = "fallback"
ORIGEM_INDEFINIDA  = "indefinida"


@dataclass(frozen=True)
class ResolucaoSala:
    """Sala resolvida + de onde veio. `sala` pode ser None quando não há
    nenhuma configuração utilizável (cena degrada, mas não quebra)."""

    sala: SalaEscritorio | None
    origem: str
    aviso: str | None = None

    @property
    def slug(self) -> str | None:
        return self.sala.slug if self.sala else None


def mapa_loja_para_sala(salas: list[SalaEscritorio] | None = None) -> dict[int, SalaEscritorio]:
    """{loja_id: sala} apenas para salas ativas com loja vinculada."""
    if salas is None:
        salas = list(SalaEscritorio.objects.filter(ativo=True).select_related("loja"))
    return {s.loja_id: s for s in salas if s.loja_id and s.ativo}


def _sala_por_slug(salas: list[SalaEscritorio], slug: str) -> SalaEscritorio | None:
    for s in salas:
        if s.slug == slug and s.ativo:
            return s
    return None


def resolver_sala_trabalho(
    personagem,
    batidas_do_dia: list,
    salas: list[SalaEscritorio],
    por_loja: dict[int, SalaEscritorio] | None = None,
) -> ResolucaoSala:
    """Sala onde a personagem TRABALHA hoje.

    Não é necessariamente a sala onde ela aparece agora: quem está no almoço
    aparece no refeitório (ver `sala_da_cena`). `batidas_do_dia` já vem
    carregada pela projeção, para não disparar query por personagem."""
    if por_loja is None:
        por_loja = mapa_loja_para_sala(salas)

    # 1 e 2: loja da batida válida mais recente que informa loja.
    for batida in sorted(batidas_do_dia, key=lambda b: b.momento, reverse=True):
        if not batida.loja_id:
            continue
        sala = por_loja.get(batida.loja_id)
        if sala is not None:
            return ResolucaoSala(sala=sala, origem=ORIGEM_LOJA)
        # Loja conhecida mas sem sala mapeada: cai para o passo 3, avisando.
        return _sala_padrao_ou_fallback(
            personagem, salas, aviso="loja_sem_sala_mapeada",
        )

    # 3 e 4: nenhuma batida com loja.
    return _sala_padrao_ou_fallback(personagem, salas, aviso=None)


def _sala_padrao_ou_fallback(personagem, salas, aviso: str | None) -> ResolucaoSala:
    sala_padrao = personagem.sala_padrao
    if sala_padrao is not None and sala_padrao.ativo:
        return ResolucaoSala(sala=sala_padrao, origem=ORIGEM_SALA_PADRAO, aviso=aviso)

    entrada = _sala_por_slug(salas, SLUG_ENTRADA)
    if entrada is not None:
        # Aviso técnico: só o id da personagem, nunca nome/dado pessoal.
        logger.warning(
            "escritorio: personagem %s sem sala padrão utilizável; usando %s",
            personagem.pk, SLUG_ENTRADA,
        )
        return ResolucaoSala(
            sala=entrada, origem=ORIGEM_FALLBACK,
            aviso=aviso or "personagem_sem_sala_padrao",
        )

    logger.warning(
        "escritorio: personagem %s sem sala resolvível (nenhuma sala ativa)", personagem.pk,
    )
    return ResolucaoSala(
        sala=None, origem=ORIGEM_INDEFINIDA,
        aviso=aviso or "sem_sala_configurada",
    )


def sala_da_cena(estado: str, resolucao: ResolucaoSala, salas: list[SalaEscritorio]) -> ResolucaoSala:
    """Onde a personagem aparece AGORA, dado o estado.

    Almoço leva ao refeitório; chegada e saída ficam na entrada; estados sem
    presença física (folga, ausência, batida faltando, fim de expediente) não
    renderizam personagem nenhuma. `MISSING_PUNCH` sai de cena de propósito:
    a pessoa não está na loja de madrugada só porque esqueceu de bater."""
    from apps.escritorio_virtual.services.projecao import EstadoPersonagem as E

    if estado in (E.LUNCH, E.RETURNING_FROM_LUNCH):
        refeitorio = _sala_por_slug(salas, SLUG_REFEITORIO)
        if refeitorio is not None:
            return ResolucaoSala(sala=refeitorio, origem=resolucao.origem, aviso=resolucao.aviso)
        return ResolucaoSala(
            sala=resolucao.sala, origem=resolucao.origem,
            aviso=resolucao.aviso or "sem_refeitorio_configurado",
        )

    if estado in (E.ARRIVING, E.LEAVING):
        entrada = _sala_por_slug(salas, SLUG_ENTRADA)
        if entrada is not None:
            return ResolucaoSala(sala=entrada, origem=resolucao.origem, aviso=resolucao.aviso)
        return resolucao

    if estado in (E.WORKING, E.AWAY):
        return resolucao

    # OFFLINE, OFF_SHIFT, DAY_OFF, ABSENT, MISSING_PUNCH: fora de cena.
    return ResolucaoSala(sala=None, origem=resolucao.origem, aviso=resolucao.aviso)
