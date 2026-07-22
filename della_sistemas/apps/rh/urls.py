from django.urls import path

from apps.rh.views import (
    afastamentos as v_afast,
    aprovacoes as v_aprov,
    beneficios as v_beneficios,
    colaboradores as v_colab,
    comissao as v_comissao,
    correcoes as v_correcoes,
    escalas as v_escalas,
    ferias as v_ferias,
    jornada as v_jornada,
    parametros as v_param,
    ponto as v_ponto,
    registros as v_registros,
    salarios as v_salarios,
)

app_name = "rh"

urlpatterns = [
    # Colaboradores
    path("colaboradores/", v_colab.view_colaboradores, name="colaboradores"),
    path("colaboradores/novo/", v_colab.view_colaborador_form, name="colaborador_novo"),
    path("colaboradores/<int:pk>/editar/", v_colab.view_colaborador_form, name="colaborador_editar"),
    path("colaboradores/<int:pk>/toggle/", v_colab.view_colaborador_toggle, name="colaborador_toggle"),

    # Escalas
    path("escalas/", v_escalas.view_escalas, name="escalas"),
    path("escalas/novo/", v_escalas.view_escala_form, name="escala_novo"),
    path("escalas/<int:pk>/editar/", v_escalas.view_escala_form, name="escala_editar"),
    path("escalas/<int:pk>/excluir/", v_escalas.view_escala_excluir, name="escala_excluir"),
    path("escalas/excecoes/", v_escalas.view_escala_excecoes, name="escala_excecoes"),
    path("escalas/excecoes/<int:pk>/excluir/", v_escalas.view_escala_excecao_excluir, name="escala_excecao_excluir"),

    # Salários
    path("salarios/resumo/", v_salarios.view_folha_resumo, name="folha_resumo"),
    path("salarios/detalhada/", v_salarios.view_folha_detalhada, name="folha_detalhada"),
    path("salarios/", v_salarios.view_salarios, name="salarios"),
    path("salarios/evento/novo/", v_salarios.view_evento_novo, name="evento_novo"),
    path("salarios/evento/<int:pk>/excluir/", v_salarios.view_evento_excluir, name="evento_excluir"),
    path("salarios/recorrencia/<int:pk>/encerrar/", v_salarios.view_recorrencia_encerrar, name="recorrencia_encerrar"),
    path("salarios/recorrencia/<int:pk>/excluir/", v_salarios.view_recorrencia_excluir, name="recorrencia_excluir"),
    path("salarios/pagamentos/salvar/", v_salarios.view_pagamentos_salvar, name="pagamentos_salvar"),

    # Comissão
    path("comissao/", v_comissao.view_comissao, name="comissao"),
    path("comissao/incluir/", v_comissao.view_comissao_incluir, name="comissao_incluir"),
    path("comissao/<int:colaborador_id>/pdf/", v_comissao.view_comissao_pdf, name="comissao_pdf"),
    path("comissao/<int:colaborador_id>/<int:pedido_id>/salvar/", v_comissao.view_comissao_salvar, name="comissao_salvar"),

    # Férias
    path("ferias/", v_ferias.view_ferias, name="ferias"),
    path("ferias/pdf/", v_ferias.view_ferias_pdf, name="ferias_pdf"),
    path("ferias/periodo/novo/", v_ferias.view_periodo_novo, name="periodo_novo"),
    path("ferias/periodo/<int:pk>/excluir/", v_ferias.view_periodo_excluir, name="periodo_excluir"),
    path("ferias/periodo/<int:pk>/abono/", v_ferias.view_abono_salvar, name="abono_salvar"),
    path("ferias/gozo/novo/", v_ferias.view_gozo_novo, name="gozo_novo"),
    path("ferias/gozo/<int:pk>/excluir/", v_ferias.view_gozo_excluir, name="gozo_excluir"),

    # Afastamentos (faltas, atestados, folgas — férias ficam no módulo Férias)
    path("afastamentos/", v_afast.view_afastamentos, name="afastamentos"),
    path("afastamentos/novo/", v_afast.view_afastamento_novo, name="afastamento_novo"),
    path("afastamentos/<int:pk>/editar/", v_afast.view_afastamento_editar, name="afastamento_editar"),
    path("afastamentos/<int:pk>/salvar/", v_afast.view_afastamento_salvar, name="afastamento_salvar"),
    path("afastamentos/<int:pk>/anexo/", v_afast.view_afastamento_anexo, name="afastamento_anexo"),
    path("afastamentos/anexo/<int:pk>/", v_afast.view_afastamento_anexo_item, name="afastamento_anexo_item"),
    path("afastamentos/<int:pk>/excluir/", v_afast.view_afastamento_excluir, name="afastamento_excluir"),

    # Benefícios (VT, VA, VR, plano de saúde…)
    path("beneficios/", v_beneficios.view_beneficios, name="beneficios"),
    path("beneficios/tipo/novo/", v_beneficios.view_beneficio_tipo_novo, name="beneficio_tipo_novo"),
    path("beneficios/tipo/<int:pk>/toggle/", v_beneficios.view_beneficio_tipo_toggle, name="beneficio_tipo_toggle"),

    # Controle de Ponto — bater o próprio ponto
    path("ponto/", v_ponto.view_ponto, name="ponto"),
    path("ponto/bater/", v_ponto.view_bater, name="ponto_bater"),
    path("ponto/relatorio/", v_ponto.view_relatorio, name="ponto_relatorio"),

    # Controle de Ponto — Minhas Correções (funcionário propõe horários)
    path("ponto/correcoes/", v_correcoes.view_correcoes, name="correcoes"),
    path("ponto/correcoes/propor/", v_correcoes.view_propor_correcao, name="propor_correcao"),

    # Controle de Ponto — Aprovações (gestor)
    path("ponto/aprovacoes/", v_aprov.view_aprovacoes, name="aprovacoes"),
    path("ponto/aprovacoes/<int:pk>/aprovar/", v_aprov.view_correcao_aprovar, name="correcao_aprovar"),
    path("ponto/aprovacoes/<int:pk>/rejeitar/", v_aprov.view_correcao_rejeitar, name="correcao_rejeitar"),
    path("ponto/aprovacoes/<int:pk>/excluir/", v_aprov.view_correcao_excluir, name="correcao_excluir"),

    # Controle de Ponto — Jornada (gestor)
    path("ponto/jornada/", v_jornada.view_jornada, name="jornada"),
    path("ponto/jornada/salvar/", v_jornada.view_jornada_salvar, name="jornada_salvar"),
    path("ponto/jornada/dia/excluir/", v_jornada.view_dia_excluir, name="dia_excluir"),
    path("ponto/jornada/dia/abonar/", v_jornada.view_dia_abonar, name="dia_abonar"),
    path("ponto/jornada/dia/abono/excluir/", v_jornada.view_dia_abono_excluir, name="dia_abono_excluir"),
    path("ponto/jornada/pdf/", v_jornada.view_jornada_pdf, name="jornada_pdf"),

    # Controle de Ponto — Registros (auditoria de origem)
    path("ponto/registros/", v_registros.view_registros, name="registros"),
    path("ponto/registros/<int:pk>/excluir/", v_registros.view_registro_excluir, name="registro_excluir"),
    path("ponto/registros/abono/<int:pk>/excluir/", v_registros.view_abono_excluir, name="abono_excluir"),

    # Controle de Ponto — Parâmetros (gestor)
    path("ponto/parametros/", v_param.view_parametros, name="parametros"),
    path("ponto/parametros/tolerancia/", v_param.view_tolerancia_salvar, name="tolerancia_salvar"),
    path("ponto/parametros/vinculos/", v_param.view_vinculos_salvar, name="vinculos_salvar"),
    path("ponto/parametros/loja/novo/", v_param.view_loja_form, name="loja_novo"),
    path("ponto/parametros/loja/<int:pk>/editar/", v_param.view_loja_form, name="loja_editar"),
    path("ponto/parametros/loja/<int:pk>/excluir/", v_param.view_loja_delete, name="loja_delete"),
]
