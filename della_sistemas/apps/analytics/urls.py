from django.urls import path

from apps.analytics.views import ao_vivo as live_views
from apps.analytics.views import relatorio as rel_views
from apps.analytics.views import vendas_painel as vendas_views
from apps.analytics.views import visitas as visitas_views

app_name = 'analytics'

urlpatterns = [
    # A tela antiga "Analytics do Site" foi substituida pelos paineis Visitas e
    # Vendas em 2026-08-24. A rota continua respondendo, redirecionando, para
    # nao quebrar link salvo, favorito ou atalho que alguem ja tenha.
    path('', visitas_views.antiga_para_visitas, name='dashboard'),

    path('visitas/', visitas_views.visitas, name='visitas'),
    path('vendas/', vendas_views.vendas, name='vendas'),
    path('vendas/exportar/', vendas_views.vendas_export, name='vendas_export'),

    path('gerar-link/', visitas_views.gerar_link, name='gerar_link'),

    path('htmx/trafico/', visitas_views.htmx_trafico, name='htmx_trafico'),
    path('ao-vivo/', live_views.ao_vivo, name='ao_vivo'),
    path('relatorio/', rel_views.relatorio_list, name='relatorio_list'),
    path('relatorio/<int:pk>/download/', rel_views.relatorio_download, name='relatorio_download'),
]
