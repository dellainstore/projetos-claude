from django.urls import path

from .views import dashboard, monitoramento, relatorio, saldo, solicitar, webhook

app_name = "motoqueiro"

urlpatterns = [
    path("", relatorio.view_relatorio, name="relatorio"),
    path("dashboard/", dashboard.view_dashboard, name="dashboard"),
    path("saldo/", saldo.view_saldo, name="saldo"),
    path("saldo/lancar/", saldo.view_saldo_lancar, name="saldo_lancar"),
    path("monitoramento/", monitoramento.view_monitoramento, name="monitoramento"),
    path("monitoramento/criar/", monitoramento.view_criar, name="monitoramento_criar"),
    path("monitoramento/<int:pk>/cancelar/", monitoramento.view_cancelar, name="monitoramento_cancelar"),
    path("solicitar/", solicitar.view_solicitar, name="solicitar"),
    path("solicitar/autocomplete/", solicitar.htmx_autocomplete, name="htmx_autocomplete"),
    path("solicitar/place-details/", solicitar.htmx_place_details, name="htmx_place_details"),
    path("solicitar/cotar/", solicitar.htmx_cotar, name="htmx_cotar"),
    path("solicitar/confirmar/", solicitar.htmx_confirmar, name="htmx_confirmar"),
    path("<int:pk>/status/", relatorio.view_atualizar_status_manual, name="atualizar_status_manual"),
    path("<int:pk>/cancelar/", relatorio.view_cancelar, name="cancelar"),
    path("<int:pk>/prioridade/", relatorio.view_priorizar, name="priorizar"),
    # O token secreto vai no caminho: e a unica protecao possivel, ja que a
    # Lalamove nao assina os webhooks. A rota sem token responde 200 + log,
    # so pra nao gerar retry em loop enquanto a URL nao e trocada no portal.
    path("webhook/lalamove/<str:token>/", webhook.webhook_lalamove, name="webhook_lalamove"),
    path("webhook/lalamove/", webhook.webhook_lalamove, name="webhook_lalamove_sem_token"),
    path("webhook/loggi/", webhook.webhook_loggi, name="webhook_loggi"),
]
