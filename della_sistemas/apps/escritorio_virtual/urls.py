"""Rotas do escritório virtual.

Só existem rotas GET. Não há endpoint público nesta versão: `/escritorio/`
inteiro exige sessão + permissão `escritorio.ver`.
"""

from django.urls import path

from apps.escritorio_virtual.views import api as v_api
from apps.escritorio_virtual.views import diagnostico as v_diag

app_name = "escritorio"

urlpatterns = [
    path("", v_diag.view_diagnostico, name="diagnostico"),
    path("api/estado/", v_api.view_estado, name="api_estado"),
]
