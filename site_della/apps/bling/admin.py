from django.contrib import admin
from django.utils.html import format_html
from .models import BlingToken, BlingLog


@admin.register(BlingToken)
class BlingTokenAdmin(admin.ModelAdmin):
    list_display = ('expira_em', 'badge_valido', 'criado_em', 'atualizado_em', 'btn_autorizar')
    readonly_fields = ('access_token', 'refresh_token', 'expira_em', 'criado_em', 'atualizado_em')
    ordering = ('-criado_em',)
    change_list_template = 'admin/bling_token_changelist.html'

    def badge_valido(self, obj):
        if obj.valido:
            return format_html(
                '<span style="background:#27ae60;color:#fff;padding:2px 8px;'
                'border-radius:3px;font-size:11px;">Válido</span>'
            )
        return format_html(
            '<span style="background:#e74c3c;color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px;">Expirado</span>'
        )
    badge_valido.short_description = 'Token'

    def btn_autorizar(self, obj):
        return format_html(
            '<a href="/bling/autorizar/" style="background:#c9a96e;color:#fff;padding:3px 10px;'
            'border-radius:3px;font-size:11px;text-decoration:none;">Renovar</a>'
        )
    btn_autorizar.short_description = 'Ação'

    def has_add_permission(self, request):
        return False


@admin.register(BlingLog)
class BlingLogAdmin(admin.ModelAdmin):
    list_display = ('criado_em', 'tipo', 'pedido', 'badge_sucesso', 'erro_resumo')
    list_filter = ('tipo', 'sucesso')
    search_fields = ('pedido__numero', 'erro')
    date_hierarchy = 'criado_em'
    ordering = ('-criado_em',)
    readonly_fields = ('tipo', 'pedido', 'sucesso', 'payload_enviado', 'resposta', 'erro', 'criado_em')

    def badge_sucesso(self, obj):
        if obj.sucesso:
            return format_html(
                '<span style="background:#27ae60;color:#fff;padding:2px 8px;'
                'border-radius:3px;font-size:11px;">OK</span>'
            )
        return format_html(
            '<span style="background:#e74c3c;color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px;">Erro</span>'
        )
    badge_sucesso.short_description = 'Resultado'

    def erro_resumo(self, obj):
        if obj.erro:
            return obj.erro[:80] + ('...' if len(obj.erro) > 80 else '')
        return '—'
    erro_resumo.short_description = 'Erro'

    def has_add_permission(self, request):
        return False
