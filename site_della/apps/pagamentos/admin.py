from django.contrib import admin
from django.utils.html import format_html
from .models import Pagamento

STATUS_CORES = {
    'pendente':  '#f39c12',
    'aprovado':  '#27ae60',
    'recusado':  '#e74c3c',
    'cancelado': '#e74c3c',
    'estornado': '#8e44ad',
}


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ('pedido', 'gateway', 'forma', 'parcelas', 'valor_formatado', 'badge_status', 'criado_em')
    list_filter = ('status', 'gateway', 'forma')
    search_fields = ('pedido__numero', 'gateway_id', 'pedido__email')
    date_hierarchy = 'criado_em'
    ordering = ('-criado_em',)
    readonly_fields = ('pedido', 'gateway', 'gateway_id', 'forma', 'parcelas', 'valor', 'dados_retorno', 'criado_em', 'atualizado_em')

    fieldsets = (
        ('Pagamento', {
            'fields': ('pedido', 'gateway', 'gateway_id', 'forma', 'parcelas', 'valor', 'status'),
        }),
        ('Resposta do gateway', {
            'fields': ('dados_retorno',),
            'classes': ('collapse',),
        }),
        ('Datas', {
            'fields': ('criado_em', 'atualizado_em'),
            'classes': ('collapse',),
        }),
    )

    def badge_status(self, obj):
        cor = STATUS_CORES.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 8px;'
            'border-radius:3px;font-size:11px;">{}</span>',
            cor,
            obj.get_status_display(),
        )
    badge_status.short_description = 'Status'

    def valor_formatado(self, obj):
        v = f'{obj.valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return format_html('R$ {}', v)
    valor_formatado.short_description = 'Valor'
