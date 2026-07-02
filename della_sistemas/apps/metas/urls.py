from django.urls import path
from apps.metas.views.dashboard import view_dashboard
from apps.metas.views.cadastro import (
    view_metas_individual,
    view_metas_canal,
)

app_name = "metas"

urlpatterns = [
    # Dashboard
    path("", view_dashboard, name="dashboard"),

    # Cadastro — Metas por mês (colaboradores vêm do cadastro único do RH)
    path("cadastro/metas-individual/", view_metas_individual, name="metas_individual"),
    path("cadastro/metas-canal/", view_metas_canal, name="metas_canal"),
]
