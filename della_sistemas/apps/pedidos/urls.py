from django.urls import path

from apps.pedidos.views.dashboard import view_dashboard, view_sync_start, view_sync_status
from apps.pedidos.views.historico import view_historico, view_historico_excluir
from apps.pedidos.views.pagamentos import (
    view_dar_baixa,
    view_dar_baixa_parcela,
    view_pagamentos_confirmados,
    view_pagamentos_pendentes,
    view_pagamentos_resumo,
    view_salvar_correcao,
)
from apps.pedidos.views.pendentes import view_pendentes

app_name = "pedidos"

urlpatterns = [
    path("", view_dashboard, name="dashboard"),
    path("sync/start/", view_sync_start, name="sync_start"),
    path("sync/status/", view_sync_status, name="sync_status"),
    path("historico/", view_historico, name="historico"),
    path("historico/excluir/<str:tipo>/<int:pk>/", view_historico_excluir, name="historico_excluir"),
    path("pendentes/", view_pendentes, name="pendentes"),
    path("pagamentos/pendentes/", view_pagamentos_pendentes, name="pagamentos_pendentes"),
    path("pagamentos/confirmados/", view_pagamentos_confirmados, name="pagamentos_confirmados"),
    path("pagamentos/resumo/", view_pagamentos_resumo, name="pagamentos_resumo"),
    path("htmx/dar-baixa/<int:pedido_id>/", view_dar_baixa, name="dar_baixa"),
    path("htmx/baixar-parcela/<int:parcela_id>/", view_dar_baixa_parcela, name="dar_baixa_parcela"),
    path("htmx/salvar-correcao/<int:pedido_id>/", view_salvar_correcao, name="salvar_correcao"),
]
