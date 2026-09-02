from django.urls import path

from apps.financeiro import views

app_name = "financeiro"

urlpatterns = [
    path("dashboard-faturamento/", views.view_dashboard_faturamento, name="dashboard_faturamento"),
    path("htmx/dashboard-faturamento/", views.htmx_dashboard_dados, name="htmx_dashboard_faturamento"),

    # ── Private Label ────────────────────────────────────────────────
    path("private-label/", views.pl_home, name="pl_home"),

    # Configurações (contas, categorias, centros de custo, contatos, formas
    # de pagamento, recorrências) — 1 rota, abas via ?aba=
    path("private-label/configuracoes/", views.pl_configuracoes, name="pl_configuracoes"),

    path("private-label/htmx/contas/form/", views.pl_htmx_conta_form, name="pl_htmx_conta_form"),
    path("private-label/htmx/contas/<int:pk>/form/", views.pl_htmx_conta_form, name="pl_htmx_conta_form_editar"),
    path("private-label/htmx/contas/salvar/", views.pl_htmx_conta_salvar, name="pl_htmx_conta_salvar"),
    path("private-label/htmx/contas/lista/", views.pl_htmx_contas_lista, name="pl_htmx_contas_lista"),

    path("private-label/htmx/categorias/form/", views.pl_htmx_categoria_form, name="pl_htmx_categoria_form"),
    path("private-label/htmx/categorias/<int:pk>/form/", views.pl_htmx_categoria_form, name="pl_htmx_categoria_form_editar"),
    path("private-label/htmx/categorias/salvar/", views.pl_htmx_categoria_salvar, name="pl_htmx_categoria_salvar"),
    path("private-label/htmx/categorias/lista/", views.pl_htmx_categorias_lista, name="pl_htmx_categorias_lista"),

    path("private-label/htmx/centros-custo/form/", views.pl_htmx_centro_custo_form, name="pl_htmx_centro_custo_form"),
    path("private-label/htmx/centros-custo/<int:pk>/form/", views.pl_htmx_centro_custo_form, name="pl_htmx_centro_custo_form_editar"),
    path("private-label/htmx/centros-custo/salvar/", views.pl_htmx_centro_custo_salvar, name="pl_htmx_centro_custo_salvar"),
    path("private-label/htmx/centros-custo/lista/", views.pl_htmx_centros_custo_lista, name="pl_htmx_centros_custo_lista"),

    path("private-label/htmx/contatos/form/", views.pl_htmx_contato_form, name="pl_htmx_contato_form"),
    path("private-label/htmx/contatos/<int:pk>/form/", views.pl_htmx_contato_form, name="pl_htmx_contato_form_editar"),
    path("private-label/htmx/contatos/salvar/", views.pl_htmx_contato_salvar, name="pl_htmx_contato_salvar"),
    path("private-label/htmx/contatos/lista/", views.pl_htmx_contatos_lista, name="pl_htmx_contatos_lista"),

    path("private-label/htmx/formas-pagamento/form/", views.pl_htmx_forma_pagamento_form, name="pl_htmx_forma_pagamento_form"),
    path("private-label/htmx/formas-pagamento/<int:pk>/form/", views.pl_htmx_forma_pagamento_form, name="pl_htmx_forma_pagamento_form_editar"),
    path("private-label/htmx/formas-pagamento/salvar/", views.pl_htmx_forma_pagamento_salvar, name="pl_htmx_forma_pagamento_salvar"),
    path("private-label/htmx/formas-pagamento/lista/", views.pl_htmx_formas_pagamento_lista, name="pl_htmx_formas_pagamento_lista"),

    path("private-label/htmx/recorrencias/form/", views.pl_htmx_recorrencia_form, name="pl_htmx_recorrencia_form"),
    path("private-label/htmx/recorrencias/salvar/", views.pl_htmx_recorrencia_salvar, name="pl_htmx_recorrencia_salvar"),
    path("private-label/htmx/recorrencias/<int:pk>/pausar/", views.pl_htmx_recorrencia_pausar, name="pl_htmx_recorrencia_pausar"),
    path("private-label/htmx/recorrencias/lista/", views.pl_htmx_recorrencias_lista, name="pl_htmx_recorrencias_lista"),

    # Lançamentos
    path("private-label/lancamentos/", views.pl_lancamentos, name="pl_lancamentos"),
    path("private-label/htmx/lancamentos/lista/", views.pl_htmx_lancamentos_lista, name="pl_htmx_lancamentos_lista"),
    path("private-label/htmx/lancamentos/form/", views.pl_htmx_lancamento_form, name="pl_htmx_lancamento_form"),
    path("private-label/htmx/lancamentos/<int:pk>/form/", views.pl_htmx_lancamento_form, name="pl_htmx_lancamento_form_editar"),
    path("private-label/htmx/lancamentos/salvar/", views.pl_htmx_lancamento_salvar, name="pl_htmx_lancamento_salvar"),
    path("private-label/htmx/lancamentos/<int:pk>/duplicar/", views.pl_htmx_lancamento_duplicar, name="pl_htmx_lancamento_duplicar"),
    path("private-label/htmx/lancamentos/<int:pk>/cancelar/", views.pl_htmx_lancamento_cancelar, name="pl_htmx_lancamento_cancelar"),
    path("private-label/htmx/lancamentos/<int:pk>/deletar/", views.pl_htmx_lancamento_deletar, name="pl_htmx_lancamento_deletar"),
    path("private-label/htmx/lancamentos/<int:pk>/detalhe/", views.pl_htmx_lancamento_detalhe, name="pl_htmx_lancamento_detalhe"),
    path("private-label/htmx/lancamentos/<int:pk>/anexo/", views.pl_htmx_anexo_upload, name="pl_htmx_anexo_upload"),
    path("private-label/anexos/<int:pk>/", views.pl_anexo_download, name="pl_anexo_download"),

    # Baixas
    path("private-label/htmx/parcelas/<int:pk>/baixar/form/", views.pl_htmx_baixa_form, name="pl_htmx_baixa_form"),
    path("private-label/htmx/parcelas/<int:pk>/baixar/salvar/", views.pl_htmx_baixa_salvar, name="pl_htmx_baixa_salvar"),
    path("private-label/htmx/baixas/<int:pk>/estornar/", views.pl_htmx_baixa_estornar, name="pl_htmx_baixa_estornar"),
    path("private-label/htmx/lancamentos/baixa-lote/form/", views.pl_htmx_baixa_lote_form, name="pl_htmx_baixa_lote_form"),
    path("private-label/htmx/lancamentos/baixa-lote/", views.pl_htmx_baixa_lote, name="pl_htmx_baixa_lote"),
    path("private-label/htmx/lancamentos/deletar-lote/form/", views.pl_htmx_lancamento_deletar_lote_form, name="pl_htmx_lancamento_deletar_lote_form"),
    path("private-label/htmx/lancamentos/deletar-lote/", views.pl_htmx_lancamento_deletar_lote, name="pl_htmx_lancamento_deletar_lote"),

    # Transferências
    path("private-label/htmx/transferencias/form/", views.pl_htmx_transferencia_form, name="pl_htmx_transferencia_form"),
    path("private-label/htmx/transferencias/salvar/", views.pl_htmx_transferencia_salvar, name="pl_htmx_transferencia_salvar"),
    path("private-label/htmx/transferencias/<int:pk>/estornar/", views.pl_htmx_transferencia_estornar, name="pl_htmx_transferencia_estornar"),

    # Dashboard
    path("private-label/dashboard/", views.pl_dashboard, name="pl_dashboard"),

    # Ajuste de saldo (ação sensível)
    path("private-label/htmx/ajuste-saldo/form/", views.pl_htmx_ajuste_saldo_form, name="pl_htmx_ajuste_saldo_form"),
    path("private-label/htmx/ajuste-saldo/salvar/", views.pl_htmx_ajuste_saldo_salvar, name="pl_htmx_ajuste_saldo_salvar"),
]
