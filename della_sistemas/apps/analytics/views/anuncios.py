"""Painel Anúncios: investimento e funil (alcance → clique → carrinho →
compra) por campanha, direto da Marketing API do Meta.

Números só do Meta (mesmo sendo mais otimistas que a venda real do site) —
pedido explícito do dono em 2026-08-24: quer falar a mesma língua que o
Gerenciador de Anúncios, sem um segundo número "verificado" que cause
estranheza comparado ao que o Meta mostra.

Padrão da tela (diferente de Visitas/Vendas, que abrem em "últimos 7 dias"):
  - Campanhas: só as ATIVAS, todas pré-marcadas.
  - Período: desde o início da campanha ativa mais antiga até hoje.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required

from apps.analytics.metricas import _resolver_periodo


@perm_required("analytics.ver_anuncios")
def anuncios(request: HttpRequest) -> HttpResponse:
    from apps.analytics import meta_ads
    from django.utils import timezone

    if not meta_ads.configurado():
        return render(request, 'analytics/anuncios.html', {
            'sem_config': True, 'filtro': '', 'de_val': '', 'ate_val': '',
        })

    campanhas = meta_ads.listar_campanhas()

    status_filtro = request.GET.get('status', 'ativas')  # ativas | inativas | todas
    if status_filtro == 'ativas':
        campanhas_visiveis = [c for c in campanhas if c['ativa']]
    elif status_filtro == 'inativas':
        campanhas_visiveis = [c for c in campanhas if not c['ativa']]
    else:
        campanhas_visiveis = campanhas

    campanhas_ativas = [c for c in campanhas if c['ativa']]

    # Sem nenhum filtro escolhido: seleciona automaticamente TODAS as
    # campanhas ativas e usa o período desde a mais antiga delas até hoje.
    auto = 'campanha' not in request.GET
    if auto:
        campanha_ids_selecionadas = [c['id'] for c in campanhas_ativas]
    else:
        campanha_ids_selecionadas = request.GET.getlist('campanha')

    if 'periodo' in request.GET:
        filtro, inicio, fim, de_val, ate_val = _resolver_periodo(request)
    else:
        datas_inicio = [c['inicio'] for c in campanhas_ativas if c['inicio']]
        inicio = min(datas_inicio) if datas_inicio else None
        fim = timezone.now()
        filtro, de_val, ate_val = 'auto', '', ''

    funil = meta_ads.funil_periodo(inicio, fim, campanha_ids_selecionadas or None)
    orcamento_diario = meta_ads.orcamento_diario_medio(campanhas, campanha_ids_selecionadas)

    return render(request, 'analytics/anuncios.html', {
        'filtro': filtro, 'de_val': de_val, 'ate_val': ate_val,
        'periodo_inicio': inicio, 'periodo_fim': fim,
        'status_filtro': status_filtro,
        'campanhas_visiveis': campanhas_visiveis,
        'campanha_ids_selecionadas': campanha_ids_selecionadas,
        'total_campanhas': len(campanhas),
        'funil': funil,
        'orcamento_diario': orcamento_diario,
    })
