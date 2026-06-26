from django.urls import path
from apps.metas.views.dashboard import view_dashboard
from apps.metas.views.cadastro import (
    view_funcionarios,
    view_funcionario_form,
    view_funcionario_desativar,
    view_metas_individual,
    view_metas_canal,
)

app_name = "metas"

urlpatterns = [
    # Dashboard
    path("", view_dashboard, name="dashboard"),

    # Cadastro — Funcionários
    path("cadastro/funcionarios/", view_funcionarios, name="cadastro_funcionarios"),
    path("cadastro/funcionarios/novo/", view_funcionario_form, name="funcionario_novo"),
    path("cadastro/funcionarios/<int:pk>/editar/", view_funcionario_form, name="funcionario_editar"),
    path("cadastro/funcionarios/<int:pk>/toggle/", view_funcionario_desativar, name="funcionario_toggle"),

    # Cadastro — Metas por mês
    path("cadastro/metas-individual/", view_metas_individual, name="metas_individual"),
    path("cadastro/metas-canal/", view_metas_canal, name="metas_canal"),
]
