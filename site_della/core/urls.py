from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import handler404 as custom_404, csp_report  # noqa: F401

handler404 = 'core.views.handler404'
from apps.core_utils.admin_views import (
    relatorio as admin_relatorio,
    instagram_refresh,
    dashboard_pedidos as admin_dashboard_pedidos,
    dashboard_marketing as admin_dashboard_marketing,
    dashboard_marketing_export as admin_dashboard_marketing_export,
)
from apps.core_utils.admin_verificacao import admin_verificar_view
from apps.produtos.views import feed_meta_xml
from apps.produtos.views_sitemap import sitemap_xml, robots_txt

admin.site.site_header = 'Della Instore: Administracao'
admin.site.site_title = 'Della Instore'
admin.site.index_title = 'Painel de Controle'


def _healthz(_request):
    return HttpResponse('ok', content_type='text/plain')


urlpatterns = [
    path('healthz', _healthz, name='healthz'),
    path('csp-report/', csp_report, name='csp_report'),
    path('painel/relatorio/', admin_relatorio, name='admin_relatorio'),
    path('painel/pedidos/dashboard/', admin_dashboard_pedidos, name='admin_dashboard_pedidos'),
    path('painel/marketing/', admin_dashboard_marketing, name='admin_marketing'),
    path('painel/marketing/export/', admin_dashboard_marketing_export, name='admin_marketing_export'),
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

    # Analytics interno (endpoint de eventos client-side)
    path('analytics/', include('apps.analytics.urls', namespace='analytics')),
]

# Serve arquivos de media em desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
