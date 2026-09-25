"""
Feed de produtos para o Google Merchant Center (Shopping).

Diferenca chave em relacao ao feed da Meta (services/meta_catalog.py): o
Google exige um item por OFERTA VENDAVEL (cor+tamanho), nao um item por
produto com cores/tamanhos agrupados numa lista so — o Google rejeita/
penaliza atributo `color`/`size` com varios valores num item so. Aqui cada
Variacao ativa e disponivel vira um item, todos compartilhando o mesmo
`item_group_id` (o id do Produto) para aparecerem agrupados como variantes
no anuncio.

Sob demanda (couro etc, ver Variacao.prazo_confeccao_dias): mapeado como
`availability=backorder` (Google entende como "vendemos, mas demora mais
pra chegar", diferente de simplesmente "in stock") + `min/max_handling_time`
somando o prazo de confeccao ao manuseio padrao — o mesmo prazo que ja soma
no calculo de frete real do checkout (apps/pedidos/views.py:_frete_cep,
`prazo_final = (o['prazo'] or 0) + prazo_adicional`). Assim o Google mostra
o prazo de entrega real dessas pecas sem precisar de uma politica de frete
separada.

O Google exige `availability_date` em todo item `backorder` (sem ela o item
e' reprovado com "Atributo ausente: [availability_date]"). Usamos a data em
que a peca fica pronta pra envio: hoje + prazo de confeccao em dias uteis.
Como o feed e' gerado a cada busca do Google, a data acompanha o dia.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.html import strip_tags

BRAND = "D'ELLA Instore"
GOOGLE_PRODUCT_CATEGORY = 'Apparel & Accessories > Clothing'

# Manuseio padrao (dias) para itens prontos a entrega — some com o prazo de
# transito calculado pela politica de frete cadastrada no Merchant Center.
# Ajustar aqui se a operacao confirmar um numero diferente.
HANDLING_MIN_PADRAO = 0
HANDLING_MAX_PADRAO = 1


def _somar_dias_uteis(data, dias: int):
    while dias > 0:
        data += timedelta(days=1)
        if data.weekday() < 5:
            dias -= 1
    return data


def _availability_date(dias_confeccao: int) -> str:
    """Data ISO 8601 com fuso (ex.: 2026-10-05T00:00:00-03:00)."""
    pronta = _somar_dias_uteis(timezone.localdate(), dias_confeccao)
    dt = timezone.make_aware(datetime.combine(pronta, time.min))
    return dt.isoformat()


def _variacao_elegivel(variacao) -> bool:
    return bool(variacao.ativa and variacao.disponivel)


def variacao_para_item_google(variacao, produto, site_url: str) -> dict | None:
    """Monta um item do feed do Google para uma variacao especifica.
    Retorna None se a variacao nao tiver imagem (Google exige imagem)."""
    cor_id = variacao.cor_id
    imagens_cor = produto.imagens_da_cor(cor_id) if cor_id else []
    imagem = imagens_cor[0] if imagens_cor else produto.imagem_principal
    if not imagem or not getattr(imagem, 'imagem', None):
        return None

    site_url = (site_url or '').rstrip('/')
    link = f'{site_url}{produto.get_absolute_url()}'
    image_link = f'{site_url}{imagem.imagem.url}'
    description = ' '.join(strip_tags(produto.descricao or '').split())

    category_parts = []
    if produto.categoria_id:
        if produto.categoria.parent_id:
            category_parts.append(produto.categoria.parent.nome)
        category_parts.append(produto.categoria.nome)
    product_type = ' > '.join(category_parts)

    titulo = produto.nome
    if variacao.label:
        titulo = f'{produto.nome} - {variacao.label}'

    sob_demanda = variacao.sob_demanda
    item = {
        'id':                       str(variacao.id),
        'title':                    titulo,
        'description':              description[:9999],
        'availability':             'backorder' if sob_demanda else 'in stock',
        'condition':                'new',
        'price':                    f'{variacao.preco_base:.2f} BRL',
        'link':                     link,
        'image_link':               image_link,
        'brand':                    BRAND,
        'google_product_category':  GOOGLE_PRODUCT_CATEGORY,
        'product_type':             product_type,
        'gender':                   'female',
        'age_group':                'adult',
        'item_group_id':            str(produto.id),
    }
    if variacao.em_promocao:
        item['sale_price'] = f'{variacao.preco_atual:.2f} BRL'
    mpn = variacao.sku_variacao or produto.sku
    if mpn:
        item['mpn'] = mpn
    if variacao.cor_id:
        item['color'] = variacao.cor.nome
    if variacao.tamanho_id:
        item['size'] = variacao.tamanho.nome

    if sob_demanda:
        extra = variacao.prazo_total_adicional_dias
        item['min_handling_time'] = HANDLING_MIN_PADRAO + extra
        item['max_handling_time'] = HANDLING_MAX_PADRAO + extra
        item['availability_date'] = _availability_date(extra)

    return item


def produto_para_itens_google(produto, site_url: str) -> list[dict]:
    """Uma variacao ativa/disponivel = um item. Produtos sem variacao
    cadastrada (raro, mas o modelo permite) nao entram no feed do Google —
    o Google exige oferta vendavel identificavel, o produto agregado usado
    no feed da Meta nao serve aqui."""
    itens = []
    for variacao in produto.variacoes.all():
        if not _variacao_elegivel(variacao):
            continue
        item = variacao_para_item_google(variacao, produto, site_url)
        if item is not None:
            itens.append(item)
    return itens
