from django.urls import path
from . import views

app_name = 'produtos'

urlpatterns = [
    path('', views.homepage, name='home'),
    path('loja/', views.loja, name='loja'),
    path('loja/tamanhos/', views.loja_tamanhos, name='loja_tamanhos'),
    path('loja/<slug:parent_slug>/<slug:categoria_slug>/', views.loja, name='loja_subcategoria'),
    path('loja/<slug:categoria_slug>/', views.loja, name='loja_categoria'),
    path('produto/<slug:slug>/', views.detalhe_produto, name='detalhe'),
    path('avaliacoes/pedido/<str:numero>/', views.avaliar_pedido, name='avaliar_pedido'),
    path('busca/', views.busca, name='busca'),
    path('busca/autocomplete/', views.busca_autocomplete, name='busca_autocomplete'),
    path('wishlist/toggle/<int:produto_id>/', views.toggle_wishlist, name='toggle_wishlist'),
    path('wishlist/', views.wishlist, name='wishlist'),
    # Página de links da bio (Instagram) - estilo Linktree
    path('links/', views.links, name='links'),
    # Páginas institucionais
    path('sobre/', views.sobre, name='sobre'),
    path('contato/', views.contato, name='contato'),
    path('politica-de-privacidade/', views.politica_privacidade, name='politica_privacidade'),
    path('trocas-e-devolucoes/', views.trocas_devolucoes, name='trocas_devolucoes'),
    path('termos-de-uso/', views.termos_uso, name='termos_uso'),
    path('perguntas-frequentes/', views.perguntas_frequentes, name='perguntas_frequentes'),
    path('meios-de-pagamento/', views.meios_pagamento, name='meios_pagamento'),
    path('guia-de-tamanhos/', views.guia_tamanhos, name='guia_tamanhos'),
    # Outros
    path('newsletter/', views.newsletter_signup, name='newsletter'),
]
