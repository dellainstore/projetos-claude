"""De onde vem a visita e quanto cada origem realmente rende.

Este cruzamento nao existia em nenhum dos dois paineis antigos, e era o
principal motivo de nao dar para decidir verba:

- o "Marketing e Atribuicao" do site_della sabia que o anuncio vendeu 3 vezes,
  mas nao quantas pessoas ele trouxe;
- o "Analytics do Site" sabia que o anuncio trouxe 491 pessoas, mas nao quanto
  elas compraram.

Ninguem cruzava os dois, entao ninguem sabia que aquele anuncio converte 0,61%.
"""

from django.db.models import BooleanField, Case, Count, Exists, OuterRef, Sum, Value, When

from apps.analytics.attribution import ORIGENS_PAGAS, label_origem


def _por_sessao(sessoes_qs):
    """Agrupa as sessoes do periodo por origem legivel."""
    from apps.analytics.models import EventoSite
    from apps.analytics.vendas import numeros_pagos

    venda_paga = EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='pedido_finalizado',
        produto_slug='', pedido_numero__in=numeros_pagos(),
    )

    linhas = (
        sessoes_qs
        .annotate(
            tem_fbclid=Case(When(fbclid='', then=Value(False)),
                            default=Value(True), output_field=BooleanField()),
            tem_gclid=Case(When(gclid='', then=Value(False)),
                           default=Value(True), output_field=BooleanField()),
            vendeu=Exists(venda_paga),
        )
        .values('utm_source', 'utm_medium', 'tem_fbclid', 'tem_gclid', 'vendeu')
        .annotate(total=Count('id'))
    )

    agg: dict = {}
    for linha in linhas:
        rotulo = label_origem(linha['utm_source'], linha['tem_fbclid'],
                              linha['tem_gclid'], linha['utm_medium'])
        item = agg.setdefault(rotulo, {'origem': rotulo, 'visitantes': 0, 'vendas': 0})
        item['visitantes'] += linha['total']
        if linha['vendeu']:
            item['vendas'] += linha['total']
    return agg


def _receita_por_origem(inicio, fim):
    """Receita paga do periodo, atribuida a origem da sessao que gerou a venda."""
    from apps.analytics.models import EventoSite
    from apps.analytics.vendas import numeros_pagos

    linhas = (
        EventoSite.objects
        .filter(ocorrido_em__range=(inicio, fim), tipo='pedido_finalizado',
                produto_slug='', pedido_numero__in=numeros_pagos())
        .annotate(
            tem_fbclid=Case(When(sessao__fbclid='', then=Value(False)),
                            default=Value(True), output_field=BooleanField()),
            tem_gclid=Case(When(sessao__gclid='', then=Value(False)),
                           default=Value(True), output_field=BooleanField()),
        )
        .values('sessao__utm_source', 'sessao__utm_medium', 'tem_fbclid', 'tem_gclid')
        .annotate(receita=Sum('valor_total'), pedidos=Count('pedido_numero', distinct=True))
    )

    agg: dict = {}
    for linha in linhas:
        rotulo = label_origem(linha['sessao__utm_source'], linha['tem_fbclid'],
                              linha['tem_gclid'], linha['sessao__utm_medium'])
        item = agg.setdefault(rotulo, {'receita': 0, 'pedidos': 0})
        item['receita'] += linha['receita'] or 0
        item['pedidos'] += linha['pedidos']
    return agg


def origens_com_retorno(sessoes_qs, inicio, fim):
    """Uma linha por origem: visitantes, vendas, receita e conversao.

    `sessoes_qs` ja vem filtrado por periodo e por trafego real.
    """
    agg = _por_sessao(sessoes_qs)
    receitas = _receita_por_origem(inicio, fim)

    for rotulo, dados in receitas.items():
        item = agg.setdefault(rotulo, {'origem': rotulo, 'visitantes': 0, 'vendas': 0})
        item['receita'] = dados['receita']
        # A venda pode ter vindo de sessao iniciada antes do periodo; nesse
        # caso o contador por sessao nao a viu, mas a receita existe.
        item['vendas'] = max(item['vendas'], dados['pedidos'])

    total_visitantes = sum(i['visitantes'] for i in agg.values()) or 1
    linhas = []
    for item in agg.values():
        item.setdefault('receita', 0)
        visitantes = item['visitantes']
        item['conversao'] = round(item['vendas'] / visitantes * 100, 2) if visitantes else 0
        item['pct_visitantes'] = round(visitantes / total_visitantes * 100, 1)
        item['paga'] = item['origem'] in ORIGENS_PAGAS
        linhas.append(item)

    return sorted(linhas, key=lambda i: (-i['visitantes'], i['origem']))
