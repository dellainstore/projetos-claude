"""Numeros de dinheiro do painel Vendas.

Diferenca importante em relacao ao painel Visitas: aqui a fonte da verdade e o
PEDIDO no espelho `PedidoSite`, nao o evento de analytics. O evento serve so
para ligar a venda a origem da sessao que a gerou.

Motivo: o evento `pedido_finalizado` e gravado na criacao do pedido e nao sabe
se o pagamento entrou. O status no pedido sabe. Somar por evento tambem
duplicaria receita quando o pedido gera evento de total e de item (ver a nota
em apps/analytics/vendas.py).

Venda aqui nunca passa por filtro de bot: o status pago ja e prova de que a
compra existe, e a heuristica de bot ja marcou cliente real por engano.
"""

from decimal import Decimal

from django.db.models import Avg, Count, Min, Q, Sum

from apps.analytics.attribution import ORIGENS_PAGAS, label_origem, nome_campanha
from apps.analytics.vendas import STATUS_AGUARDANDO, STATUS_PAGOS


def _pedidos(inicio, fim, status=STATUS_PAGOS):
    from apps.analytics.models import PedidoSite
    return PedidoSite.objects.filter(criado_em__range=(inicio, fim), status__in=status)


def resumo(inicio, fim):
    """Cards do topo do painel Vendas."""
    from apps.analytics.models import EventoSite
    from apps.analytics.vendas import eventos_itens

    pagos = _pedidos(inicio, fim)
    agg = pagos.aggregate(vendas=Count('id'), receita=Sum('total'), ticket=Avg('total'))

    aguardando = _pedidos(inicio, fim, STATUS_AGUARDANDO).aggregate(
        n=Count('id'), valor=Sum('total')
    )

    itens = eventos_itens(
        Q(ocorrido_em__range=(inicio, fim))
    ).aggregate(t=Sum('quantidade'))['t'] or 0

    return {
        'vendas': agg['vendas'] or 0,
        'receita': agg['receita'] or Decimal('0'),
        'ticket': agg['ticket'] or Decimal('0'),
        'itens': itens,
        'aguardando': aguardando['n'] or 0,
        'aguardando_valor': aguardando['valor'] or Decimal('0'),
    }


def _origem_por_pedido(inicio, fim):
    """{numero_do_pedido: rotulo de origem}, da sessao que gerou a venda.

    A sessao e a fonte principal porque o pedido so passou a guardar a
    atribuicao de forma confiavel em 2026-08-23; antes disso o cookie do
    Safari expirava antes da compra e o pedido chegava sem UTM nenhuma.
    Quando a sessao tambem nao sabe, cai para o que estiver no pedido.
    """
    from apps.analytics.models import EventoSite, PedidoSite

    por_numero = {}
    eventos = (
        EventoSite.objects
        .filter(ocorrido_em__range=(inicio, fim), tipo='pedido_finalizado',
                produto_slug='', pedido_numero__gt='')
        .values('pedido_numero', 'sessao__utm_source', 'sessao__utm_medium',
                'sessao__utm_campaign', 'sessao__fbclid', 'sessao__gclid')
    )
    for ev in eventos:
        por_numero[ev['pedido_numero']] = {
            'origem': label_origem(
                ev['sessao__utm_source'], bool(ev['sessao__fbclid']),
                bool(ev['sessao__gclid']), ev['sessao__utm_medium'],
            ),
            'campanha': nome_campanha(ev['sessao__utm_campaign']),
        }

    # Pedido sem evento de analytics (compra fora do fluxo normal do site).
    faltando = _pedidos(inicio, fim).exclude(numero__in=por_numero.keys())
    for p in faltando.values('numero', 'utm_source', 'utm_medium', 'utm_campaign',
                             'fbclid', 'gclid'):
        por_numero[p['numero']] = {
            'origem': label_origem(p['utm_source'], bool(p['fbclid']),
                                   bool(p['gclid']), p['utm_medium']),
            'campanha': nome_campanha(p['utm_campaign']),
        }
    return por_numero


