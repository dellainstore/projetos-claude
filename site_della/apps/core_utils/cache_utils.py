import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# ─── Chaves canônicas ─────────────────────────────────────────────────────────
MENU_CATEGORIAS      = 'menu_categorias_ativas'
HOME_BANNERS         = 'home_banners'
HOME_MINI_BANNERS    = 'home_mini_banners'
HOME_LOOK            = 'home_look_semana'
HOME_DEPOIMENTOS     = 'home_depoimentos'
HOME_DESTAQUES       = 'home_produtos_destaque'
LOJA_CONFIG          = 'loja_config'
GUIA_TABELAS         = 'guia_tabelas_medidas'
MANUTENCAO_ATIVA     = 'manutencao_ativa'
TARJA_FRASES         = 'tarja_frases'
NEWSLETTER_OFERTA    = 'newsletter_cupom_oferta'
LINKS_BIO            = 'links_bio_ativos'

def _key_pagina(slug: str) -> str:
    return f'pagina_estatica_{slug}'

def _key_relacionados(categoria_id) -> str:
    return f'produtos_relacionados_{categoria_id}'

def _key_tabela_medidas(categoria_id) -> str:
    return f'tabela_medidas_{categoria_id}'

# ─── Invalidações específicas ─────────────────────────────────────────────────

def invalidar_categorias():
    cache.delete(MENU_CATEGORIAS)

def invalidar_banners():
    cache.delete_many([HOME_BANNERS, HOME_MINI_BANNERS, HOME_LOOK])

def invalidar_look():
    cache.delete(HOME_LOOK)

def invalidar_pagina(slug: str):
    cache.delete(_key_pagina(slug))

def invalidar_config_loja():
    cache.delete_many([LOJA_CONFIG, HOME_DESTAQUES])

def invalidar_manutencao():
    cache.delete(MANUTENCAO_ATIVA)

def invalidar_tarja():
    cache.delete(TARJA_FRASES)

def invalidar_links_bio():
    cache.delete(LINKS_BIO)

def invalidar_newsletter_oferta():
    cache.delete(NEWSLETTER_OFERTA)

def invalidar_categoria_produtos(categoria_id):
    cache.delete_many([
        _key_relacionados(categoria_id),
        _key_tabela_medidas(categoria_id),
    ])


def invalidar_tabelas_medidas(categoria_id=None):
    cache.delete(GUIA_TABELAS)

    if categoria_id:
        cache.delete(_key_tabela_medidas(categoria_id))
        return

    try:
        from apps.produtos.models import Categoria
        categoria_ids = Categoria.objects.values_list('id', flat=True)
        cache.delete_many([_key_tabela_medidas(cat_id) for cat_id in categoria_ids])
    except Exception:
        logger.warning('Falha ao invalidar cache de tabelas de medidas por categoria', exc_info=True)

def invalidar_home_completa():
    cache.delete_many([
        HOME_BANNERS, HOME_MINI_BANNERS, HOME_LOOK,
        HOME_DEPOIMENTOS, HOME_DESTAQUES,
    ])
