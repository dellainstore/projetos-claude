from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core_utils.admin_views import (
    relatorio as admin_relatorio,
    instagram_refresh,
    dashboard_pedidos as admin_dashboard_pedidos,
)
from apps.core_utils.admin_verificacao import admin_verificar_view
from apps.produtos.views import feed_meta_xml
from apps.produtos.views_sitemap import sitemap_xml, robots_txt

# Personaliza o cabeçalho do Django Admin
admin.site.site_header = 'Della Instore — Administração'
admin.site.site_title = 'Della Instore'
admin.site.index_title = 'Painel de Controle'

urlpatterns = [
    path('painel/relatorio/', admin_relatorio, name='admin_relatorio'),
    path('painel/pedidos/dashboard/', admin_dashboard_pedidos, name='admin_dashboard_pedidos'),
    path('painel/instagram/refresh/', instagram_refresh, name='admin_instagram_refresh'),
    # Verificação de e-mail a cada 30 dias (deve vir antes de painel/)
    path('painel/verificar/', admin_verificar_view, name='admin_verificar'),
    # Admin Django
    path('painel/', admin.site.urls),
    path('feed-meta.xml', feed_meta_xml, name='feed_meta'),
    path('sitemap.xml', sitemap_xml, name='sitemap'),
    path('robots.txt', robots_txt, name='robots'),

    # Homepage e páginas institucionais
    path('', include('apps.produtos.urls', namespace='produtos')),

    # Conta do cliente (login, cadastro, minha conta)
    path('conta/', include('apps.usuarios.urls', namespace='usuarios')),

    # Carrinho e checkout
    path('carrinho/', include('apps.pedidos.urls', namespace='pedidos')),

    # Pagamentos (webhooks PagSeguro)
    path('pagamento/', include('apps.pagamentos.urls', namespace='pagamentos')),

    # Webhooks Bling (retorno de NF, pedidos)
    path('bling/', include('apps.bling.urls', namespace='bling')),
]

# Serve arquivos de media em desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
