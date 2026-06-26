from .incluir import (
    view_incluir, view_incluir_submit,
    htmx_buscar_bases, htmx_buscar_cores, htmx_buscar_tamanhos, htmx_buscar_templates,
    view_cancelar_request, view_editar_request,
)
from .aprovacoes import view_aprovacoes, view_aprovar
from .historico import view_historico, view_excluir_move
from .manutencao import view_manutencao, view_sync_catalogo, view_rebuild_variacoes, view_limpeza, view_processar_pipeline
from .resumo import view_resumo_produtos
from .precos import (
    view_precos, htmx_cores_por_modelo, view_aplicar_precos,
    view_historico_precos, view_download_csv_atacado,
    htmx_buscar_modelos_precos, view_upload_atacado,
    view_exportar_atacado_csv, view_exportar_atacado_ultimas,
    view_excluir_preco,
    view_job_precos_status, view_download_csv_job,
)
