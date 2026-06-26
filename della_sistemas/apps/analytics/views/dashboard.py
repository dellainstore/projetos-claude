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
    hoje_inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)

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

    return filtro, inicio, fim, de_val, ate_val


def _calcular_ao_vivo():
    from apps.analytics.models import SessaoSite, EventoSite

    agora = timezone.now()
    corte = agora - timedelta(minutes=5)

    visitantes = SessaoSite.objects.filter(ultima_acao_em__gte=corte).count()
    paginas = list(
        EventoSite.objects
        .filter(tipo='pagina_vista', ocorrido_em__gte=corte)
        .values('pagina_url')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )
    return {'visitantes': visitantes, 'paginas': paginas}


def _calcular_resumo(inicio, fim):
    from apps.analytics.models import SessaoSite, EventoSite
    from django.db.models import Exists, OuterRef

    periodo = Q(ocorrido_em__range=(inicio, fim))
    sessoes_periodo = SessaoSite.objects.filter(iniciada_em__range=(inicio, fim))

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

    periodo = Q(ocorrido_em__range=(inicio, fim))

    visitantes = SessaoSite.objects.filter(iniciada_em__range=(inicio, fim)).count()
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

    periodo = Q(ocorrido_em__range=(inicio, fim))

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
    sessoes = list(
        SessaoSite.objects
        .filter(iniciada_em__range=(inicio, fim))
        .filter(Exists(EventoSite.objects.filter(sessao=OuterRef('pk'), tipo='produto_adicionado')))
        .annotate(comprou=Exists(comprou_qs))
        .order_by('-ultima_acao_em')
        .values('id', 'comprou', 'ultima_acao_em')[:20]
    )

    if not sessoes:
        return []

    session_ids = [s['id'] for s in sessoes]
    items_map: dict = {}
    for evt in (
        EventoSite.objects
        .filter(sessao_id__in=session_ids, tipo='produto_adicionado')
        .values('sessao_id', 'produto_nome', 'quantidade')
        .order_by('ocorrido_em')
    ):
        sid = evt['sessao_id']
        if sid not in items_map:
            items_map[sid] = []
        items_map[sid].append({
            'nome': (evt['produto_nome'] or 'Produto')[:45],
            'qtd': evt['quantidade'] or 1,
        })

    result = []
    for s in sessoes:
        itens = items_map.get(s['id'], [])
        total_itens = sum(i['qtd'] for i in itens)
        result.append({
            'ultima_acao': s['ultima_acao_em'],
            'comprou': s['comprou'],
            'itens': itens,
            'total_itens': total_itens,
        })
    return result


def _calcular_trafico_semanal(inicio, fim):
    from apps.analytics.models import EventoSite
    from django.db.models import Count
    from django.db.models.functions import ExtractHour, ExtractIsoWeekDay

    NOMES = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
    NOMES_FULL = ['Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado', 'Domingo']
    HORAS = [f'{h:02d}h' for h in range(24)]

    por_dia_raw = dict(
        EventoSite.objects
        .filter(ocorrido_em__range=(inicio, fim), tipo='pagina_vista')
        .annotate(dia=ExtractIsoWeekDay('ocorrido_em'))
        .values('dia')
        .annotate(total=Count('id'))
        .values_list('dia', 'total')
    )

    por_hora_raw = list(
        EventoSite.objects
        .filter(ocorrido_em__range=(inicio, fim), tipo='pagina_vista')
        .annotate(
            dia=ExtractIsoWeekDay('ocorrido_em'),
            hora=ExtractHour('ocorrido_em'),
        )
        .values('dia', 'hora')
        .annotate(total=Count('id'))
        .values_list('dia', 'hora', 'total')
    )

    por_dia = [por_dia_raw.get(i + 1, 0) for i in range(7)]

    por_dia_hora = [[0] * 24 for _ in range(7)]
    for (dia, hora, total) in por_hora_raw:
        por_dia_hora[dia - 1][hora] += total

    hora_agg = [sum(por_dia_hora[d][h] for d in range(7)) for h in range(24)]

    pico_dia_idx = por_dia.index(max(por_dia)) if any(por_dia) else None
    menor_dia_idx = min(
        (i for i, v in enumerate(por_dia) if v > 0),
        key=lambda i: por_dia[i], default=None,
    ) if any(por_dia) else None
    pico_hora = hora_agg.index(max(hora_agg)) if any(hora_agg) else None

    return {
        'labels': NOMES,
        'labels_full': NOMES_FULL,
        'horas': HORAS,
        'por_dia': por_dia,
        'por_dia_hora': por_dia_hora,
        'pico_dia': NOMES_FULL[pico_dia_idx] if pico_dia_idx is not None else '',
        'pico_dia_total': por_dia[pico_dia_idx] if pico_dia_idx is not None else 0,
        'menor_dia': NOMES_FULL[menor_dia_idx] if menor_dia_idx is not None else '',
        'menor_dia_total': por_dia[menor_dia_idx] if menor_dia_idx is not None else 0,
        'pico_hora': pico_hora,
    }


def _calcular_origens(inicio, fim):
    from apps.analytics.models import SessaoSite

    sessoes = list(
        SessaoSite.objects
        .filter(iniciada_em__range=(inicio, fim))
        .values('utm_source')
        .annotate(total=Count('id'))
        .order_by('-total')[:20]
    )

    def _label(source):
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
        return 'Direto / Outros'

    agg = {}
    for row in sessoes:
        label = _label(row['utm_source'])
        agg[label] = agg.get(label, 0) + row['total']

    total = sum(agg.values()) or 1
    result = [
        {'origem': k, 'total': v, 'pct': round(v / total * 100, 1)}
        for k, v in sorted(agg.items(), key=lambda x: -x[1])
    ]
    return result[:8]


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
        trafico   = _calcular_trafico_semanal(inicio, fim)
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
        'horas': trafico['horas'] if trafico else [],
        'por_dia': trafico['por_dia'] if trafico else [],
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
