from django.urls import path
from . import views

app_name = 'bling'

urlpatterns = [
    path('autorizar/', views.oauth_autorizar, name='oauth_autorizar'),
    path('callback/',  views.oauth_callback,  name='oauth_callback'),
    path('webhook/',   views.webhook,          name='webhook'),
]
