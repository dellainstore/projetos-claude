from django.urls import path
from . import views

app_name = "produtos"

urlpatterns = [
    # Incluir Estoque
    path("incluir/", views.view_incluir, name="incluir"),
    path("incluir/submit/", views.view_incluir_submit, name="incluir_submit"),
    path("incluir/pendente/<int:request_id>/cancelar/", views.view_cancelar_request, name="cancelar_request"),
    path("incluir/pendente/<int:request_id>/editar/", views.view_editar_request, name="editar_request"),
    # HTMX endpoints
    path("htmx/bases/", views.htmx_buscar_bases, name="htmx_bases"),
    path("htmx/cores/", views.htmx_buscar_cores, name="htmx_cores"),
    path("htmx/tamanhos/", views.htmx_buscar_tamanhos, name="htmx_tamanhos"),
    path("htmx/templates/", views.htmx_buscar_templates, name="htmx_templates"),
    # Aprovações
    path("aprovacoes/", views.view_aprovacoes, name="aprovacoes"),
    path("aprovacoes/<int:request_id>/", views.view_aprovar, name="aprovar"),
    # Histórico
    path("historico/", views.view_historico, name="historico"),
    path("historico/<int:move_id>/excluir/", views.view_excluir_move, name="excluir_move"),
    # Manutenção
    path("manutencao/", views.view_manutencao, name="manutencao"),
    path("manutencao/sync/", views.view_sync_catalogo, name="sync_catalogo"),
    path("manutencao/rebuild/", views.view_rebuild_variacoes, name="rebuild_variacoes"),
    path("manutencao/limpeza/", views.view_limpeza, name="limpeza"),
    path("manutencao/pipeline/", views.view_processar_pipeline, name="processar_pipeline"),
    # Preços
    path("precos/", views.view_precos, name="precos"),
    path("precos/aplicar/", views.view_aplicar_precos, name="aplicar_precos"),
    path("precos/historico/", views.view_historico_precos, name="historico_precos"),
    path("precos/historico/<int:preco_id>/excluir/", views.view_excluir_preco, name="excluir_preco"),
    path("precos/csv-atacado/", views.view_download_csv_atacado, name="download_csv_atacado"),
    path("precos/job/<str:job_id>/status/", views.view_job_precos_status, name="job_precos_status"),
    path("precos/job/<str:job_id>/csv/", views.view_download_csv_job, name="download_csv_job"),
    path("htmx/precos/cores/", views.htmx_cores_por_modelo, name="htmx_precos_cores"),
    path("htmx/precos/modelos/", views.htmx_buscar_modelos_precos, name="htmx_modelos_precos"),
    path("precos/upload-atacado/", views.view_upload_atacado, name="upload_atacado"),
    path("precos/exportar-atacado/", views.view_exportar_atacado_csv, name="exportar_atacado_csv"),
    path("precos/exportar-atacado-ultimas/", views.view_exportar_atacado_ultimas, name="exportar_atacado_ultimas"),
    path("resumo/", views.view_resumo_produtos, name="resumo"),
]
