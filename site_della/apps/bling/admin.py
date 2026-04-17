from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.http import HttpResponseRedirect
from .models import BlingToken, BlingLog


@admin.register(BlingToken)
class BlingTokenAdmin(admin.ModelAdmin):
    list_display = ('expira_em', 'badge_valido', 'info_autorefresh', 'criado_em', 'atualizado_em', 'acoes')
    # Tokens NÃO são exibidos em texto claro — apenas versão mascarada (8 chars + ••• + últimos 4).
    # O fluxo de refresh/OAuth continua funcionando normalmente; o admin não precisa ver o valor completo.
    readonly_fields = ('access_token_mascarado', 'refresh_token_mascarado', 'expira_em', 'criado_em', 'atualizado_em')
    ordering = ('-criado_em',)

    def access_token_mascarado(self, obj):
        t = obj.access_token or ''
        if not t:
            return '—'
        return f'{t[:8]}{"•" * 20}  (…{t[-4:]})'
    access_token_mascarado.short_description = 'Access Token'

    def refresh_token_mascarado(self, obj):
        t = obj.refresh_token or ''
        if not t:
            return '—'
        return f'{t[:8]}{"•" * 20}  (…{t[-4:]})'
    refresh_token_mascarado.short_description = 'Refresh Token'

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
            '<div style="display:flex;flex-direction:column;gap:4px;min-width:130px;">'
            '<a href="/bling/refresh-token/" '
            'style="background:#27ae60;color:#fff;padding:3px 10px;'
            'border-radius:3px;font-size:11px;text-decoration:none;white-space:nowrap;text-align:center;" '
            'title="Força renovação do access_token agora">Atualizar Token</a>'
            '<a href="/bling/autorizar/" '
            'style="background:#c9a96e;color:#fff;padding:3px 10px;'
            'border-radius:3px;font-size:11px;text-decoration:none;white-space:nowrap;text-align:center;" '
            'title="Re-autoriza do zero (use se Atualizar Token falhar)">Re-autorizar</a>'
            '</div>'
        )
    acoes.short_description = 'Ações'

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.utils.html import format_html
        extra_context = extra_context or {}
        extra_context['info_token'] = format_html(
            '<div style="background:#fffbe6;border:1px solid #f0c040;border-radius:6px;'
            'padding:12px 16px;margin-bottom:16px;font-size:13px;line-height:1.6;">'
            '<strong>ℹ️ Como funciona o token Bling</strong><br>'
            '• O <em>access_token</em> expira em ~1 hora — isso é normal, é o padrão do Bling.<br>'
            '• O sistema renova automaticamente ao fazer chamadas à API (ex: enviar pedido ao Bling).<br>'
            '• Se quiser forçar a renovação agora, clique em <strong>"Atualizar Token"</strong> (verde).<br>'
            '• Se "Atualizar Token" falhar, o <em>refresh_token</em> expirou (validade: 30 dias). '
            'Clique em <strong>"Re-autorizar"</strong> (dourado) para refazer o OAuth do zero.<br>'
            '• O pedido no campo <em>Aguardando Pagamento</em> que você viu existe no banco — '
            'para cancelá-lo vá em <a href="/painel/pedidos/pedido/">Pedidos</a>, filtre por status '
            'e use as ações ou o botão ✕ na linha.'
            '</div>'
        )
        return super().changelist_view(request, extra_context)


@admin.register(BlingLog)
class BlingLogAdmin(admin.ModelAdmin):
    list_display = ('criado_em', 'tipo', 'pedido', 'badge_sucesso', 'erro_resumo')
    list_filter = ('tipo', 'sucesso')
    search_fields = ('pedido__numero', 'erro')
    date_hierarchy = 'criado_em'
    ordering = ('-criado_em',)
    # payload_enviado e resposta omitidos da view — dados de cliente já são
    # redactados na escrita (services.py), mas a resposta da API ainda pode
    # conter IDs internos. Usar o campo 'erro' para diagnóstico operacional.
    readonly_fields = ('tipo', 'pedido', 'sucesso', 'payload_resumo', 'erro', 'criado_em')

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def payload_resumo(self, obj):
        """Exibe apenas campos não-sensíveis do payload para diagnóstico."""
        p = obj.payload_enviado or {}
        safe_keys = ('numero', 'numeroLoja', 'data', 'total', 'situacao', 'itens')
        resumo = {k: p[k] for k in safe_keys if k in p}
        if not resumo:
            return '—'
        import json as _json
        return _json.dumps(resumo, ensure_ascii=False, indent=2)[:800]
    payload_resumo.short_description = 'Payload (resumo)'

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
