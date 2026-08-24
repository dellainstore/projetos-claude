"""Painel Visitas: quem chega ao site, de onde e de que lugar do Brasil.

Divide com o painel Vendas o que antes ficava numa tela so e espalhado entre
dois sistemas. A regra da divisao:

- Visitas conta PESSOAS. A unidade e o visitante. Dinheiro so aparece como a
  conversao de cada origem, para responder onde vale investir.
- Vendas conta DINHEIRO. A unidade e o pedido pago.

A origem aparece nos dois de proposito, respondendo perguntas diferentes:
aqui, "quanta gente cada canal trouxe"; la, "quanto cada canal faturou".
"""

import json

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required

from apps.analytics.metricas import (
    _calcular_ao_vivo, _calcular_funil, _calcular_produtos,
    _calcular_trafico_semanal, _db_disponivel, _resolver_periodo,
    _segunda_da_semana,
)


@perm_required("analytics.ver")
def antiga_para_visitas(request: HttpRequest) -> HttpResponse:
    """Rota da tela antiga "Analytics do Site", substituida em 2026-08-24.

    Continua respondendo para nao quebrar link salvo ou favorito. Passa pela
    mesma permissao das demais: sem ela, quem nao tem acesso nem descobre que
    a rota existe.
    """
    from django.shortcuts import redirect
    return redirect('analytics:visitas')


@perm_required("analytics.ver")
def visitas(request: HttpRequest) -> HttpResponse:
    if not _db_disponivel():
        return render(request, 'analytics/visitas.html',
                      {'sem_config': True, 'filtro': '7d'})

    filtro, inicio, fim, de_val, ate_val = _resolver_periodo(request)

    try:
        from apps.analytics.geo import (
            resumo_dispositivo, top_cidades, visitantes_por_estado,
        )
        from apps.analytics.models import EventoSite
        from apps.analytics.origens import origens_com_retorno
        from apps.analytics.trafego import base_trafego
        from django.db.models import Q

        periodo = Q(ocorrido_em__range=(inicio, fim),
                    sessao__in=base_trafego().values('pk'))

        # Sessoes com ATIVIDADE no periodo, e nao iniciadas nele. A sessao vive
        # muito mais que o periodo consultado (a do proprio dono do site comecou
        # em 25/06 e seguia ativa em 24/08), entao filtrar por `iniciada_em`
        # deixava de fora justamente quem esta navegando agora: o card dizia
        # "1 visitante" enquanto origem, mapa, cidades e dispositivo apareciam
        # vazios logo abaixo, na mesma tela.
        ids_ativas = EventoSite.objects.filter(periodo).values('sessao_id')
        sessoes = base_trafego().filter(pk__in=ids_ativas)

        visitantes = (
            EventoSite.objects.filter(periodo).values('sessao_id').distinct().count()
        )
        paginas = EventoSite.objects.filter(periodo, tipo='pagina_vista').count()

        resumo = {
            'visitantes': visitantes,
            'paginas': paginas,
            'paginas_por_visitante': round(paginas / visitantes, 1) if visitantes else 0,
        }
        ao_vivo    = _calcular_ao_vivo()
        estados    = visitantes_por_estado(sessoes)
        cidades    = top_cidades(sessoes)
        dispositivo = resumo_dispositivo(sessoes)
        origens    = origens_com_retorno(sessoes, inicio, fim)
        funil      = _calcular_funil(inicio, fim)
        produtos   = _calcular_produtos(inicio, fim)
        trafico    = _calcular_trafico_semanal(_segunda_da_semana(request))
        db_ok = True
    except Exception:
        resumo = {'visitantes': 0, 'paginas': 0, 'paginas_por_visitante': 0}
        ao_vivo = {'visitantes': 0, 'paginas': [], 'cidades': []}
        estados = cidades = dispositivo = origens = funil = []
        produtos = {'mais_vistos': [], 'mais_adicionados': [], 'mais_vendidos': []}
        trafico = None
        db_ok = False

    trafico_json = json.dumps({
        chave: trafico[chave] if trafico else []
        for chave in ('labels', 'labels_full', 'datas', 'horas',
                      'por_dia', 'por_dia_anterior', 'por_dia_hora')
    }) if trafico else 'null'

    # Maior valor do mapa, para a legenda dizer o topo da escala.
    topo_mapa = estados[0]['total'] if estados else 0

    return render(request, 'analytics/visitas.html', {
        'filtro': filtro, 'de_val': de_val, 'ate_val': ate_val,
        'resumo': resumo, 'ao_vivo': ao_vivo,
        'estados': estados, 'cidades': cidades, 'topo_mapa': topo_mapa,
        'dispositivo': dispositivo, 'origens': origens,
        'funil': funil, 'produtos': produtos,
        'trafico': trafico, 'trafico_json': trafico_json,
        'db_ok': db_ok,
    })


@perm_required("analytics.ver")
def htmx_trafico(request: HttpRequest) -> HttpResponse:
    """Troca de semana no grafico de trafego, sem recarregar a pagina."""
    if not _db_disponivel():
        return HttpResponse('')
    try:
        trafico = _calcular_trafico_semanal(_segunda_da_semana(request))
    except Exception:
        trafico = None
    trafico_json = json.dumps({
        chave: trafico[chave] if trafico else []
        for chave in ('labels', 'labels_full', 'datas', 'horas',
                      'por_dia', 'por_dia_anterior', 'por_dia_hora')
    }) if trafico else 'null'
    return render(request, 'analytics/_trafico_card.html', {
        'trafico': trafico,
        'trafico_json': trafico_json,
    })


@perm_required("analytics.ver")
def gerar_link(request: HttpRequest) -> HttpResponse:
    """Monta o link etiquetado para postagem organica (story, post, WhatsApp).

    Existe porque a etiqueta e digitada a mao nesses casos, e um espaco ou
    acento a mais faz a visita cair em "Direto ou busca" sem ninguem perceber.
    Anuncio pago nao usa isto: a Meta preenche sozinha.
    """
    return render(request, 'analytics/gerar_link.html', {})
