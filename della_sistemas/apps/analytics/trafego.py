"""Regra unica de "o que conta como visitante real" no painel do site.

O site_della ja marca `is_bot` na COLETA (User-Agent conhecido, ASN de
datacenter, rajada por IP, rajada global, rajada estrangeira). Esses filtros
sao reativos: dependem de um gatilho de volume disparar no momento em que a
sessao e criada. Scraper que roda devagar, espalhado por muitos IPs
residenciais e por cidades diferentes, nunca aciona nenhum deles.

Medicao em 2026-08-23, 30 dias de trafego ja filtrado por `is_bot`:

    1.728 sessoes ditas humanas
      617 vindas de fora do Brasil (35,7%)
          528 delas com EXATAMENTE 2 paginas, 65 com 1 pagina
            0 adicionaram ao carrinho
            0 chegaram ao checkout
            0 geraram pedido

Nenhum conjunto de pessoas reais se distribui assim. O filtro abaixo roda na
LEITURA (nao na coleta), o que resolve de uma vez tres coisas que o filtro de
coleta nao resolve:

- o residuo historico (sessoes gravadas antes do filtro de 16/08 existir:
  387 sessoes de "Riga" continuam com is_bot=False ate hoje);
- o fluxo lento que escapa dos gatilhos (7 a 10 por dia ainda passam);
- a impossibilidade de reprocessar o passado sem reescrever o banco.

NAO confundir com "todo estrangeiro e robo". A regra exige que TODOS os
sinais de nao-humano estejam presentes ao mesmo tempo; basta um falhar e a
sessao conta normalmente. Uma cliente real fora do Brasil (viajando, morando
fora e enviando para endereco daqui) falha em pelo menos um: ou navega mais
que o limiar, ou chega por campanha/anuncio, ou coloca algo no carrinho.
"""

from django.db.models import Exists, OuterRef, Q

# Siglas de subdivisao que o GeoLite2 devolve para o Brasil. Serve so para
# separar nacional de estrangeiro, nao e validacao de endereco.
UF_BRASIL = frozenset((
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS',
    'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC',
    'SP', 'SE', 'TO',
))

# Ate quantas paginas uma sessao estrangeira pode ter e ainda ser considerada
# sem sinal de navegacao humana. Calibrado sobre a distribuicao real: 96% das
# sessoes estrangeiras param em 1 ou 2 paginas, e so 23 das 617 passam de 3.
LIMIAR_PAGINAS_SCRAPER = 3


def sessoes_reais(qs=None):
    """Mesmo queryset, sem as sessoes de scraper estrangeiro.

    Aceita qualquer queryset de SessaoSite (ja filtrado por periodo, por
    exemplo) e devolve ele filtrado. Sem argumento, parte de todas.
    """
    from apps.analytics.models import EventoSite, SessaoSite

    if qs is None:
        qs = SessaoSite.objects.all()

    def _tem(tipo):
        return Exists(EventoSite.objects.filter(sessao=OuterRef('pk'), tipo=tipo))

    return (
        qs
        .annotate(
            _add_carrinho=_tem('produto_adicionado'),
            _foi_checkout=_tem('checkout_iniciado'),
            _fez_pedido=_tem('pedido_finalizado'),
        )
        .exclude(
            # Fora do Brasil (com geo resolvido: sem cidade/estado nao da para
            # afirmar nada, entao a sessao passa).
            ~Q(estado__in=UF_BRASIL),
            ~Q(estado=''),
            # Nao veio de campanha nem de clique de anuncio.
            utm_source='',
            fbclid='',
            gclid='',
            # Navegacao rasa.
            total_paginas__lte=LIMIAR_PAGINAS_SCRAPER,
            # Trava de seguranca: qualquer intencao de compra preserva a
            # sessao. `_fez_pedido` em particular garante que NENHUMA venda
            # pode sumir do painel por causa deste filtro, em nenhum cenario.
            _add_carrinho=False,
            _foi_checkout=False,
            _fez_pedido=False,
        )
    )


def base_trafego():
    """Universo de sessoes que o painel conta como gente.

    Combina as duas regras, e e o ponto de entrada que as views devem usar:

    1. `is_bot=False`, o filtro da coleta no site_della;
    2. sem o scraper que passa por ele (`sessoes_reais`);
    3. mas SEMPRE incluindo qualquer sessao que gerou pedido, mesmo marcada
       como bot.

    O item 3 existe porque `is_bot` e remarcado retroativamente pelos filtros
    de rajada do site_della (`recentes.filter(is_bot=False).update(is_bot=True)`):
    uma cliente real que compra e, minutos depois, e varrida junto com uma
    rajada do mesmo IP some do painel com a venda dela. Ja aconteceu em
    producao (pedidos 2026-0023 e 2026-0027). Compra concluida e prova
    definitiva de que a sessao e humana, e vence qualquer heuristica.
    """
    from apps.analytics.models import EventoSite, SessaoSite

    tem_pedido = Exists(
        EventoSite.objects.filter(sessao=OuterRef('pk'), tipo='pedido_finalizado')
    )
    qs = (
        SessaoSite.objects
        .annotate(_gerou_pedido=tem_pedido)
        .filter(Q(is_bot=False) | Q(_gerou_pedido=True))
    )
    return sessoes_reais(qs)
