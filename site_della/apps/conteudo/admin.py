from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from .models import BannerPrincipal, MiniBanner, LookDaSemana, PaginaEstatica, ConfiguracaoLoja, InstagramPost


@admin.register(BannerPrincipal)
class BannerPrincipalAdmin(admin.ModelAdmin):
    list_display = ('ordem', 'tipo_badge', 'titulo', 'preview_midia', 'ativo', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('titulo',)
    ordering = ('ordem',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    fieldsets = (
        ('Ordem e tipo', {
            'fields': ('ordem', 'tipo', 'ativo'),
            'description': (
                'Slide 1 deve ser o vídeo. Os demais são fotos. '
                'Apenas slides ativos aparecem no site.'
            ),
        }),
        ('Arquivo de mídia — Desktop', {
            'fields': ('video', 'poster', 'foto'),
            'description': 'Envie o vídeo OU a foto conforme o tipo selecionado acima. Formato paisagem (16:9).',
        }),
        ('Arquivo de mídia — Mobile (opcional)', {
            'fields': ('video_mobile', 'foto_mobile'),
            'classes': ('collapse',),
            'description': (
                'Versões verticais (9:16) para celular. Se não enviado, o site usa a versão desktop. '
                'Recomendado: 1080×1920px. Vídeo até 30 MB.'
            ),
        }),
        ('Textos sobre o banner', {
            'fields': ('pretitulo', 'titulo', 'titulo_italico', 'subtitulo'),
        }),
        ('Botão de ação', {
            'fields': ('texto_botao', 'url_botao'),
        }),
    )

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:conteudo_bannerprincipal_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_bannerprincipal_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir este banner?\')">✕</a>',
            edit_url, delete_url,
        )
    acoes_linha.short_description = 'Ações'

    def tipo_badge(self, obj):
        if obj.tipo == 'video':
            return format_html(
                '<span style="background:#1a73e8;color:#fff;padding:2px 8px;'
                'border-radius:3px;font-size:11px;">Vídeo</span>'
            )
        return format_html(
            '<span style="background:#34a853;color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px;">Foto</span>'
        )
    tipo_badge.short_description = 'Tipo'

    def preview_midia(self, obj):
        if obj.tipo == 'foto' and obj.foto:
            return format_html(
                '<img src="{}" style="height:50px;width:80px;object-fit:cover;border-radius:4px;" />',
                obj.foto.url,
            )
        if obj.tipo == 'video' and obj.poster:
            return format_html(
                '<img src="{}" style="height:50px;width:80px;object-fit:cover;border-radius:4px;" '
                'title="Poster do vídeo" />',
                obj.poster.url,
            )
        if obj.tipo == 'video' and obj.video:
            return format_html('<span style="color:#666;font-size:12px;">🎬 Vídeo enviado</span>')
        return '—'
    preview_midia.short_description = 'Preview'


@admin.register(MiniBanner)
class MiniBannerAdmin(admin.ModelAdmin):
    list_display = ('posicao_label', 'titulo', 'preview_foto', 'url', 'ativo', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('titulo',)
    ordering = ('posicao',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    fieldsets = (
        ('Posição e visibilidade', {
            'fields': ('posicao', 'ativo'),
            'description': (
                'Esquerda = primeiro mini banner. Direita = segundo. '
                'Cada posição aceita apenas um banner ativo por vez.'
            ),
        }),
        ('Conteúdo', {
            'fields': ('foto', 'url'),
            'description': 'O título e pré-título são opcionais — deixe em branco se o banner já tem o texto na imagem.',
        }),
        ('Texto sobre o banner (opcional)', {
            'fields': ('pretitulo', 'titulo'),
            'classes': ('collapse',),
        }),
    )

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:conteudo_minibanner_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_minibanner_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir este mini banner?\')">✕</a>',
            edit_url, delete_url,
        )
    acoes_linha.short_description = 'Ações'

    def posicao_label(self, obj):
        cores = {'esq': '#c9a96e', 'dir': '#6e8dc9'}
        cor = cores.get(obj.posicao, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px;">{}</span>',
            cor, obj.get_posicao_display(),
        )
    posicao_label.short_description = 'Posição'

    def preview_foto(self, obj):
        if obj.foto:
            return format_html(
                '<img src="{}" style="height:60px;width:45px;object-fit:cover;border-radius:4px;" />',
                obj.foto.url,
            )
        return '—'
    preview_foto.short_description = 'Preview'


@admin.register(PaginaEstatica)
class PaginaEstaticaAdmin(admin.ModelAdmin):
    list_display = ('get_slug_display', 'titulo', 'ativo', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('get_slug_display',)

    class Media:
        js = ('admin/js/pagina_editor.js', 'admin/js/admin_linhas.js')

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:conteudo_paginaestatica_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_paginaestatica_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir esta página?\')">✕</a>',
            edit_url, delete_url,
        )
    acoes_linha.short_description = 'Ações'

    fieldsets = (
        (None, {
            'fields': ('slug', 'titulo', 'ativo'),
        }),
        ('Imagem (opcional)', {
            'fields': ('imagem',),
            'classes': ('collapse',),
            'description': (
                'Usada na página "Nossa história" — aparece ao lado do texto. '
                'Proporção recomendada: retrato 3:4 (ex: 600×800px).'
            ),
        }),
        ('Conteúdo da página', {
            'fields': ('conteudo',),
            'description': (
                'Use a barra de ferramentas para formatar: negrito, itálico, listas, títulos e links. '
                'Para perguntas frequentes: use <b>Título 2 (H2)</b> para cada pergunta e parágrafos para a resposta.'
            ),
        }),
    )


@admin.register(ConfiguracaoLoja)
class ConfiguracaoLojaAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Frete grátis', {
            'fields': ('frete_gratis_acima',),
            'description': (
                'Se preenchido, um aviso de frete grátis aparece no produto quando '
                'o valor está acima desse limite. Deixe em branco para desativar.'
            ),
        }),
    )

    def has_add_permission(self, request):
        return not ConfiguracaoLoja.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LookDaSemana)
class LookDaSemanaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'preview_foto', 'lista_produtos', 'ativo', 'criado_em', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('titulo',)
    ordering = ('-criado_em',)
    readonly_fields = ('criado_em',)

    class Media:
        js = ('admin/js/look_editor.js', 'admin/js/admin_linhas.js')

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    fieldsets = (
        ('Look', {
            'fields': ('titulo', 'foto', 'descricao', 'ativo'),
            'description': (
                'A foto aparece no lado esquerdo. O título e a descrição aparecem ao lado. '
                'Apenas o look ativo mais recente é exibido na homepage.'
            ),
        }),
        ('Ponto "+" 1', {
            'fields': ('produto_ponto1', ('ponto1_top', 'ponto1_esq')),
            'description': (
                'Selecione o produto e use o editor visual (acima) para clicar na foto e posicionar o ponto. '
                'Deixe o produto em branco para não exibir este ponto.'
            ),
        }),
        ('Ponto "+" 2', {
            'fields': ('produto_ponto2', ('ponto2_top', 'ponto2_esq')),
            'description': 'Deixe o produto em branco para não exibir este ponto.',
        }),
        ('Ponto "+" 3', {
            'fields': ('produto_ponto3', ('ponto3_top', 'ponto3_esq')),
            'description': 'Deixe o produto em branco para não exibir este ponto.',
        }),
        ('Datas', {
            'fields': ('criado_em',),
            'classes': ('collapse',),
        }),
    )

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:conteudo_lookdasemana_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_lookdasemana_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir este look?\')">✕</a>',
            edit_url, delete_url,
        )
    acoes_linha.short_description = 'Ações'

    def preview_foto(self, obj):
        if obj.foto:
            return format_html(
                '<img src="{}" style="height:70px;width:50px;object-fit:cover;border-radius:4px;" />',
                obj.foto.url,
            )
        return '—'
    preview_foto.short_description = 'Foto'

    def lista_produtos(self, obj):
        nomes = [p.nome for p in [obj.produto_ponto1, obj.produto_ponto2, obj.produto_ponto3] if p]
        if not nomes:
            return '—'
        return format_html('<br>'.join(nomes))
    lista_produtos.short_description = 'Produtos'



