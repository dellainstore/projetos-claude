"""Gera (ou reaproveita) o link curto para uma postagem, e guarda o historico.

Fluxo: Site > Gerar link chama `obter_ou_criar()`, que:
1. Procura um LinkGerado ja existente para o MESMO destino (mesma pagina +
   mesmo canal + mesmo nome opcional) e devolve ele, sem chamar o site_della
   de novo. E assim que "gerei nesse canal antes, perdi o link, gerei de
   novo" recupera o mesmo endereco em vez de espalhar links diferentes para
   a mesma coisa.
2. Se nao existe, pede um codigo novo ao site_della (endpoint interno
   protegido por segredo compartilhado) e registra o LinkGerado.

Se o site_della estiver fora do ar, devolve o link completo (com UTM, sem
encurtar) como fallback, para o usuario nunca ficar sem link nenhum.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger('apps.analytics')

_TIMEOUT_SEGUNDOS = 6


class LinkCurtoIndisponivel(Exception):
    """Levantada quando o site_della nao respondeu; quem chama decide o fallback."""


def _pedir_codigo_ao_site(destino: str) -> dict:
    resp = requests.post(
        f'{settings.SITE_URL}/interno/link-curto/',
        json={'destino': destino},
        headers={'X-Link-Curto-Secret': settings.LINK_CURTO_SECRET},
        timeout=_TIMEOUT_SEGUNDOS,
    )
    resp.raise_for_status()
    return resp.json()


def obter_ou_criar(usuario, destino: str, canal: str):
    """Devolve (LinkGerado, criado_agora: bool).

    Levanta `LinkCurtoIndisponivel` se precisar criar e o site_della nao
    responder — quem chama decide se mostra o link completo como fallback.
    """
    from apps.analytics.models_link_curto import LinkGerado

    existente = LinkGerado.objects.filter(destino=destino).first()
    if existente:
        return existente, False

    try:
        dados = _pedir_codigo_ao_site(destino)
    except (requests.RequestException, ValueError) as e:
        logger.warning('Falha ao criar link curto para %s: %s', destino, e)
        raise LinkCurtoIndisponivel from e

    novo = LinkGerado.objects.create(
        usuario=usuario, destino=destino, canal=canal,
        url_curta=dados.get('url', ''),
    )
    return novo, True


def historico(limite=200):
    from apps.analytics.models_link_curto import LinkGerado
    return (
        LinkGerado.objects
        .select_related('usuario')
        .order_by('-criado_em')[:limite]
    )
