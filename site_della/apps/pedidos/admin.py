import logging

from django.contrib import admin
from django.utils.html import format_html

from .models import Pedido, ItemPedido, HistoricoPedido

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    fields = ('nome_produto', 'variacao_desc', 'sku', 'quantidade', 'preco_unitario', 'subtotal')
    readonly_fields = ('nome_produto', 'variacao_desc', 'sku', 'quantidade', 'preco_unitario', 'subtotal')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class HistoricoPedidoInline(admin.TabularInline):
    model = HistoricoPedido
    extra = 0
    fields = ('criado_em', 'status_anterior', 'status_novo', 'observacao')
    readonly_fields = ('criado_em', 'status_anterior', 'status_novo', 'observacao')
    ordering = ('-criado_em',)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Pedido
# ---------------------------------------------------------------------------

STATUS_CORES = {
    'aguardando_pagamento': '#f39c12',
    'pagamento_confirmado': '#27ae60',
    'em_separacao':         '#2980b9',
    'enviado':              '#8e44ad',
    'entregue':             '#27ae60',
    'cancelado':            '#e74c3c',
    'estornado':            '#e74c3c',
}


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = (
        'numero', 'nome_completo', 'email', 'badge_status', 'forma_pagamento',
        'total_formatado', 'badge_bling', 'codigo_rastreio', 'criado_em',
    )
    list_filter = ('status', 'forma_pagamento', 'gateway', 'estado')
    search_fields = ('numero', 'nome_completo', 'email', 'cpf', 'codigo_rastreio', 'bling_pedido_id')
    date_hierarchy = 'criado_em'
    ordering = ('-criado_em',)

    readonly_fields = (
        'numero', 'nome_completo', 'email', 'cpf', 'telefone',
        'cep_entrega', 'logradouro', 'numero_entrega', 'complemento',
        'bairro', 'cidade', 'estado',
        'subtotal', 'desconto', 'frete', 'total',
        'gateway', 'gateway_id', 'parcelas', 'forma_pagamento',
        'bling_pedido_id', 'bling_nfe_id', 'nfe_chave',
        'criado_em', 'atualizado_em',
    )

    fieldsets = (
        ('Pedido', {
            'fields': ('numero', 'status', 'criado_em', 'atualizado_em'),
        }),
        ('Cliente', {
            'fields': ('cliente', 'nome_completo', 'email', 'cpf', 'telefone'),
        }),
        ('Endereço de entrega', {
            'fields': (
                'cep_entrega', 'logradouro', 'numero_entrega',
                'complemento', 'bairro', 'cidade', 'estado',
            ),
            'classes': ('collapse',),
        }),
        ('Valores', {
            'fields': ('subtotal', 'desconto', 'frete', 'total'),
        }),
        ('Pagamento', {
            'fields': ('forma_pagamento', 'gateway', 'gateway_id', 'parcelas'),
        }),
        ('Entrega', {
            'fields': ('codigo_rastreio', 'transportadora'),
        }),
        ('Bling / NF-e', {
            'fields': ('bling_pedido_id', 'bling_nfe_id', 'nfe_chave'),
            'classes': ('collapse',),
        }),
        ('Observações', {
            'fields': ('observacao_cliente', 'observacao_interna'),
        }),
    )

    inlines = [ItemPedidoInline, HistoricoPedidoInline]
    actions = [
        'marcar_pagamento_confirmado',
        'marcar_em_separacao',
        'marcar_enviado',
        'marcar_entregue',
        'marcar_cancelado',
        'enviar_ao_bling',
        'emitir_nfe',
    ]

    def badge_status(self, obj):
        cor = STATUS_CORES.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 8px;'
            'border-radius:3px;font-size:11px;white-space:nowrap;">{}</span>',
            cor,
            obj.get_status_display(),
        )
    badge_status.short_description = 'Status'

    def total_formatado(self, obj):
        v = f'{obj.total:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return format_html('R$ {}', v)
    total_formatado.short_description = 'Total'

    def badge_bling(self, obj):
        if obj.bling_nfe_id:
            return format_html(
                '<span style="background:#27ae60;color:#fff;padding:2px 6px;'
                'border-radius:3px;font-size:11px;" title="NF-e emitida">NF-e ✓</span>'
            )
        if obj.bling_pedido_id:
            return format_html(
                '<span style="background:#2980b9;color:#fff;padding:2px 6px;'
                'border-radius:3px;font-size:11px;" title="Enviado ao Bling">Bling ✓</span>'
            )
        return format_html(
            '<span style="color:#aaa;font-size:11px;">—</span>'
        )
    badge_bling.short_description = 'Bling'

    # ── Ações de status ────────────────────────────────────────────────────────

    def _mudar_status(self, request, queryset, novo_status, label, enviar_bling=False):
        atualizados = 0
        for pedido in queryset:
            if pedido.status != novo_status:
                HistoricoPedido.objects.create(
                    pedido=pedido,
                    status_anterior=pedido.status,
                    status_novo=novo_status,
                    observacao=f'Alterado pelo admin ({request.user.email})',
                )
                pedido.status = novo_status
                pedido.save(update_fields=['status', 'atualizado_em'])
                atualizados += 1

                if enviar_bling and novo_status == 'pagamento_confirmado':
                    self._tentar_enviar_bling(request, pedido)

        self.message_user(request, f'{atualizados} pedido(s) marcado(s) como "{label}".')

    def _tentar_enviar_bling(self, request, pedido):
        """Envia o pedido ao Bling silenciosamente; avisa se falhar."""
        try:
            from apps.bling.services import enviar_pedido_bling
            ok = enviar_pedido_bling(pedido)
            if ok:
                self.message_user(
                    request,
                    f'Pedido {pedido.numero} enviado ao Bling com sucesso.',
                )
            else:
                self.message_user(
                    request,
                    f'Atenção: pedido {pedido.numero} não pôde ser enviado ao Bling. Verifique os Logs Bling.',
                    level='WARNING',
                )
        except Exception as exc:
            logger.error('Erro ao enviar pedido %s ao Bling: %s', pedido.numero, exc)
            self.message_user(
                request,
                f'Erro ao enviar pedido {pedido.numero} ao Bling: {exc}',
                level='ERROR',
            )

    @admin.action(description='→ Pagamento confirmado (+ envio automático ao Bling)')
    def marcar_pagamento_confirmado(self, request, queryset):
        self._mudar_status(request, queryset, 'pagamento_confirmado', 'Pagamento Confirmado', enviar_bling=True)

    @admin.action(description='→ Em separação')
    def marcar_em_separacao(self, request, queryset):
        self._mudar_status(request, queryset, 'em_separacao', 'Em Separação')

    @admin.action(description='→ Enviado')
    def marcar_enviado(self, request, queryset):
        self._mudar_status(request, queryset, 'enviado', 'Enviado')

    @admin.action(description='→ Entregue')
    def marcar_entregue(self, request, queryset):
        self._mudar_status(request, queryset, 'entregue', 'Entregue')

    @admin.action(description='→ Cancelado')
    def marcar_cancelado(self, request, queryset):
        self._mudar_status(request, queryset, 'cancelado', 'Cancelado')

    # ── Ações Bling ────────────────────────────────────────────────────────────

    @admin.action(description='Bling: enviar pedidos selecionados')
    def enviar_ao_bling(self, request, queryset):
        from apps.bling.services import enviar_pedido_bling

        ok_count = fail_count = 0
        for pedido in queryset:
            try:
                if enviar_pedido_bling(pedido):
                    ok_count += 1
                else:
                    fail_count += 1
            except Exception as exc:
                logger.error('Erro ao enviar pedido %s ao Bling: %s', pedido.numero, exc)
                fail_count += 1

        if ok_count:
            self.message_user(request, f'{ok_count} pedido(s) enviado(s) ao Bling.')
        if fail_count:
            self.message_user(
                request,
                f'{fail_count} pedido(s) com falha. Verifique os Logs Bling.',
                level='WARNING',
            )

    @admin.action(description='Bling: emitir NF-e dos pedidos selecionados')
    def emitir_nfe(self, request, queryset):
        from apps.bling.services import emitir_nfe_bling

        ok_count = fail_count = sem_bling = 0
        for pedido in queryset:
            if not pedido.bling_pedido_id:
                sem_bling += 1
                continue
            try:
                if emitir_nfe_bling(pedido):
                    ok_count += 1
                else:
                    fail_count += 1
            except Exception as exc:
                logger.error('Erro ao emitir NF-e do pedido %s: %s', pedido.numero, exc)
                fail_count += 1

        if ok_count:
            self.message_user(request, f'{ok_count} NF-e(s) emitida(s).')
        if sem_bling:
            self.message_user(
                request,
                f'{sem_bling} pedido(s) pulados (não enviados ao Bling ainda).',
                level='WARNING',
            )
        if fail_count:
            self.message_user(
                request,
                f'{fail_count} NF-e(s) com falha. Verifique a configuração fiscal no Bling e os Logs Bling.',
                level='ERROR',
            )
