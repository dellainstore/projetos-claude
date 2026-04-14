"""
Integração com Instagram Graph API.

Busca os últimos posts da conta e armazena em cache para não
atingir os rate limits da API a cada requisição da homepage.

Configuração necessária no .env:
    INSTAGRAM_ACCESS_TOKEN=<long-lived token>

Como obter o token:
    1. Criar app no developers.facebook.com
    2. Adicionar produto "Instagram Basic Display"
    3. Gerar token de usuário (válido 60 dias)
    4. Trocar por Long-Lived Token via endpoint /access_token
    5. Renovar antes de expirar (ou usar token de página que não expira)
"""

import logging

import requests
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

GRAPH_URL     = 'https://graph.instagram.com'
CACHE_KEY     = 'instagram_posts'
CACHE_TIMEOUT = 60 * 60      # 1 hora
MEDIA_FIELDS  = 'id,media_type,media_url,thumbnail_url,permalink,timestamp'


def buscar_posts_instagram(limit: int = 9) -> list[dict]:
    """
    Retorna lista de posts do Instagram.
    Usa cache de 1 hora para evitar chamadas repetidas à API.
    Em caso de falha ou token não configurado, retorna lista vazia.
    """
    # Tenta retornar do cache primeiro
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached[:limit]

    token = getattr(settings, 'INSTAGRAM_ACCESS_TOKEN', '').strip()
    if not token:
        logger.debug('Instagram: INSTAGRAM_ACCESS_TOKEN não configurado.')
        return []

    posts = _buscar_da_api(token, limit)
    if posts:
        cache.set(CACHE_KEY, posts, CACHE_TIMEOUT)

    return posts


def limpar_cache_instagram():
    """Força a renovação do cache na próxima requisição."""
    cache.delete(CACHE_KEY)
    logger.info('Cache do Instagram limpo.')


def renovar_token_longa_duracao(token_curto: str) -> str | None:
    """
    Troca um token de curta duração (1h) por um de longa duração (60 dias).
    Uso: python manage.py shell → from apps.produtos.instagram import renovar_token_longa_duracao
    """
    app_id     = getattr(settings, 'INSTAGRAM_APP_ID', '')
    app_secret = getattr(settings, 'INSTAGRAM_APP_SECRET', '')

    if not app_id or not app_secret:
        logger.error('Instagram: INSTAGRAM_APP_ID e INSTAGRAM_APP_SECRET necessários para renovar token.')
        return None

    try:
        resp = requests.get(
            f'{GRAPH_URL}/access_token',
            params={
                'grant_type':        'ig_exchange_token',
                'client_secret':     app_secret,
                'access_token':      token_curto,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        novo_token = data.get('access_token')
        expira_em  = data.get('expires_in', 0)
        logger.info('Token renovado. Expira em %d segundos (~%d dias).', expira_em, expira_em // 86400)
        return novo_token
    except Exception as exc:
        logger.error('Instagram: falha ao renovar token: %s', exc)
        return None


# ── Internos ──────────────────────────────────────────────────────────────────

def _buscar_da_api(token: str, limit: int) -> list[dict]:
    """Faz a chamada real à Graph API e normaliza os posts."""
    try:
        resp = requests.get(
            f'{GRAPH_URL}/me/media',
            params={
                'fields':       MEDIA_FIELDS,
                'limit':        limit * 2,   # busca mais para filtrar vídeos sem thumb
                'access_token': token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response else '?'
        body   = exc.response.text[:200] if exc.response else ''
        if status == 400 and 'OAuthException' in body:
            logger.error('Instagram: token inválido ou expirado. Gere um novo token.')
        else:
            logger.error('Instagram: erro HTTP %s — %s', status, body)
        return []
    except Exception as exc:
        logger.error('Instagram: falha na requisição: %s', exc)
        return []

    posts = []
    for item in data.get('data', []):
        media_type = item.get('media_type', '')

        # Ignora Reels/vídeos sem thumbnail
        if media_type == 'VIDEO' and not item.get('thumbnail_url'):
            continue

        posts.append({
            'id':            item.get('id', ''),
            'media_type':    media_type,
            'media_url':     item.get('media_url', ''),
            'thumbnail_url': item.get('thumbnail_url') or item.get('media_url', ''),
            'permalink':     item.get('permalink', ''),
            'timestamp':     item.get('timestamp', ''),
        })

        if len(posts) >= limit:
            break

    logger.info('Instagram: %d post(s) carregado(s) da API.', len(posts))
    return posts
