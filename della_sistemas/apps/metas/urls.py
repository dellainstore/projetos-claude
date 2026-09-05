from django.urls import path
from apps.metas.views.dashboard import (
    view_dashboard,
    view_atualizar_start,
    view_atualizar_status,
)
from apps.metas.views.cadastro import (
    view_metas_individual,
    view_metas_canal,
)

app_name = "metas"

urlpatterns = [
    # Dashboard
    path("", view_dashboard, name="dashboard"),

    # Atualização sob demanda (antecipa o cron) — dispara em background + polling
    path("atualizar/", view_atualizar_start, name="atualizar_start"),
    path("atualizar/status/", view_atualizar_status, name="atualizar_status"),

    # Cadastro — Metas por mês (colaboradores vêm do cadastro único do RH)
    path("cadastro/metas-individual/", view_metas_individual, name="metas_individual"),
    path("cadastro/metas-canal/", view_metas_canal, name="metas_canal"),
]
