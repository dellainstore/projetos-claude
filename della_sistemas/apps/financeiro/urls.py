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

    # ── Cartões (Fase 1B) ────────────────────────────────────────────────
    path("private-label/cartoes/", views.pl_cartoes, name="pl_cartoes"),
    path("private-label/htmx/cartoes/lista/", views.pl_htmx_cartoes_lista, name="pl_htmx_cartoes_lista"),
    path("private-label/htmx/cartoes/form/", views.pl_htmx_cartao_form, name="pl_htmx_cartao_form"),
    path("private-label/htmx/cartoes/<int:pk>/form/", views.pl_htmx_cartao_form, name="pl_htmx_cartao_form_editar"),
    path("private-label/htmx/cartoes/salvar/", views.pl_htmx_cartao_salvar, name="pl_htmx_cartao_salvar"),
    path("private-label/cartoes/<int:pk>/", views.pl_cartao_detalhe, name="pl_cartao_detalhe"),
    path("private-label/htmx/cartoes/<int:pk>/conteudo/", views.pl_htmx_cartao_detalhe_conteudo, name="pl_htmx_cartao_detalhe_conteudo"),

    path("private-label/htmx/compras-cartao/form/", views.pl_htmx_compra_cartao_form, name="pl_htmx_compra_cartao_form"),
    path("private-label/htmx/compras-cartao/salvar/", views.pl_htmx_compra_cartao_salvar, name="pl_htmx_compra_cartao_salvar"),
    path("private-label/htmx/compras-cartao/<int:pk>/cancelar/", views.pl_htmx_compra_cartao_cancelar, name="pl_htmx_compra_cartao_cancelar"),

    path("private-label/htmx/faturas/<int:pk>/pagar/form/", views.pl_htmx_fatura_pagar_form, name="pl_htmx_fatura_pagar_form"),
    path("private-label/htmx/faturas/<int:pk>/pagar/salvar/", views.pl_htmx_fatura_pagar_salvar, name="pl_htmx_fatura_pagar_salvar"),
    path("private-label/htmx/pagamentos-fatura/<int:pk>/estornar/", views.pl_htmx_fatura_pagamento_estornar, name="pl_htmx_fatura_pagamento_estornar"),

    # ── Fluxo de Caixa (Fase 1C) ─────────────────────────────────────────
    path("private-label/fluxo-caixa/", views.pl_fluxo_caixa, name="pl_fluxo_caixa"),

    # ── DRE (Fase 1C) ────────────────────────────────────────────────────
    path("private-label/dre/", views.pl_dre, name="pl_dre"),
    path("private-label/dre/exportar/", views.pl_dre_exportar_csv, name="pl_dre_exportar_csv"),

    # ── Investimentos (Fase 2) ───────────────────────────────────────────
    path("private-label/investimentos/", views.pl_investimentos, name="pl_investimentos"),
    path("private-label/htmx/investimentos/lista/", views.pl_htmx_investimentos_lista, name="pl_htmx_investimentos_lista"),
    path("private-label/htmx/contas-investimento/form/", views.pl_htmx_conta_investimento_form, name="pl_htmx_conta_investimento_form"),
    path("private-label/htmx/contas-investimento/<int:pk>/form/", views.pl_htmx_conta_investimento_form, name="pl_htmx_conta_investimento_form_editar"),
    path("private-label/htmx/contas-investimento/salvar/", views.pl_htmx_conta_investimento_salvar, name="pl_htmx_conta_investimento_salvar"),
    path("private-label/htmx/investimento-transacao/form/", views.pl_htmx_investimento_transacao_form, name="pl_htmx_investimento_transacao_form"),
    path("private-label/htmx/investimento-transacao/salvar/", views.pl_htmx_investimento_transacao_salvar, name="pl_htmx_investimento_transacao_salvar"),
    path("private-label/htmx/investimento-transacao/<int:pk>/estornar/", views.pl_htmx_investimento_transacao_estornar, name="pl_htmx_investimento_transacao_estornar"),

    # ── Conciliação bancária (Fase 3) ────────────────────────────────────
    path("private-label/conciliacao/", views.pl_conciliacao, name="pl_conciliacao"),
    path("private-label/conciliacao/<int:pk>/", views.pl_conciliacao_detalhe, name="pl_conciliacao_detalhe"),
    path("private-label/htmx/conciliacao/<int:pk>/conteudo/", views.pl_htmx_conciliacao_detalhe_conteudo, name="pl_htmx_conciliacao_detalhe_conteudo"),
    path("private-label/htmx/conciliacao/<int:pk>/confirmar/", views.pl_htmx_conciliacao_confirmar, name="pl_htmx_conciliacao_confirmar"),
    path("private-label/htmx/conciliacao/<int:pk>/rejeitar/", views.pl_htmx_conciliacao_rejeitar, name="pl_htmx_conciliacao_rejeitar"),
    path("private-label/htmx/conciliacao/<int:pk>/desfazer/", views.pl_htmx_conciliacao_desfazer, name="pl_htmx_conciliacao_desfazer"),
    path("private-label/htmx/conciliacao/item/<int:pk>/ignorar/", views.pl_htmx_item_ignorar, name="pl_htmx_item_ignorar"),
    path("private-label/htmx/conciliacao/item/<int:pk>/vincular/form/", views.pl_htmx_item_vincular_form, name="pl_htmx_item_vincular_form"),
    path("private-label/htmx/conciliacao/item/<int:pk>/vincular/salvar/", views.pl_htmx_item_vincular_salvar, name="pl_htmx_item_vincular_salvar"),
]
