import json
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.core.decorators import perm_required


def _db_disponivel():
    return 'della_site' in settings.DATABASES


def _resolver_periodo(request):
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
    elif filtro == '30d':
        inicio = agora - timedelta(days=30)
        fim = agora
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
            inicio = agora - timedelta(days=7)
            fim = agora
            de_val = ate_val = ''
    else:
        filtro = '7d'
        inicio = agora - timedelta(days=7)
        fim = agora

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

    vivos = SessaoSite.objects.filter(ultima_acao_em__gte=corte, is_bot=False)
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
    return {'visitantes': visitantes, 'paginas': paginas}


def _calcular_resumo(inicio, fim):
    from apps.analytics.models import SessaoSite, EventoSite
    from django.db.models import Exists, OuterRef

    # is_bot=False em todas as metricas: o painel mostra apenas pessoas reais.
    periodo = Q(ocorrido_em__range=(inicio, fim), sessao__is_bot=False)
    sessoes_periodo = SessaoSite.objects.filter(iniciada_em__range=(inicio, fim), is_bot=False)

    visitas    = EventoSite.objects.filter(periodo, tipo='pagina_vista').count()
    visitantes = sessoes_periodo.count()

    pedidos = (
        EventoSite.objects
        .filter(periodo, tipo='pedido_finalizado', pedido_numero__gt='')
        .values('pedido_numero')
        .distinct()
        .count()
    )
    receita = (
        EventoSite.objects
        .filter(periodo, tipo='pedido_finalizado', pedido_numero__gt='')
        .aggregate(total=Sum('valor_total'))['total'] or 0
    )
    itens_vendidos = (
        EventoSite.objects
        .filter(periodo, tipo='pedido_finalizado', produto_slug__gt='')
        .aggregate(total=Sum('quantidade'))['total'] or 0
    )

    comprou_qs = EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='pedido_finalizado', pedido_numero__gt=''
    )
    carrinhos_abandonados = (
        sessoes_periodo
        .filter(Exists(EventoSite.objects.filter(sessao=OuterRef('pk'), tipo='produto_adicionado')))
        .exclude(Exists(comprou_qs))
        .count()
    )
    checkouts_abandonados = (
        sessoes_periodo
        .filter(Exists(EventoSite.objects.filter(sessao=OuterRef('pk'), tipo='checkout_iniciado')))
        .exclude(Exists(comprou_qs))
        .count()
    )

    taxa = round(pedidos / visitantes * 100, 1) if visitantes > 0 else 0
    media_paginas = round(visitas / visitantes, 1) if visitantes > 0 else 0

    return {
        'visitas': visitas,
        'visitantes': visitantes,
        'pedidos': pedidos,
        'receita': receita,
        'itens_vendidos': itens_vendidos,
        'carrinhos_abandonados': carrinhos_abandonados,
        'checkouts_abandonados': checkouts_abandonados,
        'taxa': taxa,
        'media_paginas': media_paginas,
    }


def _calcular_funil(inicio, fim):
    from apps.analytics.models import SessaoSite, EventoSite

    periodo = Q(ocorrido_em__range=(inicio, fim), sessao__is_bot=False)

    visitantes = SessaoSite.objects.filter(iniciada_em__range=(inicio, fim), is_bot=False).count()
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
    compraram = (
        EventoSite.objects
        .filter(periodo, tipo='pedido_finalizado', pedido_numero__gt='')
        .values('sessao_id').distinct().count()
    )

    base = visitantes or 1

    def pct(n):
        return round(n / base * 100, 1)

    etapas = [
        {'label': 'Entraram no site',          'total': visitantes, 'pct': 100.0},
        {'label': 'Viram um produto',           'total': viram,      'pct': pct(viram)},
        {'label': 'Adicionaram ao carrinho',    'total': adicionaram,'pct': pct(adicionaram)},
        {'label': 'Foram ao checkout',          'total': checkout,   'pct': pct(checkout)},
        {'label': 'Finalizaram a compra',       'total': compraram,  'pct': pct(compraram)},
    ]
    for i, e in enumerate(etapas):
        if i + 1 < len(etapas):
            e['queda'] = e['total'] - etapas[i + 1]['total']
        else:
            e['queda'] = 0
    return etapas


