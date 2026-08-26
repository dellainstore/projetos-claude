"""Calculos compartilhados pelos paineis Visitas e Vendas e pelo PDF semanal.

Ficavam em views/dashboard.py, junto da tela antiga "Analytics do Site".
Quando essa tela saiu, as funcoes vieram para ca: nao sao views, e os dois
paineis novos mais o relatorio semanal dependem delas.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone



def _db_disponivel():
    return 'della_site' in settings.DATABASES


def _resolver_periodo(request, corte_bot=True):
    """Resolve o periodo (filtro, inicio, fim) a partir da querystring.

    `corte_bot=True` (padrao) empurra `inicio` para nao passar de antes de
    28/06/2026 -- corte de remocao de bots/scans do trafego (ver
    `apps/analytics/constants.py`). O painel Vendas chama com
    `corte_bot=False`: venda paga e um pedido real, nunca poluicao de bot, e
    aplicar o corte aqui escondia vendas legitimas de maio/junho (pedidos
    2026-0001 a 2026-0007) mesmo com um periodo customizado cobrindo essas
    datas -- ver a mesma regra em apps/analytics/faturamento.py.
    """
    from datetime import datetime as dt
    filtro = request.GET.get('periodo', '7d')
    agora = timezone.now()
    # "Hoje" deve comecar a 00:00 no horario de Sao Paulo, nao em UTC. Sem a
    # conversao com localtime() o inicio cai as 21:00 do dia anterior (BRT),
    # fazendo o filtro "hoje" englobar o fim da noite de ontem e ficar quase
    # identico ao "7 dias" quando o trafego se concentra na virada do dia.
    hoje_inicio = timezone.localtime(agora).replace(hour=0, minute=0, second=0, microsecond=0)

    de_val = request.GET.get('de', '')
    ate_val = request.GET.get('ate', '')

    if filtro == 'hoje':
        inicio = hoje_inicio
        fim = agora
    elif filtro == 'ontem':
        inicio = hoje_inicio - timedelta(days=1)
        fim = hoje_inicio - timedelta(microseconds=1)
    elif filtro == '30d':
        # Dia de calendario (30 dias contando hoje), nao 30x24h para tras. Ver
        # a nota sobre a janela de "7d" no bloco final desta funcao.
        inicio = hoje_inicio - timedelta(days=29)
        fim = agora
    elif filtro == 'mes_atual':
        inicio = hoje_inicio.replace(day=1)
        fim = agora
    elif filtro == 'mes_passado':
        primeiro_dia_atual = hoje_inicio.replace(day=1)
        # Ultimo instante do mes passado, arredondado para 23:59:59 (nao
        # microssegundo) para o `date.max.time()` do filtro custom bater igual.
        fim = primeiro_dia_atual - timedelta(seconds=1)
        inicio = fim.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif filtro == 'custom' and de_val and ate_val:
        try:
            de_date = dt.strptime(de_val, '%Y-%m-%d').date()
            ate_date = dt.strptime(ate_val, '%Y-%m-%d').date()
            if ate_date < de_date:
                ate_date = de_date
            inicio = timezone.make_aware(dt.combine(de_date, dt.min.time()))
            fim = timezone.make_aware(
                dt.combine(ate_date, dt.max.time().replace(microsecond=0))
            )
        except (ValueError, TypeError):
            filtro = '7d'
            inicio = hoje_inicio - timedelta(days=6)
            fim = agora
            de_val = ate_val = ''
    else:
        # "Ultimos 7 dias" = 7 dias de CALENDARIO contando hoje (hoje-6 as 00:00
        # ate agora), no fuso de Sao Paulo. Antes era uma janela rolante de
        # 7x24h para tras, o que fazia o painel divergir do "Marketing e
        # Atribuicao" do site_della (que sempre usou calendario) por 1 pedido
        # inteiro dependendo da hora da consulta: em 2026-08-23 o site contava
        # 3 vendas e este painel 4, ambos "corretos" para a propria definicao.
        filtro = '7d'
        inicio = hoje_inicio - timedelta(days=6)
        fim = agora

    if corte_bot:
        # Oculta dados anteriores ao corte (28/06/2026 — remoção de bots/scans).
        from apps.analytics.constants import inicio_corte_aware
        corte = inicio_corte_aware()
        if inicio < corte:
            inicio = corte

    return filtro, inicio, fim, de_val, ate_val


def _calcular_ao_vivo():
    from apps.analytics.models import SessaoSite, EventoSite

    agora = timezone.now()
    corte = agora - timedelta(minutes=5)

    from apps.analytics.trafego import base_trafego
    vivos = base_trafego().filter(ultima_acao_em__gte=corte)
    visitantes = vivos.count()

    # Pagina atual de cada sessao ativa = pagina_url do evento de navegacao mais
    # recente (pagina_vista, produto_visualizado ou lista_visualizada). Usar so
    # 'pagina_vista' deixava a lista VAZIA quando o evento mais recente da sessao
    # era um produto_visualizado (PDP) -- por isso o contador subia mas nenhuma
    # pagina aparecia. Conta visitantes distintos por URL (nao numero de eventos).
    TIPOS_NAV = ('pagina_vista', 'produto_visualizado', 'lista_visualizada')
    eventos = (
        EventoSite.objects
        .filter(sessao__in=vivos, tipo__in=TIPOS_NAV,
                ocorrido_em__gte=corte, pagina_url__gt='')
        .order_by('sessao_id', '-ocorrido_em')
        .values('sessao_id', 'pagina_url')
    )
    atual_por_sessao = {}
    for ev in eventos:
        atual_por_sessao.setdefault(ev['sessao_id'], ev['pagina_url'])  # 1o = mais recente

    contagem = {}
    for url in atual_por_sessao.values():
        contagem[url] = contagem.get(url, 0) + 1
    paginas = [
        {'pagina_url': url, 'total': total}
        for url, total in sorted(contagem.items(), key=lambda x: -x[1])[:5]
    ]

    # Cidades dos visitantes ao vivo (aproximado via IP, resolvido no site_della
    # no momento da visita -- aqui so lemos cidade/estado ja gravados).
    contagem_cidade = {}
    for cidade, estado in vivos.exclude(cidade='').values_list('cidade', 'estado'):
        label = f'{cidade}/{estado}' if estado else cidade
        contagem_cidade[label] = contagem_cidade.get(label, 0) + 1
    cidades = [
        {'cidade': label, 'total': total}
        for label, total in sorted(contagem_cidade.items(), key=lambda x: -x[1])[:5]
    ]

    return {'visitantes': visitantes, 'paginas': paginas, 'cidades': cidades}


def _calcular_resumo(inicio, fim):
    from apps.analytics.models import SessaoSite, EventoSite
    from apps.analytics.vendas import (
        STATUS_AGUARDANDO, eventos_itens, eventos_pedidos, sessoes_com_venda_paga,
        ids_com_carrinho_liquido_positivo,
    )
    from django.db.models import Exists, OuterRef

    from apps.analytics.trafego import base_trafego

    # TRAFEGO: alem do is_bot marcado na coleta, tira o scraper que passa por
    # ele (ver apps/analytics/trafego.py).
    reais_ids = base_trafego().values('pk')
    periodo = Q(ocorrido_em__range=(inicio, fim), sessao__in=reais_ids)

    visitas    = EventoSite.objects.filter(periodo, tipo='pagina_vista').count()
    # Visitante do periodo = quem teve ATIVIDADE no periodo, nao quem criou a
    # sessao nele. A sessao aqui vive ate 30 dias (SESSION_COOKIE_AGE), entao
    # contar por `iniciada_em` respondia "quantos cookies novos nasceram", nao
    # "quanta gente visitou": quem voltou ao site com o cookie da semana
    # passada gerava paginas contadas em `visitas` sem existir no denominador.
    # Alem de inflar a media de paginas e a taxa de conversao, isso punha dois
    # numeros diferentes de visitante na mesma tela (o card dizia 209 e o funil
    # ao lado 298, medido em 2026-08-23). Mesmo criterio do funil agora.
    visitantes = (
        EventoSite.objects.filter(periodo).values('sessao_id').distinct().count()
    )

    # VENDA: dinheiro que entrou nunca passa por filtro de bot. A heuristica de
    # bot e probabilistica e ja marcou cliente real por engano mais de uma vez
    # (pedidos 2026-0023 e 2026-0027, corrigidos no site_della em 2026-08-17);
    # o status do pedido no espelho `PedidoSite` ja e prova suficiente de que a
    # venda existe. Sem `sessao__is_bot` aqui, uma sessao marcada como bot
    # DEPOIS da compra (o filtro de rajada remarca irmas retroativamente) nao
    # consegue mais apagar a venda do painel.
    periodo_venda = Q(ocorrido_em__range=(inicio, fim))

    # Venda = pedido PAGO. Pedido gerado e ainda sem pagamento entra em
    # "aguardando pagamento"; cancelado/estornado nao entra em nada.
    pagos_qs = eventos_pedidos(periodo_venda)
    pedidos = pagos_qs.values('pedido_numero').distinct().count()
    receita = pagos_qs.aggregate(total=Sum('valor_total'))['total'] or 0
    itens_vendidos = eventos_itens(periodo_venda).aggregate(total=Sum('quantidade'))['total'] or 0

    aguardando_qs = eventos_pedidos(periodo_venda, status=STATUS_AGUARDANDO)
    aguardando = aguardando_qs.values('pedido_numero').distinct().count()
    aguardando_valor = aguardando_qs.aggregate(total=Sum('valor_total'))['total'] or 0

    # Abandonado = nao gerou venda PAGA. Sessao com pedido aguardando pagamento
    # continua contando como abandonada ate o pagamento entrar (mesma regra do
    # carrinho abandonado no site_della, que so vira "recuperado" quando pago).
    #
    # Ancorado no EVENTO ocorrido na janela, nao na sessao iniciada na janela.
    # A sessao vive ate 30 dias (SESSION_COOKIE_AGE), entao quem comecou a
    # navegar antes do inicio do periodo e so abandonou o carrinho dentro dele
    # ficava fora desta conta enquanto aparecia normalmente no funil ao lado.
    # Era o que produzia "3 no checkout" embaixo de um funil mostrando 4 vendas
    # pagas na mesma tela (medido em 2026-08-23).
    comprou_qs = sessoes_com_venda_paga()
    nao_comprou = ~Exists(comprou_qs)

    def _sessoes_com_evento(tipo):
        ids = (
            EventoSite.objects
            .filter(periodo, tipo=tipo)
            .values_list('sessao_id', flat=True).distinct()
        )
        return SessaoSite.objects.filter(pk__in=ids).filter(nao_comprou)

    # So conta quem ainda tem algo no carrinho: quem adicionou e removeu tudo
    # antes de sair nao e um carrinho abandonado (ver vendas.py).
    candidatos_carrinho = _sessoes_com_evento('produto_adicionado').values_list('id', flat=True)
    carrinhos_abandonados = len(ids_com_carrinho_liquido_positivo(candidatos_carrinho))
    checkouts_abandonados = _sessoes_com_evento('checkout_iniciado').count()

    taxa = round(pedidos / visitantes * 100, 1) if visitantes > 0 else 0
    media_paginas = round(visitas / visitantes, 1) if visitantes > 0 else 0

    return {
        'visitas': visitas,
        'visitantes': visitantes,
        'pedidos': pedidos,
        'aguardando': aguardando,
        'aguardando_valor': aguardando_valor,
        'receita': receita,
        'itens_vendidos': itens_vendidos,
        'carrinhos_abandonados': carrinhos_abandonados,
        'checkouts_abandonados': checkouts_abandonados,
        'taxa': taxa,
        'media_paginas': media_paginas,
    }


def _calcular_funil(inicio, fim):
    from apps.analytics.models import SessaoSite, EventoSite
    from apps.analytics.trafego import base_trafego
    from apps.analytics.vendas import eventos_pedidos

    reais_ids = base_trafego().values('pk')
    periodo = Q(ocorrido_em__range=(inicio, fim), sessao__in=reais_ids)

    # Todas as 6 etapas contam sobre o MESMO universo: sessao com atividade
    # dentro da janela. Antes, so esta primeira etapa contava por
    # `iniciada_em`, entao quem comecou a navegar antes do periodo e comprou
    # dentro dele aparecia nas etapas de baixo sem estar no topo -- o funil
    # chegava a mostrar uma etapa com mais gente que a anterior.
    visitantes = (
        EventoSite.objects
        .filter(periodo)
        .values('sessao_id').distinct().count()
    )
    viram = (
        EventoSite.objects
        .filter(periodo, tipo='produto_visualizado')
        .values('sessao_id').distinct().count()
    )
    adicionaram = (
        EventoSite.objects
        .filter(periodo, tipo='produto_adicionado')
        .values('sessao_id').distinct().count()
    )
    checkout = (
        EventoSite.objects
        .filter(periodo, tipo='checkout_iniciado')
        .values('sessao_id').distinct().count()
    )
    # Duas etapas finais: gerar o pedido nao e o mesmo que pagar. A diferenca
    # entre elas e exatamente o PIX gerado e nao pago / cartao recusado.
    fecharam = (
        EventoSite.objects
        .filter(periodo, tipo='pedido_finalizado', produto_slug='', pedido_numero__gt='')
        .values('sessao_id').distinct().count()
    )
    compraram = eventos_pedidos(periodo).values('sessao_id').distinct().count()

    base = visitantes or 1

    def pct(n):
        return round(n / base * 100, 1)

    etapas = [
        {'label': 'Entraram no site',          'total': visitantes, 'pct': 100.0},
        {'label': 'Viram um produto',           'total': viram,      'pct': pct(viram)},
        {'label': 'Adicionaram ao carrinho',    'total': adicionaram,'pct': pct(adicionaram)},
        {'label': 'Foram ao checkout',          'total': checkout,   'pct': pct(checkout)},
        {'label': 'Fecharam o pedido',          'total': fecharam,   'pct': pct(fecharam)},
        {'label': 'Pagaram (venda)',            'total': compraram,  'pct': pct(compraram)},
    ]
    for i, e in enumerate(etapas):
        if i + 1 < len(etapas):
            e['queda'] = e['total'] - etapas[i + 1]['total']
        else:
            e['queda'] = 0
    return etapas


def _calcular_produtos(inicio, fim):
    from apps.analytics.models import EventoSite
    from apps.analytics.vendas import eventos_itens

    from apps.analytics.trafego import base_trafego

    periodo = Q(ocorrido_em__range=(inicio, fim), sessao__in=base_trafego().values('pk'))

    mais_vistos = list(
        EventoSite.objects
        .filter(periodo, tipo='produto_visualizado', produto_slug__gt='')
        .values('produto_slug', 'produto_nome')
        .annotate(total=Count('id'))
        .order_by('-total')[:25]
    )
    mais_adicionados = list(
        EventoSite.objects
        .filter(periodo, tipo='produto_adicionado', produto_slug__gt='')
        .values('produto_slug', 'produto_nome')
        .annotate(total=Count('id'))
        .order_by('-total')[:25]
    )
    # So itens de pedidos pagos (ver apps/analytics/vendas.py).
    mais_vendidos = list(
        eventos_itens(periodo)
        .values('produto_slug', 'produto_nome')
        .annotate(total=Count('id'), receita=Sum('valor_total'))
        .order_by('-total')[:25]
    )

    return {
        'mais_vistos': mais_vistos,
        'mais_adicionados': mais_adicionados,
        'mais_vendidos': mais_vendidos,
    }


def _calcular_carrinhos_recentes(inicio, fim):
    from apps.analytics.models import SessaoSite, EventoSite
    from apps.analytics.trafego import base_trafego
    from apps.analytics.vendas import (
        sessoes_com_pedido_pendente, sessoes_com_venda_paga,
    )
    from apps.analytics.vendas import numeros_pagos
    from django.db.models import Exists, OuterRef, Subquery
    from django.db.models.functions import Coalesce

    # "Comprou" so quando o pedido foi pago; pedido gerado e nao pago aparece
    # como "Aguardando pagamento".
    comprou_qs = sessoes_com_venda_paga()
    aguardando_qs = sessoes_com_pedido_pendente()
    checkout_qs = EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='checkout_iniciado'
    )
    popup_qs = EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='popup_saida_exibido'
    )

    # Data que a linha realmente descreve, e nao `ultima_acao_em`.
    #
    # A sessao vive ate 30 dias (SESSION_COOKIE_AGE), entao `ultima_acao_em` e
    # so "a ultima vez que essa pessoa mexeu no site", que pode ser dias depois
    # do que a linha esta contando. Na pratica: a cliente do pedido 2026-0030
    # comprou em 22/08 20h17 e voltou a navegar em 23/08 16h16; a linha dizia
    # "23/08 16h16 / Comprou", como se a venda fosse de hoje.
    #
    # Agora a coluna mostra a hora do evento da propria linha: a compra, quando
    # houve compra; senao, a ultima vez que algo entrou no carrinho.
    def _ultimo(**filtros):
        return Subquery(
            EventoSite.objects
            .filter(sessao=OuterRef('pk'), **filtros)
            .order_by('-ocorrido_em')
            .values('ocorrido_em')[:1]
        )

    momento_compra = _ultimo(tipo='pedido_finalizado', produto_slug='',
                             pedido_numero__in=numeros_pagos())
    momento_carrinho = _ultimo(tipo='produto_adicionado')

    # Ancorado no evento dentro da janela (mesmo criterio do resumo e do funil),
    # nao em `iniciada_em`: quem comecou a navegar antes do periodo e so mexeu
    # no carrinho dentro dele pertence a esta lista.
    ids_no_periodo = (
        EventoSite.objects
        .filter(Q(ocorrido_em__range=(inicio, fim)), tipo='produto_adicionado')
        .values_list('sessao_id', flat=True).distinct()
    )
    sessoes = list(
        base_trafego()
        .filter(pk__in=ids_no_periodo)
        .annotate(
            comprou=Exists(comprou_qs),
            aguardando=Exists(aguardando_qs),
            foi_checkout=Exists(checkout_qs),
            viu_popup=Exists(popup_qs),
            momento=Coalesce(momento_compra, momento_carrinho, 'ultima_acao_em'),
        )
        .order_by('-momento')
        .values('id', 'comprou', 'aguardando', 'foi_checkout', 'viu_popup',
                'momento')[:60]
    )

    if not sessoes:
        return []

    session_ids = [s['id'] for s in sessoes]
    # Carrinho liquido: soma adicoes e desconta remocoes (produto_removido nao
    # carrega quantidade/valor, so casa pela linha via produto_nome -- o
    # produto_removido do site nao grava produto_slug, ver bug corrigido em
    # apps/pedidos/carrinho.py:Carrinho.adicionar do site_della). Sem isso, uma
    # sessao que adicionou e removeu itens antes de finalizar aparecia com o
    # carrinho bruto (tudo que ja passou pelo carrinho), inflando itens/valor
    # mesmo com "Comprou" certo (ex: pedido 2026-0010 -- 4 adicoes/2 remocoes
    # na sessao, comprou so 2).
    items_map: dict = {}
    for evt in (
        EventoSite.objects
        .filter(sessao_id__in=session_ids, tipo__in=['produto_adicionado', 'produto_removido'])
        .values('sessao_id', 'tipo', 'produto_nome', 'quantidade', 'valor_total')
        .order_by('ocorrido_em')
    ):
        sid = evt['sessao_id']
        carrinho = items_map.setdefault(sid, {})
        chave = evt['produto_nome'] or ''
        if evt['tipo'] == 'produto_adicionado':
            item = carrinho.setdefault(chave, {
                'nome': (evt['produto_nome'] or 'Produto')[:45], 'qtd': 0, 'valor': 0,
            })
            item['qtd'] += evt['quantidade'] or 1
            item['valor'] += evt['valor_total'] or 0
        else:
            carrinho.pop(chave, None)

    result = []
    for s in sessoes:
        itens = list(items_map.get(s['id'], {}).values())
        total_itens = sum(i['qtd'] for i in itens)
        if total_itens == 0:
            # Adicionou e removeu tudo antes de sair: carrinho esvaziado, nao
            # e um carrinho abandonado (ver ids_com_carrinho_liquido_positivo
            # em apps/analytics/vendas.py, mesma regra aplicada no resumo).
            continue
        valor_total = sum(i['valor'] for i in itens)
        result.append({
            'ultima_acao': s['momento'],
            'comprou': s['comprou'],
            'aguardando': s['aguardando'] and not s['comprou'],
            'foi_checkout': s['foi_checkout'],
            'viu_popup': s['viu_popup'],
            'itens': itens,
            'total_itens': total_itens,
            'valor_total': valor_total,
        })
    return result


def _segunda_da_semana(request):
    """Segunda-feira (date) da semana selecionada no grafico.

    `?semana=YYYY-MM-DD` (qualquer dia da semana, encaixado na segunda). Sem o
    parametro: semana atual. Nunca deixa avancar para uma semana futura."""
    from datetime import datetime as _dt
    hoje = timezone.localdate()
    seg_atual = hoje - timedelta(days=hoje.weekday())
    val = request.GET.get('semana', '')
    if val:
        try:
            d = _dt.strptime(val, '%Y-%m-%d').date()
            seg = d - timedelta(days=d.weekday())
            return min(seg, seg_atual)  # bloqueia semana futura
        except (ValueError, TypeError):
            pass
    return seg_atual


def _calcular_trafico_semanal(seg_semana):
    """Trafego da semana ancorada (Seg a Dom), por data real, comparando com a
    semana anterior. Dias que ainda nao aconteceram ficam vazios (None)."""
    from datetime import datetime as _dt
    from apps.analytics.models import EventoSite
    from apps.analytics.constants import inicio_corte_aware
    from apps.analytics.trafego import base_trafego
    from django.db.models import Count
    from django.db.models.functions import ExtractHour, TruncDate

    _reais = base_trafego().values('pk')

    NOMES = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
    NOMES_FULL = ['Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado', 'Domingo']
    HORAS = [f'{h:02d}h' for h in range(24)]
    hoje = timezone.localdate()
    corte = inicio_corte_aware()

    def _serie(seg):
        ini = timezone.make_aware(_dt.combine(seg, _dt.min.time()))
        fim = timezone.make_aware(
            _dt.combine(seg + timedelta(days=6), _dt.max.time().replace(microsecond=0))
        )
        if ini < corte:
            ini = corte
        raw = dict(
            EventoSite.objects
            .filter(ocorrido_em__range=(ini, fim), tipo='pagina_vista', sessao__in=_reais)
            .annotate(d=TruncDate('ocorrido_em')).values('d')
            .annotate(t=Count('id')).values_list('d', 't')
        )
        dias = [0] * 7
        for d, t in raw.items():
            dias[d.weekday()] += t  # weekday(): Seg=0 .. Dom=6
        return dias, ini, fim

    por_dia, ini, fim = _serie(seg_semana)
    por_dia_anterior, _, _ = _serie(seg_semana - timedelta(days=7))

    # Detalhe por hora (para o clique no dia) -- so da semana selecionada
    por_dia_hora = [[0] * 24 for _ in range(7)]
    for (d, h, t) in (
        EventoSite.objects
        .filter(ocorrido_em__range=(ini, fim), tipo='pagina_vista', sessao__in=_reais)
        .annotate(d=TruncDate('ocorrido_em'), h=ExtractHour('ocorrido_em'))
        .values('d', 'h').annotate(t=Count('id')).values_list('d', 'h', 't')
    ):
        por_dia_hora[d.weekday()][h] += t

    # Dias que ainda nao aconteceram nesta semana -> vazios no grafico
    datas = [seg_semana + timedelta(days=i) for i in range(7)]
    futuros = {i for i, dd in enumerate(datas) if dd > hoje}
    por_dia_exib = [None if i in futuros else por_dia[i] for i in range(7)]

    realizados = [(i, por_dia[i]) for i in range(7) if i not in futuros and por_dia[i] > 0]
    pico_dia_idx = max(realizados, key=lambda x: x[1])[0] if realizados else None
    menor_dia_idx = min(realizados, key=lambda x: x[1])[0] if realizados else None
    hora_agg = [sum(por_dia_hora[d][h] for d in range(7)) for h in range(24)]
    pico_hora = hora_agg.index(max(hora_agg)) if any(hora_agg) else None

    # Comparacao com a semana anterior.
    #
    # Com a semana em curso, o trecho comparavel vai ate o MESMO INSTANTE da
    # semana anterior, e nao ate o fim do mesmo dia. Comparar por dia inteiro
    # faz a segunda de madrugada (4 minutos de semana) ser confrontada com a
    # segunda inteira da semana passada: dava "-100%" em vermelho toda semana,
    # um alarme falso que aparecia justamente quando nao havia o que analisar.
    em_curso = seg_semana <= hoje <= seg_semana + timedelta(days=6)
    comparacao_parcial = False
    if em_curso:
        agora = timezone.localtime(timezone.now())
        decorrido = agora - timezone.make_aware(_dt.combine(seg_semana, _dt.min.time()))
        n = (hoje - seg_semana).days + 1
        total_atual = sum(por_dia[:n])

        seg_anterior = seg_semana - timedelta(days=7)
        ini_ant = timezone.make_aware(_dt.combine(seg_anterior, _dt.min.time()))
        if ini_ant < corte:
            ini_ant = corte
        total_anterior = (
            EventoSite.objects
            .filter(ocorrido_em__range=(ini_ant, ini_ant + decorrido),
                    tipo='pagina_vista', sessao__in=_reais)
            .count()
        )
        # Nas primeiras horas da semana a base e pequena demais para um
        # percentual dizer alguma coisa; o template esconde o comparativo.
        comparacao_parcial = decorrido < timedelta(hours=12)
    else:
        total_atual = sum(por_dia)
        total_anterior = sum(por_dia_anterior)

    if total_anterior:
        delta_pct = round((total_atual - total_anterior) / total_anterior * 100)
    else:
        delta_pct = 100 if total_atual else 0

    return {
        'labels': NOMES,
        'labels_full': NOMES_FULL,
        'horas': HORAS,
        'datas': [d.strftime('%d/%m') for d in datas],
        'por_dia': por_dia_exib,
        'por_dia_anterior': por_dia_anterior,
        'por_dia_hora': por_dia_hora,
        'pico_dia': NOMES_FULL[pico_dia_idx] if pico_dia_idx is not None else '',
        'pico_dia_total': por_dia[pico_dia_idx] if pico_dia_idx is not None else 0,
        'menor_dia': NOMES_FULL[menor_dia_idx] if menor_dia_idx is not None else '',
        'menor_dia_total': por_dia[menor_dia_idx] if menor_dia_idx is not None else 0,
        'pico_hora': pico_hora,
        # Navegacao e comparacao
        'semana_label': f"{datas[0].strftime('%d/%m')} a {datas[6].strftime('%d/%m/%Y')}",
        'semana_atual': seg_semana.strftime('%Y-%m-%d'),
        'semana_anterior': (seg_semana - timedelta(days=7)).strftime('%Y-%m-%d'),
        'semana_proxima': (seg_semana + timedelta(days=7)).strftime('%Y-%m-%d'),
        'tem_proxima': seg_semana < (hoje - timedelta(days=hoje.weekday())),
        'eh_semana_atual': em_curso,
        'total_atual': total_atual,
        'total_anterior': total_anterior,
        'delta_pct': delta_pct,
        'delta_subiu': total_atual >= total_anterior,
        'comparacao_parcial': comparacao_parcial,
    }


def _calcular_origens(inicio, fim):
    from apps.analytics.attribution import label_origem
    from apps.analytics.models import SessaoSite
    from apps.analytics.trafego import base_trafego
    from django.db.models import BooleanField, Case, Value, When

    # Agrupa por utm_source + presenca de click id (fbclid/gclid). Os click ids
    # entram apenas como BOOLEAN (tem/nao tem) para nao explodir o agrupamento --
    # o valor de cada fbclid e unico por clique.
    # Sessoes com atividade no periodo, nao iniciadas nele (ver a nota em
    # views/visitas.py: a sessao vive muito mais que a janela consultada).
    from apps.analytics.models import EventoSite as _Evt
    _ativas = _Evt.objects.filter(
        ocorrido_em__range=(inicio, fim), sessao__in=base_trafego().values('pk')
    ).values('sessao_id')

    sessoes = list(
        base_trafego()
        .filter(pk__in=_ativas)
        .annotate(
            tem_fbclid=Case(When(fbclid='', then=Value(False)),
                            default=Value(True), output_field=BooleanField()),
            tem_gclid=Case(When(gclid='', then=Value(False)),
                           default=Value(True), output_field=BooleanField()),
        )
        .values('utm_source', 'utm_medium', 'tem_fbclid', 'tem_gclid')
        .annotate(total=Count('id'))
        .order_by('-total')[:60]
    )

    agg = {}
    for row in sessoes:
        label = label_origem(row['utm_source'], row['tem_fbclid'], row['tem_gclid'],
                             row['utm_medium'])
        agg[label] = agg.get(label, 0) + row['total']

    total = sum(agg.values()) or 1
    result = [
        {'origem': k, 'total': v, 'pct': round(v / total * 100, 1)}
        for k, v in sorted(agg.items(), key=lambda x: -x[1])
    ]
    return result[:8]
