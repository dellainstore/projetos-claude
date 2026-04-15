from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.http import HttpResponseRedirect
from .models import BlingToken, BlingLog


@admin.register(BlingToken)
class BlingTokenAdmin(admin.ModelAdmin):
    list_display = ('expira_em', 'badge_valido', 'info_autorefresh', 'criado_em', 'atualizado_em', 'acoes')
    readonly_fields = ('access_token', 'refresh_token', 'expira_em', 'criado_em', 'atualizado_em')
    ordering = ('-criado_em',)

    def badge_valido(self, obj):
        if obj.valido:
            return format_html(
                '<span style="background:#27ae60;color:#fff;padding:2px 8px;'
                'border-radius:3px;font-size:11px;">✓ Válido</span>'
            )
        return format_html(
            '<span style="background:#e74c3c;color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px;">⏰ Expirado (normal — será renovado automático)</span>'
        )
    badge_valido.short_description = 'Status'

    def info_autorefresh(self, obj):
        return format_html(
            '<span style="font-size:11px;color:#666;">'
            'O sistema renova o token automaticamente ao usar a API.<br>'
            'Access token dura ~1h (padrão Bling). Refresh token dura 30 dias.'
            '</span>'
        )
    info_autorefresh.short_description = 'Como funciona'
    info_autorefresh.allow_tags = True

    def acoes(self, obj):
        return format_html(
            '<a href="/bling/refresh-token/" '
            'style="background:#27ae60;color:#fff;padding:3px 10px;'
            'border-radius:3px;font-size:11px;text-decoration:none;margin-right:6px;" '
            'title="Força renovação do access_token agora">Atualizar Token</a>'
            '<a href="/bling/autorizar/" '
            'style="background:#c9a96e;color:#fff;padding:3px 10px;'
            'border-radius:3px;font-size:11px;text-decoration:none;" '
            'title="Re-autoriza do zero (use se Atualizar Token falhar)">Re-autorizar</a>'
        )
    acoes.short_description = 'Ações'

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['info_token'] = (
            'O access_token expira em ~1 hora — comportamento normal do Bling. '
            'O sistema renova automaticamente sempre que faz uma chamada à API (pedidos, estoque, etc.). '
            'Clique em "Atualizar Token" se quiser forçar a renovação agora. '
            'Se falhar, use "Re-autorizar" para refazer o fluxo OAuth completo.'
        )
        return super().changelist_view(request, extra_context)


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
