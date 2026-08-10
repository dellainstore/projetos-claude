from django.urls import path

from apps.tarefas.views import colunas, historico, htmx, painel

app_name = "tarefas"

urlpatterns = [
    path("", painel.view_painel, name="painel"),
    path("historico/", historico.view_historico, name="historico"),

    path("htmx/board/", htmx.htmx_board, name="htmx_board"),
    path("htmx/badge/", htmx.htmx_badge_pendencias, name="htmx_badge_pendencias"),
    path("htmx/nova/", htmx.htmx_form_nova_tarefa, name="htmx_form_nova_tarefa"),
    path("htmx/criar/", htmx.htmx_criar_tarefa, name="htmx_criar_tarefa"),
    path("htmx/tarefa/<int:pk>/", htmx.htmx_detalhe_tarefa, name="htmx_detalhe_tarefa"),
    path("htmx/tarefa/<int:pk>/editar/", htmx.htmx_editar_tarefa, name="htmx_editar_tarefa"),
    path("htmx/tarefa/<int:pk>/mover/", htmx.htmx_mover_status, name="htmx_mover_status"),
    path("htmx/tarefa/<int:pk>/arquivar/", htmx.htmx_arquivar_tarefa, name="htmx_arquivar_tarefa"),

    path("colunas/", colunas.view_colunas, name="colunas"),
    path("colunas/criar/", colunas.htmx_criar_coluna, name="htmx_criar_coluna"),
    path("colunas/<int:pk>/editar/", colunas.htmx_editar_coluna, name="htmx_editar_coluna"),
    path("colunas/reordenar/", colunas.htmx_reordenar_colunas, name="htmx_reordenar_colunas"),
]
