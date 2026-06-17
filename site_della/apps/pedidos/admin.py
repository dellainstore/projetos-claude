import logging

from django.contrib import admin, messages
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.urls import reverse
from apps.core_utils.admin_mixin import DellaAdminMixin

from .models import Pedido, ItemPedido, HistoricoPedido, Cupom, CupomEmitido, CodigoVendedor, CarrinhoAbandonado

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
    'pronto_retirada':      '#c9a96e',
    'enviado':              '#8e44ad',
    'entregue':             '#27ae60',
    'cancelado':            '#e74c3c',
    'estornado':            '#e74c3c',
}


@admin.register(Pedido)
class PedidoAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = (
        'numero', 'nome_completo', 'email', 'badge_status', 'badge_retirada',
        'forma_pagamento', 'total_formatado', 'badge_bling', 'codigo_rastreio',
        'criado_em', 'acoes_linha',
    )
    list_display_links = ('numero', 'nome_completo')
    list_filter = ('status', 'retirada_loja', 'forma_pagamento', 'gateway', 'estado')
    search_fields = ('numero', 'nome_completo', 'email', 'cpf', 'codigo_rastreio', 'bling_pedido_id')
    date_hierarchy = 'criado_em'
    ordering = ('-criado_em',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Mantém delete_selected + apenas as actions custom declaradas em self.actions
        permitidas = {'delete_selected', *(self.actions or [])}
        return {k: v for k, v in actions.items() if k in permitidas}

    def delete_model(self, request, obj):
        self._restaurar_estoque_se_aplicavel(obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for pedido in queryset:
            self._restaurar_estoque_se_aplicavel(pedido)
        super().delete_queryset(request, queryset)

    def _restaurar_estoque_se_aplicavel(self, pedido):
        # Pedidos cancelados/estornados já devolveram o estoque no webhook/cron
        if pedido.status in ('cancelado', 'estornado'):
            return
        try:
            from apps.bling.services import restaurar_estoque_pedido
            restaurar_estoque_pedido(pedido)
        except Exception as exc:
            logger.error('Falha ao restaurar estoque ao excluir pedido %s: %s',
                         pedido.numero, exc)

    readonly_fields = (
        'numero', 'nome_completo', 'email', 'cpf', 'telefone',
        'cep_entrega', 'logradouro', 'numero_entrega', 'complemento',
        'bairro', 'cidade', 'estado',
        'subtotal', 'desconto', 'frete', 'total',
        'gateway', 'gateway_id', 'parcelas', 'forma_pagamento',
        'cupom_codigo', 'codigo_vendedor_str',
        'bling_pedido_id',
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
        ('Cupom / Vendedor', {
            'fields': ('cupom', 'cupom_codigo', 'codigo_vendedor', 'codigo_vendedor_str'),
            'classes': ('collapse',),
        }),
        ('Entrega', {
            'fields': ('retirada_loja', 'codigo_rastreio', 'transportadora'),
        }),
        ('Bling', {
            'fields': ('bling_pedido_id',),
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
        'marcar_pronto_retirada',
        'marcar_enviado',
        'marcar_entregue',
        'marcar_cancelado',
        'cancelar_e_estornar_pagseguro',
        'enviar_ao_bling',
        'emitir_nfe',
    ]

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:pedidos_pedido_change', args=[obj.pk])
        delete_url = reverse('admin:pedidos_pedido_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este pedido?')
    acoes_linha.short_description = 'Ações'

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

    def badge_retirada(self, obj):
        if obj.retirada_loja:
            return format_html(
                '<span style="background:#c9a96e;color:#fff;padding:2px 6px;'
                'border-radius:3px;font-size:11px;" title="Retirada na loja">Loja</span>'
            )
        return format_html('<span style="color:#ddd;font-size:11px;">-</span>')
    badge_retirada.short_description = 'Retirada'

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

    def _mudar_status(self, request, queryset, novo_status, label,
                      enviar_bling=False, enviar_email_envio=False):
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

                if novo_status == 'pagamento_confirmado':
                    self._tentar_enviar_email_pagamento_confirmado(request, pedido)

                if novo_status == 'pronto_retirada':
                    self._tentar_enviar_email_pronto_retirada(request, pedido)

                if enviar_email_envio and novo_status == 'enviado':
                    self._tentar_enviar_email_envio(request, pedido)

                if novo_status == 'entregue':
                    self._tentar_enviar_email_entregue(request, pedido)

                if novo_status == 'cancelado':
                    self._tentar_enviar_email_cancelamento(request, pedido, estornado=False)
                    try:
                        from apps.bling.services import restaurar_estoque_pedido
                        restaurar_estoque_pedido(pedido)
                    except Exception as exc_e:
                        logger.error('Erro ao restaurar estoque do pedido %s: %s', pedido.numero, exc_e)

        self.message_user(request, f'{atualizados} pedido(s) marcado(s) como "{label}".')

    def _tentar_enviar_email_pagamento_confirmado(self, request, pedido):
        """Envia e-mail informando que o pagamento foi confirmado e o pedido está em separação."""
        try:
            from apps.pedidos.emails import enviar_confirmacao_pagamento
            ok = enviar_confirmacao_pagamento(pedido)
            if not ok:
                self.message_user(
                    request,
                    f'Não foi possível enviar e-mail de confirmação de pagamento para {pedido.email}.',
                    level='WARNING',
                )
        except Exception as exc:
            logger.error('Erro ao enviar e-mail de pagamento confirmado do pedido %s: %s', pedido.numero, exc)

    def _tentar_enviar_email_pronto_retirada(self, request, pedido):
        """Envia e-mail informando que o pedido esta pronto para retirada na loja."""
        try:
            from apps.pedidos.emails import enviar_pronto_retirada
            ok = enviar_pronto_retirada(pedido)
            if not ok:
                self.message_user(
                    request,
                    f'Não foi possível enviar e-mail de pronto para retirada para {pedido.email}.',
                    level='WARNING',
                )
        except Exception as exc:
            logger.error('Erro ao enviar e-mail de pronto para retirada do pedido %s: %s', pedido.numero, exc)

    def _tentar_enviar_email_entregue(self, request, pedido):
        """Envia e-mail de entregue + avaliacao para qualquer pedido marcado como entregue pelo admin."""
        try:
            from apps.pedidos.emails import enviar_confirmacao_entrega
            ok = enviar_confirmacao_entrega(pedido)
            if not ok:
                self.message_user(
                    request,
                    f'Não foi possível enviar e-mail de entregue para {pedido.email}.',
                    level='WARNING',
                )
        except Exception as exc:
            logger.error('Erro ao enviar e-mail de entregue do pedido %s: %s', pedido.numero, exc)

    def _tentar_enviar_email_cancelamento(self, request, pedido, estornado=False):
        """Envia e-mail informando o cancelamento do pedido."""
        try:
            from apps.pedidos.emails import enviar_cancelamento
            ok = enviar_cancelamento(pedido, estornado=estornado)
            if not ok:
                self.message_user(
                    request,
                    f'Não foi possível enviar e-mail de cancelamento para {pedido.email}.',
                    level='WARNING',
                )
        except Exception as exc:
            logger.error('Erro ao enviar e-mail de cancelamento do pedido %s: %s', pedido.numero, exc)

    def _tentar_enviar_email_envio(self, request, pedido):
        """Envia e-mail de notificação de envio com rastreio."""
        try:
            from apps.pedidos.emails import enviar_notificacao_envio
            ok = enviar_notificacao_envio(pedido)
            if ok:
                self.message_user(request, f'E-mail de envio disparado para {pedido.email}.')
            else:
                self.message_user(
                    request,
                    f'Não foi possível enviar o e-mail de envio para {pedido.email}. Verifique as configurações de e-mail.',
                    level='WARNING',
                )
        except Exception as exc:
            logger.error('Erro ao enviar e-mail de envio do pedido %s: %s', pedido.numero, exc)

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

    @admin.action(description='→ Pronto para Retirada (+ e-mail ao cliente)')
    def marcar_pronto_retirada(self, request, queryset):
        self._mudar_status(request, queryset, 'pronto_retirada', 'Pronto para Retirada')

    @admin.action(description='→ Enviado (+ e-mail de rastreio)')
    def marcar_enviado(self, request, queryset):
        self._mudar_status(request, queryset, 'enviado', 'Enviado')

    @admin.action(description='→ Entregue')
    def marcar_entregue(self, request, queryset):
        self._mudar_status(request, queryset, 'entregue', 'Entregue')

    @admin.action(description='→ Cancelado')
    def marcar_cancelado(self, request, queryset):
        self._mudar_status(request, queryset, 'cancelado', 'Cancelado')

    @admin.action(description='⚠ Cancelar + Estornar PagBank (irreversível)')
    def cancelar_e_estornar_pagseguro(self, request, queryset):
        """
        Cancela o pedido E solicita estorno da cobrança no PagBank.
        Mostra página de confirmação antes de executar (ação irreversível).
        Após estorno: muda status para 'cancelado', restaura estoque e
        atualiza situação no Bling.
        """
        if request.POST.get('confirmar') == 'yes':
            from apps.pagamentos.services.pagseguro import cancelar_pedido_pagseguro
            from apps.bling.services import (
                restaurar_estoque_pedido, atualizar_situacao_bling, SITUACAO_CANCELADO,
            )

            sucessos, falhas = [], []
            for pedido in queryset:
                ok, info = cancelar_pedido_pagseguro(pedido)
                if not ok:
                    falhas.append((pedido.numero, info))
                    continue

                if pedido.status != 'cancelado':
                    HistoricoPedido.objects.create(
                        pedido=pedido,
                        status_anterior=pedido.status,
                        status_novo='cancelado',
                        observacao=f'Estorno PagBank (charge {info}) solicitado por {request.user.email}',
                    )
                    pedido.status = 'cancelado'
                    pedido.save(update_fields=['status', 'atualizado_em'])

                    try:
                        restaurar_estoque_pedido(pedido)
                    except Exception as exc:
                        logger.warning('Estoque: falha ao restaurar pedido %s após estorno: %s',
                                       pedido.numero, exc)
                    if pedido.bling_pedido_id:
                        try:
                            atualizar_situacao_bling(pedido, SITUACAO_CANCELADO)
                        except Exception as exc:
                            logger.warning('Bling: falha ao cancelar pedido %s após estorno: %s',
                                           pedido.numero, exc)

                    self._tentar_enviar_email_cancelamento(request, pedido, estornado=True)

                sucessos.append(pedido.numero)

            if sucessos:
                self.message_user(
                    request,
                    f'{len(sucessos)} pedido(s) estornado(s) no PagBank: {", ".join(sucessos)}.',
                    level=messages.SUCCESS,
                )
            for numero, motivo in falhas:
                self.message_user(
                    request,
                    f'Falha ao estornar {numero}: {motivo}',
                    level=messages.ERROR,
                )
            return None

        return TemplateResponse(request, 'admin/pedidos/confirmar_estorno.html', {
            'pedidos': queryset,
            'opts':    self.model._meta,
            'title':   'Confirmar Cancelamento + Estorno PagBank',
        })

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

    def save_model(self, request, obj, form, change):
        if change and 'status' in form.changed_data and obj.status == 'entregue':
            super().save_model(request, obj, form, change)
            self._tentar_enviar_email_entregue(request, obj)
        else:
            super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# Cupom
# ---------------------------------------------------------------------------

@admin.register(Cupom)
class CupomAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display  = ('codigo', 'origem', 'tipo', 'valor_formatado', 'vezes_usado', 'quantidade_total',
                     'um_por_cliente', 'valido_ate', 'ativo', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('codigo',)
    search_fields = ('codigo',)
    list_filter   = ('origem', 'tipo', 'ativo', 'um_por_cliente')
    ordering      = ('-id',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        return {}

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_newsletter_oferta
        invalidar_newsletter_oferta()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import invalidar_newsletter_oferta
        invalidar_newsletter_oferta()

    fieldsets = (
        ('Código e desconto', {
            'fields': ('codigo', 'origem', 'tipo', 'valor', 'ativo'),
            'description': (
                'Tipo <b>Percentual</b>: informe o % de desconto (ex: 10 = 10%). '
                'Tipo <b>Valor fixo</b>: informe o valor em reais (ex: 30.00). '
                '<b>Origem</b>: Manual = código que a cliente digita direto. '
                'Newsletter / Primeira compra / Aniversário = template usado pelo sistema para gerar cupons únicos por cliente.'
            ),
        }),
        ('Limites de uso', {
            'fields': ('quantidade_total', 'um_por_cliente'),
            'description': (
                'Quantidade total em branco = ilimitado. '
                '"1 uso por cliente" controla pelo CPF.'
            ),
        }),
        ('Validade', {
            'fields': ('valido_de', 'valido_ate', 'dias_validade_pos_emissao'),
            'description': (
                'Datas fixas: deixe em branco para não limitar. '
                '<b>Dias de validade após emissão</b>: para templates de cupons individuais '
                '(newsletter, etc.) — quando preenchido, ignora as datas fixas e expira N dias após emissão.'
            ),
        }),
    )

    def valor_formatado(self, obj):
        if obj.tipo == 'percentual':
            return format_html('<span style="color:#2980b9;">{} %</span>', obj.valor)
        v = f'{obj.valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return format_html('<span style="color:#27ae60;">R$ {}</span>', v)
    valor_formatado.short_description = 'Desconto'

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:pedidos_cupom_change', args=[obj.pk])
        delete_url = reverse('admin:pedidos_cupom_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este cupom?')
    acoes_linha.short_description = 'Ações'


# ---------------------------------------------------------------------------
# CupomEmitido (instâncias geradas automaticamente — newsletter, etc.)
# ---------------------------------------------------------------------------

@admin.register(CupomEmitido)
class CupomEmitidoAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display  = ('codigo', 'email', 'origem_template', 'status_badge',
                     'emitido_em', 'expira_em', 'usado_em', 'acoes_linha')
    list_display_links = ('codigo',)
    search_fields = ('codigo', 'email', 'cliente__email', 'cliente__nome')
    list_filter   = ('cupom_template__origem', 'cupom_template')
    ordering      = ('-emitido_em',)
    autocomplete_fields = ('cupom_template', 'cliente', 'pedido')
    readonly_fields = ('codigo', 'emitido_em', 'expira_em', 'usado_em', 'pedido')

    class Media:
        js = ('admin/js/admin_linhas.js',)

    fieldsets = (
        ('Identificação', {
            'fields': ('codigo', 'cupom_template', 'email', 'cliente'),
        }),
        ('Datas', {
            'fields': ('emitido_em', 'expira_em', 'usado_em', 'pedido'),
        }),
    )

    def has_add_permission(self, request):
        # Não permite criar manualmente — só pelo fluxo automático (newsletter etc.)
        return False

    def origem_template(self, obj):
        return obj.cupom_template.get_origem_display()
    origem_template.short_description = 'Origem'
    origem_template.admin_order_field = 'cupom_template__origem'

    def status_badge(self, obj):
        status = obj.status
        cores = {
            'valido':   ('#27ae60', 'Válido'),
            'usado':    ('#2980b9', 'Usado'),
            'expirado': ('#c0392b', 'Expirado'),
        }
        cor, label = cores.get(status, ('#888', status))
        return format_html('<span style="color:{};font-weight:600;">{}</span>', cor, label)
    status_badge.short_description = 'Status'

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:pedidos_cupomemitido_change', args=[obj.pk])
        delete_url = reverse('admin:pedidos_cupomemitido_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este cupom emitido?')
    acoes_linha.short_description = 'Ações'


# ---------------------------------------------------------------------------
# CodigoVendedor
# ---------------------------------------------------------------------------

@admin.register(CodigoVendedor)
class CodigoVendedorAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display  = ('codigo', 'nome', 'total_pedidos', 'ativo', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('codigo',)
    search_fields = ('codigo', 'nome')
    list_filter   = ('ativo',)
    ordering      = ('nome',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        return {}

    fieldsets = (
        (None, {
            'fields': ('codigo', 'nome', 'ativo'),
        }),
    )

    def total_pedidos(self, obj):
        count = obj.pedidos.exclude(status='cancelado').count()
        return count
    total_pedidos.short_description = 'Pedidos vinculados'

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:pedidos_codigovendedor_change', args=[obj.pk])
        delete_url = reverse('admin:pedidos_codigovendedor_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este código de vendedor?')
    acoes_linha.short_description = 'Ações'


# ---------------------------------------------------------------------------
# CarrinhoAbandonado
# ---------------------------------------------------------------------------

@admin.register(CarrinhoAbandonado)
class CarrinhoAbandonadoAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = (
        'email', 'nome', 'quantidade_itens_display', 'total_formatado',
        'badge_status', 'atualizado_em', 'acoes_linha',
    )
    list_display_links = ('email',)
    list_filter = ('email_enviado', 'recuperado')
    search_fields = ('email', 'nome', 'cliente__cpf')
    date_hierarchy = 'atualizado_em'
    ordering = ('-atualizado_em',)
    readonly_fields = (
        'cliente', 'email', 'nome', 'total', 'itens_resumo',
        'email_enviado', 'email_enviado_em', 'recuperado',
        'criado_em', 'atualizado_em',
    )

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions_filtradas = {k: v for k, v in actions.items() if k == 'delete_selected'}
        actions_filtradas['enviar_email_agora'] = (
            CarrinhoAbandonadoAdmin._action_enviar_email,
            'enviar_email_agora',
            'Enviar e-mail de lembrete agora',
        )
        return actions_filtradas

    def _action_enviar_email(self, request, queryset):
        from .emails import enviar_email_carrinho_abandonado
        enviados = 0
        for ca in queryset.filter(recuperado=False):
            if enviar_email_carrinho_abandonado(ca):
                enviados += 1
        from django.contrib import messages as msgs
        msgs.success(request, f'{enviados} e-mail(s) de lembrete enviado(s).')
    _action_enviar_email.short_description = 'Enviar e-mail de lembrete agora'

    def has_add_permission(self, request):
        return False

    fieldsets = (
        ('Cliente', {
            'fields': ('cliente', 'email', 'nome'),
        }),
        ('Carrinho', {
            'fields': ('total', 'itens_resumo'),
        }),
        ('Status', {
            'fields': ('email_enviado', 'email_enviado_em', 'recuperado'),
        }),
        ('Datas', {
            'fields': ('criado_em', 'atualizado_em'),
            'classes': ('collapse',),
        }),
    )

    def quantidade_itens_display(self, obj):
        return f'{obj.quantidade_itens} item(s)'
    quantidade_itens_display.short_description = 'Itens'

    def total_formatado(self, obj):
        valor = f'{obj.total:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return format_html('<strong style="color:#c9a96e;">R$ {}</strong>', valor)
    total_formatado.short_description = 'Total'

    def badge_status(self, obj):
        if obj.recuperado:
            cor, label = '#27ae60', 'Recuperado'
        elif obj.email_enviado:
            cor, label = '#2980b9', 'E-mail enviado'
        else:
            cor, label = '#f39c12', 'Aguardando'
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;'
            'font-size:11px;font-weight:700;letter-spacing:.5px;white-space:nowrap;">{}</span>',
            cor, label,
        )
    badge_status.short_description = 'Status'

    def itens_resumo(self, obj):
        linhas = []
        for item in obj.itens:
            nome = item.get('nome', '')
            var  = item.get('variacao_desc', '')
            qtd  = item.get('quantidade', 1)
            sub  = item.get('subtotal', '')
            desc = f'{qtd}x {nome}'
            if var:
                desc += f' — {var}'
            desc += f' &nbsp; <strong>R$ {sub}</strong>'
            linhas.append(f'<li style="padding:4px 0;font-size:13px;">{desc}</li>')
        return format_html(
            '<ul style="margin:0;padding:0;list-style:none;">{}</ul>',
            ''.join(linhas),
        )
    itens_resumo.short_description = 'Itens do carrinho'

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:pedidos_carrinhoabandonado_change', args=[obj.pk])
        delete_url = reverse('admin:pedidos_carrinhoabandonado_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este registro?', edit_label='✎ Ver')
    acoes_linha.short_description = 'Ações'
