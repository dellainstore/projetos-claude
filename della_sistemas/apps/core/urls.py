from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.view_home, name="home"),
    path("login/", views.view_login, name="login"),
    path("logout/", views.view_logout, name="logout"),
    path("usuarios/", views.view_usuarios, name="usuarios"),
    path("usuarios/criar/", views.view_usuario_criar, name="usuario_criar"),
    path("usuarios/<int:pk>/editar/", views.view_usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/desativar/", views.view_usuario_desativar, name="usuario_desativar"),
]
