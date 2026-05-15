from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from apps.core_utils.admin_mixin import DellaAdminMixin
from .models import Pagamento, CartaoSalvo

STATUS_CORES = {
    'pendente':  '#f39c12',
    'aprovado':  '#27ae60',
    'recusado':  '#e74c3c',
    'cancelado': '#e74c3c',
    'estornado': '#8e44ad',
}


@admin.register(Pagamento)
class PagamentoAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = ('pedido', 'gateway', 'forma', 'parcelas', 'valor_formatado', 'badge_status', 'criado_em', 'acoes_linha')
    list_display_links = ('pedido',)
    list_filter = ('status', 'gateway', 'forma')
    search_fields = ('pedido__numero', 'gateway_id', 'pedido__email')
    date_hierarchy = 'criado_em'
    ordering = ('-criado_em',)
    readonly_fields = ('pedido', 'gateway', 'gateway_id', 'forma', 'parcelas', 'valor', 'dados_retorno', 'criado_em', 'atualizado_em')

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:pagamentos_pagamento_change', args=[obj.pk])
        delete_url = reverse('admin:pagamentos_pagamento_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este pagamento?')
    acoes_linha.short_description = 'Ações'

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


@admin.register(CartaoSalvo)
class CartaoSalvoAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display  = ('cliente', 'bandeira_display', 'ultimos_4', 'nome_titular', 'validade', 'status_validade', 'ativo', 'criado_em', 'acoes_linha')
    list_display_links = ('cliente',)
    list_filter   = ('bandeira', 'ativo')
    search_fields = ('cliente__email', 'nome_titular', 'ultimos_4')
    date_hierarchy = 'criado_em'
    ordering      = ('-criado_em',)
    readonly_fields = ('cliente', 'token_pagbank', 'ultimos_4', 'nome_titular',
                       'bandeira', 'mes_expiracao', 'ano_expiracao', 'criado_em')

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:pagamentos_cartaosalvo_change', args=[obj.pk])
        delete_url = reverse('admin:pagamentos_cartaosalvo_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este cartão salvo?')
    acoes_linha.short_description = 'Ações'

    def bandeira_display(self, obj):
        icones = {
            'visa': '💳', 'mastercard': '💳', 'elo': '💳',
            'amex': '💳', 'hipercard': '💳', 'outro': '💳',
        }
        return format_html('<strong>{}</strong>', obj.get_bandeira_display())
    bandeira_display.short_description = 'Bandeira'

    def validade(self, obj):
        return obj.validade_display
    validade.short_description = 'Validade'

    def status_validade(self, obj):
        if obj.esta_vencido:
            return format_html(
                '<span style="background:#e74c3c;color:#fff;padding:2px 7px;'
                'border-radius:3px;font-size:11px;">Vencido</span>'
            )
        return format_html(
            '<span style="background:#27ae60;color:#fff;padding:2px 7px;'
            'border-radius:3px;font-size:11px;">Válido</span>'
        )
    status_validade.short_description = 'Status'