@admin.register(InstagramPost)
class InstagramPostAdmin(admin.ModelAdmin):
    list_display  = ('preview', 'instagram_id', 'media_type', 'timestamp', 'ativo', 'ordem', 'acoes_linha')
    list_editable = ('ativo', 'ordem')
    list_display_links = ('instagram_id',)
    list_filter   = ('ativo', 'media_type')
    ordering      = ('ordem', '-timestamp')
    readonly_fields = ('instagram_id', 'media_type', 'permalink', 'timestamp', 'preview_grande')

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_urls(self):
        urls = super().get_urls()
        extra = [path('importar-instagram/', self.admin_site.admin_view(self.importar_instagram), name='importar_instagram')]
        return extra + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['importar_url'] = 'importar-instagram/'
        return super().changelist_view(request, extra_context=extra_context)

    def importar_instagram(self, request):
        from django.conf import settings
        from django.core.files.base import ContentFile
        import requests as req
        from dateutil.parser import parse as parse_dt
        import os

        token      = getattr(settings, 'INSTAGRAM_ACCESS_TOKEN', '')
        account_id = getattr(settings, 'INSTAGRAM_ACCOUNT_ID', '')

        if not token or not account_id:
            self.message_user(request, 'Configure INSTAGRAM_ACCESS_TOKEN e INSTAGRAM_ACCOUNT_ID no .env', messages.ERROR)
            return redirect('..')

        url = (
            f'https://graph.facebook.com/v19.0/{account_id}/media'
            f'?fields=id,media_type,media_url,thumbnail_url,permalink,caption,timestamp'
            f'&limit=30&access_token={token}'
        )
        try:
            r = req.get(url, timeout=10)
            r.raise_for_status()
            data = r.json().get('data', [])
        except Exception as e:
            self.message_user(request, f'Erro ao buscar posts: {e}', messages.ERROR)
            return redirect('..')

        novos = 0
        erros = 0
        for item in data:
            # Vídeos usam thumbnail_url; fotos e carrosséis usam media_url
            media_type = item.get('media_type', 'IMAGE')
            if media_type == 'VIDEO':
                img_url = item.get('thumbnail_url') or ''
            else:
                img_url = item.get('media_url') or item.get('thumbnail_url') or ''

            if not img_url:
                continue

            if InstagramPost.objects.filter(instagram_id=item['id']).exists():
                continue

            # Baixa a imagem localmente para não depender de URLs temporárias do Instagram
            try:
                img_resp = req.get(img_url, timeout=15)
                img_resp.raise_for_status()
                ext      = '.jpg'
                filename = f"{item['id']}{ext}"
                img_file = ContentFile(img_resp.content, name=filename)
            except Exception:
                img_file = None
                erros += 1

            post = InstagramPost(
                instagram_id = item['id'],
                media_type   = media_type,
                permalink    = item.get('permalink', ''),
                caption      = (item.get('caption') or '')[:1000],
                timestamp    = parse_dt(item['timestamp']) if item.get('timestamp') else None,
                ativo        = False,
            )
            post.save()
            if img_file:
                post.imagem_local.save(filename, img_file, save=True)
            novos += 1

        msg = f'{novos} post(s) importado(s).'
        if erros:
            msg += f' {erros} imagem(ns) não puderam ser baixadas (vídeos sem thumbnail).'
        self.message_user(request, msg)
        return redirect('..')

    def preview(self, obj):
        url = obj.imagem_url
        if url:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="height:60px;width:60px;object-fit:cover;border-radius:4px;" />'
                '</a>', obj.permalink, url
            )
        return '—'
    preview.short_description = 'Foto'

    def preview_grande(self, obj):
        url = obj.imagem_url
        if url:
            return format_html('<img src="{}" style="max-width:300px;border-radius:6px;" />', url)
        return '—'
    preview_grande.short_description = 'Preview'

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:conteudo_instagrampost_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_instagrampost_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir?\')">✕</a>',
            edit_url, delete_url,
        )
    acoes_linha.short_description = 'Ações'
