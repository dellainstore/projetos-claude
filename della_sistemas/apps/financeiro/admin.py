from django.contrib import admin

from apps.financeiro.models import (
    AjusteSaldo,
    AnexoFinanceiro,
    Baixa,
    CategoriaFinanceira,
    CentroCusto,
    ContaBancaria,
    ContatoFinanceiro,
    FormaPagamento,
    LancamentoFinanceiro,
    LogAuditoriaFinanceiro,
    MovimentoConta,
    OcorrenciaRecorrencia,
    OperacaoFinanceira,
    Parcela,
    RegraRecorrencia,
    TagFinanceira,
    Transferencia,
)


@admin.register(OperacaoFinanceira)
class OperacaoFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "status")


@admin.register(ContaBancaria)
class ContaBancariaAdmin(admin.ModelAdmin):
    list_display = ("nome", "banco", "tipo_conta", "saldo_inicial", "ativa", "incluir_consolidado")
    list_filter = ("tipo_conta", "ativa")


@admin.register(CategoriaFinanceira)
class CategoriaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria_pai", "natureza", "ordem", "ativa")
    list_filter = ("natureza", "ativa")


@admin.register(CentroCusto)
class CentroCustoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "ordem")


@admin.register(ContatoFinanceiro)
class ContatoFinanceiroAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "documento", "ativo")
    list_filter = ("tipo", "ativo")
    search_fields = ("nome", "documento")


@admin.register(FormaPagamento)
class FormaPagamentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "ordem")


@admin.register(TagFinanceira)
class TagFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("nome", "operacao")


@admin.register(LancamentoFinanceiro)
class LancamentoFinanceiroAdmin(admin.ModelAdmin):
    list_display = (
        "descricao", "tipo", "categoria", "valor_original", "data_vencimento",
        "estado_estrutural",
    )
    list_filter = ("tipo", "estado_estrutural", "categoria")
    search_fields = ("descricao", "numero_documento")
    date_hierarchy = "data_vencimento"


@admin.register(Parcela)
class ParcelaAdmin(admin.ModelAdmin):
    list_display = ("lancamento", "numero", "valor", "data_vencimento", "estado_estrutural")
    list_filter = ("estado_estrutural",)


@admin.register(Baixa)
class BaixaAdmin(admin.ModelAdmin):
    list_display = (
        "parcela", "valor_principal", "juros", "multa", "desconto",
        "valor_movimentado", "data", "conta", "estornada",
    )
    list_filter = ("estornada", "conta")


@admin.register(Transferencia)
class TransferenciaAdmin(admin.ModelAdmin):
    list_display = ("conta_origem", "conta_destino", "valor", "data", "estornada")
    list_filter = ("estornada",)


@admin.register(RegraRecorrencia)
class RegraRecorrenciaAdmin(admin.ModelAdmin):
    list_display = ("descricao", "tipo_lancamento", "frequencia", "ativa", "pausada", "janela_gerada_ate")
    list_filter = ("frequencia", "ativa", "pausada")


@admin.register(OcorrenciaRecorrencia)
class OcorrenciaRecorrenciaAdmin(admin.ModelAdmin):
    list_display = ("regra", "data_ocorrencia", "lancamento")


@admin.register(AjusteSaldo)
class AjusteSaldoAdmin(admin.ModelAdmin):
    list_display = ("conta", "valor", "usuario", "criado_em")


@admin.register(MovimentoConta)
class MovimentoContaAdmin(admin.ModelAdmin):
    list_display = ("conta", "data", "valor", "evento_chave")
    list_filter = ("conta",)
    search_fields = ("evento_chave",)


@admin.register(LogAuditoriaFinanceiro)
class LogAuditoriaFinanceiroAdmin(admin.ModelAdmin):
    list_display = ("entidade", "objeto_id", "acao", "usuario", "criado_em")
    list_filter = ("entidade", "acao")


@admin.register(AnexoFinanceiro)
class AnexoFinanceiroAdmin(admin.ModelAdmin):
    list_display = ("nome_original", "lancamento", "tamanho", "enviado_por", "enviado_em")
