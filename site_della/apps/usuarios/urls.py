from django.urls import path
from . import views

app_name = 'usuarios'

urlpatterns = [
    path('entrar/', views.login_view, name='login'),
    path('sair/', views.logout_view, name='logout'),
    path('cadastro/', views.cadastro, name='cadastro'),
    path('minha-conta/', views.minha_conta, name='minha_conta'),
    path('minha-conta/editar/', views.editar_perfil, name='editar_perfil'),
    path('minha-conta/enderecos/', views.enderecos, name='enderecos'),
    path('minha-conta/enderecos/novo/', views.novo_endereco, name='novo_endereco'),
    path('minha-conta/enderecos/<int:pk>/editar/', views.editar_endereco, name='editar_endereco'),
    path('minha-conta/enderecos/<int:pk>/excluir/', views.excluir_endereco, name='excluir_endereco'),
    path('recuperar-senha/', views.recuperar_senha, name='recuperar_senha'),
    path('recuperar-senha/confirmar/<uidb64>/<token>/', views.confirmar_senha, name='confirmar_senha'),
]