def por_origem(inicio, fim):
    """Faturamento, vendas e ticket por origem."""
    atrib = _origem_por_pedido(inicio, fim)
    agg: dict = {}
    for p in _pedidos(inicio, fim).values('numero', 'total'):
        rotulo = atrib.get(p['numero'], {}).get('origem', 'Direto ou busca')
        item = agg.setdefault(rotulo, {'origem': rotulo, 'vendas': 0,
                                       'receita': Decimal('0')})
        item['vendas'] += 1
        item['receita'] += p['total'] or Decimal('0')

    total = sum(i['receita'] for i in agg.values()) or Decimal('1')
    linhas = []
    for item in agg.values():
        item['ticket'] = item['receita'] / item['vendas'] if item['vendas'] else Decimal('0')
        item['pct'] = round(float(item['receita']) / float(total) * 100)
        item['paga'] = item['origem'] in ORIGENS_PAGAS
        linhas.append(item)
    return sorted(linhas, key=lambda i: -i['receita'])


def por_campanha(inicio, fim):
    """Faturamento por campanha, com o nome ja decodificado e legivel."""
    atrib = _origem_por_pedido(inicio, fim)
    agg: dict = {}
    for p in _pedidos(inicio, fim).values('numero', 'total'):
        dados = atrib.get(p['numero'], {})
        nome = dados.get('campanha') or ''
        if not nome:
            continue
        item = agg.setdefault(nome, {'campanha': nome, 'vendas': 0,
                                     'receita': Decimal('0'),
                                     'origem': dados.get('origem', '')})
        item['vendas'] += 1
        item['receita'] += p['total'] or Decimal('0')
    for item in agg.values():
        item['ticket'] = item['receita'] / item['vendas'] if item['vendas'] else Decimal('0')
    return sorted(agg.values(), key=lambda i: -i['receita'])


def qualidade_atribuicao(inicio, fim):
    """Quanto do faturamento tem origem conhecida.

    Serve de alarme: se despencar, e sinal de etiqueta quebrada no anuncio, e
    nao de mudanca de comportamento da cliente.
    """
    atrib = _origem_por_pedido(inicio, fim)
    com = sem = Decimal('0')
    n_com = n_sem = 0
    for p in _pedidos(inicio, fim).values('numero', 'total'):
        valor = p['total'] or Decimal('0')
        if atrib.get(p['numero'], {}).get('origem', 'Direto ou busca') == 'Direto ou busca':
            sem += valor
            n_sem += 1
        else:
            com += valor
            n_com += 1
    total = com + sem
    return {
        'com_origem': n_com, 'sem_origem': n_sem,
        'receita_com': com, 'receita_sem': sem,
        'pct': round(float(com) / float(total) * 100) if total else 0,
    }


def novos_x_recorrentes(inicio, fim):
    """Quantas compras vieram de quem ja tinha comprado antes.

    Casa por e-mail e nao pelo FK de cliente: compra de convidada (checkout sem
    cadastro) nao tem cliente vinculado, e ignorar essas compras subestimaria a
    recorrencia real.
    """
    from apps.analytics.models import PedidoSite

    pedidos = list(_pedidos(inicio, fim).values('email', 'criado_em'))
    if not pedidos:
        return {'novos': 0, 'recorrentes': 0}

    emails = {p['email'] for p in pedidos if p['email']}
    primeira_compra = {}
    for linha in (
        PedidoSite.objects
        .filter(email__in=emails, status__in=STATUS_PAGOS)
        .values('email')
        .annotate(primeira=Min('criado_em'))
    ):
        primeira_compra[linha['email']] = linha['primeira']

    novos = recorrentes = 0
    for p in pedidos:
        primeira = primeira_compra.get(p['email'])
        # Comparado com a data DO PEDIDO, nao com o inicio do periodo: quem
        # comprou duas vezes dentro do proprio periodo tem a segunda compra
        # como recorrente. Comparando com `inicio`, as duas compras da mesma
        # cliente contavam como "nova" (caso real: Anna Gontijo, pedidos
        # 2026-0025 e 2026-0026).
        if primeira and primeira < p['criado_em']:
            recorrentes += 1
        else:
            novos += 1
    return {'novos': novos, 'recorrentes': recorrentes}


def ultimos_pedidos(inicio, fim, limite=15):
    """Pedidos recentes com a origem de cada um."""
    atrib = _origem_por_pedido(inicio, fim)
    linhas = []
    for p in (_pedidos(inicio, fim)
              .order_by('-criado_em')
              .values('numero', 'nome_completo', 'total', 'criado_em', 'status')[:limite]):
        dados = atrib.get(p['numero'], {})
        linhas.append({
            'numero': p['numero'],
            'cliente': p['nome_completo'] or 'Cliente',
            'total': p['total'],
            'criado_em': p['criado_em'],
            'status': p['status'],
            'origem': dados.get('origem', 'Direto ou busca'),
            'campanha': dados.get('campanha', ''),
        })
    return linhas
