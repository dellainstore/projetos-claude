from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core_utils.admin_views import relatorio as admin_relatorio, instagram_refresh

# Personaliza o cabeçalho do Django Admin
admin.site.site_header = 'Della Instore — Administração'
admin.site.site_title = 'Della Instore'
admin.site.index_title = 'Painel de Controle'

urlpatterns = [
    # Admin Django
    path('painel/', admin.site.urls),
    path('painel/relatorio/', admin_relatorio, name='admin_relatorio'),
    path('painel/instagram/refresh/', instagram_refresh, name='admin_instagram_refresh'),

    # Homepage e páginas institucionais
    path('', include('apps.produtos.urls', namespace='produtos')),

    # Conta do cliente (login, cadastro, minha conta)
    path('conta/', include('apps.usuarios.urls', namespace='usuarios')),

    # Carrinho e checkout
    path('carrinho/', include('apps.pedidos.urls', namespace='pedidos')),

    # Pagamentos (webhooks PagSeguro/Stone)
    path('pagamento/', include('apps.pagamentos.urls', namespace='pagamentos')),

    # Webhooks Bling (retorno de NF, pedidos)
    path('bling/', include('apps.bling.urls', namespace='bling')),
]

# Serve arquivos de media em desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
