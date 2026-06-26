from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('evento/', views.registrar_evento_ajax, name='evento'),
    path('capturar-email-popup/', views.capturar_email_popup, name='capturar_email_popup'),
]
