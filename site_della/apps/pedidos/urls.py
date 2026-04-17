from django.urls import path
from . import views

app_name = 'pedidos'

urlpatterns = [
    path('', views.carrinho, name='carrinho'),
    path('status/', views.carrinho_status, name='carrinho_status'),
    path('adicionar/<int:produto_id>/', views.adicionar_ao_carrinho, name='adicionar'),
    path('remover/<str:item_id>/', views.remover_do_carrinho, name='remover'),
    path('atualizar/', views.atualizar_carrinho, name='atualizar'),
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/endereco/', views.checkout_endereco, name='checkout_endereco'),
    path('checkout/entrega/', views.checkout_entrega, name='checkout_entrega'),
    path('checkout/pagamento/', views.checkout_pagamento, name='checkout_pagamento'),
    path('confirmacao/<str:numero>/', views.confirmacao_pedido, name='confirmacao'),
    path('meus-pedidos/', views.meus_pedidos, name='meus_pedidos'),
    path('pedido/<str:numero>/', views.detalhe_pedido, name='detalhe_pedido'),
    path('cep/<str:cep>/', views.consultar_cep, name='consultar_cep'),
    path('frete/', views.calcular_frete, name='calcular_frete'),
    path('validar-cupom/', views.validar_cupom, name='validar_cupom'),
    path('validar-vendedor/', views.validar_vendedor, name='validar_vendedor'),
]
