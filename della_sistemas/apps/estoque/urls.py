from django.urls import path

from apps.estoque import views

app_name = "estoque"

urlpatterns = [
    path("atual/", views.view_estoque_atual, name="estoque_atual"),
    path("saude/", views.view_saude, name="saude"),
    path("reposicao/", views.view_reposicao, name="reposicao"),
    path("queima/", views.view_queima, name="queima"),
    path("previsao/", views.view_previsao, name="previsao"),
    path("atualizar/", views.view_atualizar_dados, name="atualizar"),
]
