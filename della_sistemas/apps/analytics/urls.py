from django.urls import path

from apps.analytics.views import ao_vivo as live_views
from apps.analytics.views import dashboard as dash_views
from apps.analytics.views import relatorio as rel_views

app_name = 'analytics'

urlpatterns = [
    path('', dash_views.dashboard, name='dashboard'),
    path('ao-vivo/', live_views.ao_vivo, name='ao_vivo'),
    path('relatorio/', rel_views.relatorio_list, name='relatorio_list'),
    path('relatorio/<int:pk>/download/', rel_views.relatorio_download, name='relatorio_download'),
]
