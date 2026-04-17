from django.urls import path
from . import views

app_name = 'pagamentos'

urlpatterns = [
    # PagSeguro
    path('pagseguro/retorno/', views.pagseguro_retorno, name='pagseguro_retorno'),
    path('pagseguro/notificacao/', views.pagseguro_notificacao, name='pagseguro_notificacao'),

    # Stone
    path('stone/webhook/', views.stone_webhook, name='stone_webhook'),

    # Cartão — repagamento de pedido existente
    path('cartao/pagar/<str:pedido_numero>/', views.cartao_pagar_pedido, name='cartao_pagar_pedido'),

    # Pix (geração de QR Code e polling de status)
    path('pix/gerar/<str:pedido_numero>/', views.pix_gerar, name='pix_gerar'),
    path('pix/status/<str:pedido_numero>/', views.pix_status, name='pix_status'),
]
