from django.contrib import admin

from apps.pedidos.models import BaixaPedido, HistoricoSituacaoPedido, PedidoBling


@admin.register(PedidoBling)
class PedidoBlingAdmin(admin.ModelAdmin):
    list_display  = ["numero", "cliente_nome", "situacao_nome", "data_pedido", "valor_total", "atualizado_em"]
    list_filter   = ["situacao_nome"]
    search_fields = ["numero", "cliente_nome", "bling_id"]
    readonly_fields = ["bling_id", "atualizado_em", "criado_em"]


@admin.register(HistoricoSituacaoPedido)
class HistoricoSituacaoAdmin(admin.ModelAdmin):
    list_display  = ["pedido", "situacao_nome", "registrado_em"]
    readonly_fields = ["registrado_em"]


@admin.register(BaixaPedido)
class BaixaPedidoAdmin(admin.ModelAdmin):
    list_display  = ["pedido", "confirmado_por", "confirmado_em"]
    readonly_fields = ["confirmado_em"]
