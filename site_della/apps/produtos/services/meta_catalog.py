"""
Integracao com a Content API de Catalogo da Meta (Commerce Manager).

Empurra atualizacoes de produto (preco, disponibilidade, estoque) em tempo
real assim que o Produto ou uma de suas Variacao e salvo, em vez de esperar
o proximo carregamento do feed diario (/feed-meta.xml).

O dicionario de campos e montado uma unica vez em `produto_para_item_meta`
e reaproveitado tanto pelo feed XML (apps/produtos/views.py:feed_meta_xml)
quanto por este push em tempo real, para os dois nunca divergirem.

Configuracao necessaria no .env:
    META_CATALOG_TOKEN=<token de System User com permissao catalog_management>
    META_CATALOG_ID=<id do catalogo no Commerce Manager>

Como gerar o token:
    1. Business Manager > Configuracoes > Usuarios do sistema
    2. Atribuir o catalogo ao usuario do sistema (Ativos > Catalogos > Gerenciar catalogo)
    3. Gerar novo token com a permissao catalog_management marcada
"""

import json
import logging

import requests
from django.conf import settings
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

GRAPH_URL = 'https://graph.facebook.com'
TIMEOUT   = 10


def catalogo_configurado() -> bool:
    return bool(settings.META_CATALOG_TOKEN and settings.META_CATALOG_ID)


def produto_disponivel(produto) -> bool:
    variacoes = [v for v in produto.variacoes.all() if v.ativa]
    if not variacoes:
        return True
    return any(v.disponivel for v in variacoes)


def produto_quantidade(produto) -> int:
    variacoes = [v for v in produto.variacoes.all() if v.ativa and v.disponivel]
    if not variacoes:
        return 0
    total = 0
    for v in variacoes:
        if v.modo_efetivo == 'sob_demanda':
            return 999
        total += v.estoque or 0
    return max(total, 1)


def formatar_preco_meta(valor) -> str:
    return f'{valor:.2f} BRL'


def produto_elegivel(produto) -> bool:
    """Mesmo filtro do feed: produto ativo com categoria ativa."""
    return bool(produto.ativo and produto.categoria_id and produto.categoria.ativa)


def produto_para_item_meta(produto, site_url: str) -> dict | None:
    """
    Monta o item no formato de campos da Content API / Batch API da Meta.
    Retorna None quando o produto nao tem foto principal (sem imagem o item
    nao pode ser enviado, mesma regra que o feed ja aplicava).
    """
    imagem = produto.imagem_principal
    if not imagem or not getattr(imagem, 'imagem', None):
        return None

    site_url    = (site_url or '').rstrip('/')
    link        = f'{site_url}{produto.get_absolute_url()}'
    image_link  = f'{site_url}{imagem.imagem.url}'
    description = ' '.join(strip_tags(produto.descricao or '').split())

    category_parts = []
    if produto.categoria_id:
        if produto.categoria.parent_id:
            category_parts.append(produto.categoria.parent.nome)
        category_parts.append(produto.categoria.nome)
    product_type = ' > '.join(category_parts)

    variacoes_ativas = [v for v in produto.variacoes.all() if v.ativa]
    color_values = sorted({v.cor.nome for v in variacoes_ativas if v.cor_id})
    size_values  = sorted({v.tamanho.nome for v in variacoes_ativas if v.tamanho_id})

    item = {
        'id':                       str(produto.id),
        'title':                    produto.nome,
        'description':              description[:9999],
        'availability':             'in stock' if produto_disponivel(produto) else 'out of stock',
        'inventory':                produto_quantidade(produto),
        'condition':                'new',
        'price':                    formatar_preco_meta(produto.preco_base_exibicao),
        'link':                     link,
        'image_link':               image_link,
        'brand':                    "D'ELLA Instore",
        'google_product_category':  'Apparel & Accessories > Clothing',
        'product_type':             product_type,
        'gender':                   'female',
        'age_group':                'adult',
        'item_group_id':            str(produto.id),
    }
    if produto.em_promocao:
        item['sale_price'] = formatar_preco_meta(produto.preco_atual)
    if produto.sku:
        item['mpn'] = produto.sku
    if color_values:
        item['color'] = ', '.join(color_values)
    if size_values:
        item['size'] = ', '.join(size_values)
    return item


def enviar_atualizacao_produto_meta(produto):
    """
    Empurra o produto pro catalogo da Meta em tempo real (Batch API).
    Falha silenciosa em log: o feed diario (/feed-meta.xml) continua como
    rede de seguranca caso a Meta esteja fora do ar ou o token expire.
    """
    if not catalogo_configurado():
        logger.debug('Meta catalog: token/catalog_id nao configurado, push ignorado.')
        return

    site_url = getattr(settings, 'SITE_URL', '') or ''
    item = produto_para_item_meta(produto, site_url)
    if item is None:
        logger.debug('Meta catalog: produto %s sem foto principal, push ignorado.', produto.id)
        return

    if not produto_elegivel(produto):
        # Produto inativo ou categoria inativa: mantem o item no catalogo
        # (historico, avaliacoes, facilita reativar) mas marca fora de estoque.
        item['availability'] = 'out of stock'
        item['inventory']    = 0

    _enviar_batch([{'method': 'UPDATE', 'data': item}], produto.id)


def _enviar_batch(requests_payload: list[dict], produto_id: int):
    url = f'{GRAPH_URL}/{settings.META_GRAPH_API_VERSION}/{settings.META_CATALOG_ID}/items_batch'
    try:
        resp = requests.post(
            url,
            data={
                'access_token': settings.META_CATALOG_TOKEN,
                'item_type':    'PRODUCT_ITEM',
                'requests':     json.dumps(requests_payload),
            },
            timeout=TIMEOUT,
        )
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Meta catalog: falha de rede/parse no produto %s: %s', produto_id, exc)
        return

    if resp.status_code != 200 or 'error' in payload:
        logger.warning(
            'Meta catalog: erro ao enviar produto %s (status=%s): %s',
            produto_id, resp.status_code, payload.get('error', payload),
        )
        return

    logger.info('Meta catalog: produto %s enviado (handle=%s).', produto_id, payload.get('handles'))