def _calcular_produtos(inicio, fim):
    from apps.analytics.models import EventoSite

    periodo = Q(ocorrido_em__range=(inicio, fim), sessao__is_bot=False)

    mais_vistos = list(
        EventoSite.objects
        .filter(periodo, tipo='produto_visualizado', produto_slug__gt='')
        .values('produto_slug', 'produto_nome')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )
    mais_adicionados = list(
        EventoSite.objects
        .filter(periodo, tipo='produto_adicionado', produto_slug__gt='')
        .values('produto_slug', 'produto_nome')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )
    mais_vendidos = list(
        EventoSite.objects
        .filter(periodo, tipo='pedido_finalizado', produto_slug__gt='')
        .values('produto_slug', 'produto_nome')
        .annotate(total=Count('id'), receita=Sum('valor_total'))
        .order_by('-total')[:10]
    )

    return {
        'mais_vistos': mais_vistos,
        'mais_adicionados': mais_adicionados,
        'mais_vendidos': mais_vendidos,
    }


def _calcular_carrinhos_recentes(inicio, fim):
    from apps.analytics.models import SessaoSite, EventoSite
    from django.db.models import Exists, OuterRef

    comprou_qs = EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='pedido_finalizado', pedido_numero__gt=''
    )
    checkout_qs = EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='checkout_iniciado'
    )
    popup_qs = EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='popup_saida_exibido'
    )
    sessoes = list(
        SessaoSite.objects
        .filter(iniciada_em__range=(inicio, fim), is_bot=False)
        .filter(Exists(EventoSite.objects.filter(sessao=OuterRef('pk'), tipo='produto_adicionado')))
        .annotate(
            comprou=Exists(comprou_qs),
            foi_checkout=Exists(checkout_qs),
            viu_popup=Exists(popup_qs),
        )
        .order_by('-ultima_acao_em')
        .values('id', 'comprou', 'foi_checkout', 'viu_popup', 'ultima_acao_em')[:20]
    )

    if not sessoes:
        return []

    session_ids = [s['id'] for s in sessoes]
    items_map: dict = {}
    for evt in (
        EventoSite.objects
        .filter(sessao_id__in=session_ids, tipo='produto_adicionado')
        .values('sessao_id', 'produto_nome', 'quantidade', 'valor_total')
        .order_by('ocorrido_em')
    ):
        sid = evt['sessao_id']
        if sid not in items_map:
            items_map[sid] = []
        items_map[sid].append({
            'nome': (evt['produto_nome'] or 'Produto')[:45],
            'qtd': evt['quantidade'] or 1,
            'valor': evt['valor_total'] or 0,
        })

    result = []
    for s in sessoes:
        itens = items_map.get(s['id'], [])
        total_itens = sum(i['qtd'] for i in itens)
        valor_total = sum(i['valor'] for i in itens)
        result.append({
            'ultima_acao': s['ultima_acao_em'],
            'comprou': s['comprou'],
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
    from django.db.models import Count
    from django.db.models.functions import ExtractHour, TruncDate

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
            .filter(ocorrido_em__range=(ini, fim), tipo='pagina_vista', sessao__is_bot=False)
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
        .filter(ocorrido_em__range=(ini, fim), tipo='pagina_vista', sessao__is_bot=False)
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

    # Comparacao com a semana anterior. Se a semana ainda esta em curso, compara
    # so o trecho ja decorrido (Seg ate hoje) contra os mesmos dias da anterior.
    em_curso = seg_semana <= hoje <= seg_semana + timedelta(days=6)
    if em_curso:
        n = (hoje - seg_semana).days + 1
        total_atual = sum(por_dia[:n])
        total_anterior = sum(por_dia_anterior[:n])
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
    }


def _calcular_origens(inicio, fim):
    from apps.analytics.models import SessaoSite
    from django.db.models import BooleanField, Case, Value, When

    # Agrupa por utm_source + presenca de click id (fbclid/gclid). Os click ids
    # entram apenas como BOOLEAN (tem/nao tem) para nao explodir o agrupamento --
    # o valor de cada fbclid e unico por clique.
    sessoes = list(
        SessaoSite.objects
        .filter(iniciada_em__range=(inicio, fim), is_bot=False)
        .annotate(
            tem_fbclid=Case(When(fbclid='', then=Value(False)),
                            default=Value(True), output_field=BooleanField()),
            tem_gclid=Case(When(gclid='', then=Value(False)),
                           default=Value(True), output_field=BooleanField()),
        )
        .values('utm_source', 'tem_fbclid', 'tem_gclid')
        .annotate(total=Count('id'))
        .order_by('-total')[:40]
    )

    def _label(source, tem_fbclid=False, tem_gclid=False):
        s = (source or '').lower().strip()
        if 'google' in s:
            return 'Google'
        if s in ('ig', 'instagram') or 'instagram' in s:
            return 'Instagram'
        if s in ('fb', 'facebook') or 'facebook' in s:
            return 'Facebook'
        if 'meta' in s:
            return 'Meta'
        if 'whatsapp' in s or 'wapp' in s:
            return 'WhatsApp'
        if s:
            return s.capitalize()
        # Sem utm_source: o click id revela a origem paga do clique.
        if tem_fbclid:
            return 'Meta'
        if tem_gclid:
            return 'Google'
        return 'Direto / Outros'

    agg = {}
    for row in sessoes:
        label = _label(row['utm_source'], row['tem_fbclid'], row['tem_gclid'])
        agg[label] = agg.get(label, 0) + row['total']

    total = sum(agg.values()) or 1
    result = [
        {'origem': k, 'total': v, 'pct': round(v / total * 100, 1)}
        for k, v in sorted(agg.items(), key=lambda x: -x[1])
    ]
    return result[:8]


@perm_required("analytics.ver")
def htmx_trafico(request: HttpRequest) -> HttpResponse:
    if not _db_disponivel():
        return HttpResponse('')
    try:
        trafico = _calcular_trafico_semanal(_segunda_da_semana(request))
    except Exception:
        trafico = None
    trafico_json = json.dumps({
        'labels': trafico['labels'] if trafico else [],
        'labels_full': trafico['labels_full'] if trafico else [],
        'datas': trafico['datas'] if trafico else [],
        'horas': trafico['horas'] if trafico else [],
        'por_dia': trafico['por_dia'] if trafico else [],
        'por_dia_anterior': trafico['por_dia_anterior'] if trafico else [],
        'por_dia_hora': trafico['por_dia_hora'] if trafico else [],
    }) if trafico else 'null'
    return render(request, 'analytics/_trafico_card.html', {
        'trafico': trafico,
        'trafico_json': trafico_json,
    })


@perm_required("analytics.ver")
def dashboard(request: HttpRequest) -> HttpResponse:
    if not _db_disponivel():
        return render(request, 'analytics/dashboard.html', {
            'sem_config': True,
            'filtro': '7d',
        })

    filtro, inicio, fim, de_val, ate_val = _resolver_periodo(request)

    try:
        ao_vivo   = _calcular_ao_vivo()
        resumo    = _calcular_resumo(inicio, fim)
        funil     = _calcular_funil(inicio, fim)
        produtos  = _calcular_produtos(inicio, fim)
        origens   = _calcular_origens(inicio, fim)
        carrinhos = _calcular_carrinhos_recentes(inicio, fim)
        trafico   = _calcular_trafico_semanal(_segunda_da_semana(request))
        db_ok = True
    except Exception:
        ao_vivo   = {'visitantes': 0, 'paginas': []}
        resumo    = {'visitas': 0, 'visitantes': 0, 'pedidos': 0, 'receita': 0,
                     'itens_vendidos': 0, 'carrinhos_abandonados': 0,
                     'checkouts_abandonados': 0, 'taxa': 0, 'media_paginas': 0}
        funil     = []
        produtos  = {'mais_vistos': [], 'mais_adicionados': [], 'mais_vendidos': []}
        origens   = []
        carrinhos = []
        trafico   = None
        db_ok = False

    trafico_json = json.dumps({
        'labels': trafico['labels'] if trafico else [],
        'labels_full': trafico['labels_full'] if trafico else [],
        'datas': trafico['datas'] if trafico else [],
        'horas': trafico['horas'] if trafico else [],
        'por_dia': trafico['por_dia'] if trafico else [],
        'por_dia_anterior': trafico['por_dia_anterior'] if trafico else [],
        'por_dia_hora': trafico['por_dia_hora'] if trafico else [],
    }) if trafico else 'null'

    return render(request, 'analytics/dashboard.html', {
        'filtro': filtro,
        'de_val': de_val,
        'ate_val': ate_val,
        'ao_vivo': ao_vivo,
        'resumo': resumo,
        'funil': funil,
        'produtos': produtos,
        'origens': origens,
        'carrinhos': carrinhos,
        'trafico': trafico,
        'trafico_json': trafico_json,
        'db_ok': db_ok,
    })
