"""
Integração com a API dos Correios CWS para rastreamento de objetos.

Autenticação: Basic Auth (CNPJ + código de acesso) → JWT com ~1h de validade.
O JWT é cacheado para evitar reautenticação a cada cron.

Endpoint de rastreio: GET /sro/v1/objetos?codigosObjetos={codigo}&tipo=T&resultado=U&linguagem=pt
"""
import base64
import logging
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.correios.com.br'
CACHE_KEY = 'correios_jwt_token'


def _obter_token() -> str | None:
    """Retorna JWT válido, usando cache quando possível."""
    token = cache.get(CACHE_KEY)
    if token:
        return token

    usuario = getattr(settings, 'CORREIOS_USUARIO', '')
    codigo = getattr(settings, 'CORREIOS_CODIGO_ACESSO', '')
    if not usuario or not codigo:
        logger.error('CORREIOS_USUARIO ou CORREIOS_CODIGO_ACESSO não configurados.')
        return None

    credencial = base64.b64encode(f'{usuario}:{codigo}'.encode()).decode()
    try:
        resp = requests.post(
            f'{BASE_URL}/token/v1/autentica',
            headers={'Authorization': f'Basic {credencial}'},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get('token')
        expira_em = data.get('expiraEm')

        ttl = 3000  # 50 min padrão
        if expira_em:
            try:
                exp_dt = datetime.fromisoformat(expira_em.replace('Z', '+00:00'))
                segundos = int((exp_dt - datetime.now(timezone.utc)).total_seconds()) - 120
                ttl = max(60, segundos)
            except Exception:
                pass

        cache.set(CACHE_KEY, token, ttl)
        logger.info('Token Correios obtido, expira em %s (TTL cache: %ds)', expira_em, ttl)
        return token

    except requests.HTTPError as exc:
        logger.error('Falha ao obter token Correios: %s %s', exc.response.status_code, exc.response.text)
    except Exception as exc:
        logger.error('Erro ao obter token Correios: %s', exc)
    return None


def rastrear_objeto(codigo: str) -> list[dict] | None:
    """
    Consulta eventos de rastreio de um objeto.
    Retorna lista de eventos (mais recente primeiro) ou None em caso de erro.

    Cada evento: {'descricao': str, 'dtHrCriado': str, 'codigo': str}
    """
    token = _obter_token()
    if not token:
        return None

    try:
        resp = requests.get(
            f'{BASE_URL}/sro/v1/objetos',
            params={'codigosObjetos': codigo, 'tipo': 'T', 'resultado': 'U', 'linguagem': 'pt'},
            headers={'Authorization': f'Bearer {token}'},
            timeout=15,
        )

        if resp.status_code == 401:
            cache.delete(CACHE_KEY)
            logger.warning('Token Correios expirado, invalidado do cache.')
            return None

        resp.raise_for_status()
        objetos = resp.json().get('objetos', [])
        if not objetos:
            return []

        return objetos[0].get('eventos', [])

    except requests.HTTPError as exc:
        logger.error('Erro HTTP ao rastrear %s: %s %s', codigo, exc.response.status_code, exc.response.text)
    except Exception as exc:
        logger.error('Erro ao rastrear %s: %s', codigo, exc)
    return None


def detectar_evento(eventos: list[dict]) -> str | None:
    """
    Analisa a lista de eventos e retorna o evento mais relevante:
    - 'entregue'     — entregue ao destinatário
    - 'saiu_entrega' — saiu para entrega (ainda não entregue)
    - 'postado'      — objeto postado na agência (confirma despacho)
    - None           — nenhum evento relevante detectado
    """
    for evento in eventos:
        desc = (evento.get('descricao') or '').lower()
        cod = (evento.get('codigo') or '').upper()
        if any(p in desc for p in ('entregue ao destinatário', 'entregue ao destinatario', 'objeto entregue')):
            return 'entregue'
        if cod == 'BDE' and 'entregue' in desc:
            return 'entregue'

    for evento in eventos:
        desc = (evento.get('descricao') or '').lower()
        cod = (evento.get('codigo') or '').upper()
        if any(p in desc for p in ('saiu para entrega', 'em rota de entrega', 'saindo para entrega')):
            return 'saiu_entrega'
        if cod in ('OUT', 'RO') and 'entrega' in desc:
            return 'saiu_entrega'

    for evento in eventos:
        desc = (evento.get('descricao') or '').lower()
        cod = (evento.get('codigo') or '').upper()
        if any(p in desc for p in ('objeto postado', 'postado', 'objeto coletado')):
            return 'postado'
        if cod in ('CO', 'PO'):
            return 'postado'

    return None
