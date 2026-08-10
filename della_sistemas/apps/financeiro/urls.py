from django.urls import path

from apps.financeiro import views

app_name = "financeiro"

urlpatterns = [
    path("dashboard-faturamento/", views.view_dashboard_faturamento, name="dashboard_faturamento"),
    path("htmx/dashboard-faturamento/", views.htmx_dashboard_dados, name="htmx_dashboard_faturamento"),
]
