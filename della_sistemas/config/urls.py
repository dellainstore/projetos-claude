from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls", namespace="core")),
    path("produtos/", include("apps.produtos.urls", namespace="produtos")),
    path("metas/", include("apps.metas.urls", namespace="metas")),
    path("pedidos/", include("apps.pedidos.urls", namespace="pedidos")),
    path("analytics/", include("apps.analytics.urls", namespace="analytics")),
]
