from django.urls import path

from .views import dashboard, relatorio, saldo, solicitar, webhook

app_name = "motoqueiro"

urlpatterns = [
    path("", relatorio.view_relatorio, name="relatorio"),
    path("dashboard/", dashboard.view_dashboard, name="dashboard"),
    path("saldo/", saldo.view_saldo, name="saldo"),
    path("saldo/lancar/", saldo.view_saldo_lancar, name="saldo_lancar"),
    path("solicitar/", solicitar.view_solicitar, name="solicitar"),
    path("solicitar/autocomplete/", solicitar.htmx_autocomplete, name="htmx_autocomplete"),
    path("solicitar/place-details/", solicitar.htmx_place_details, name="htmx_place_details"),
    path("solicitar/cotar/", solicitar.htmx_cotar, name="htmx_cotar"),
    path("solicitar/confirmar/", solicitar.htmx_confirmar, name="htmx_confirmar"),
    path("<int:pk>/status/", relatorio.view_atualizar_status_manual, name="atualizar_status_manual"),
    path("webhook/lalamove/", webhook.webhook_lalamove, name="webhook_lalamove"),
    path("webhook/loggi/", webhook.webhook_loggi, name="webhook_loggi"),
]
