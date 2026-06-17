from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.db import transaction
from apps.core_utils.admin_mixin import DellaAdminMixin
from .models import BannerPrincipal, MiniBanner, LookDaSemana, PaginaEstatica, ConfiguracaoLoja, InstagramPost, TarjaFrase, LinkBio, ContatoFormulario


@admin.register(BannerPrincipal)
class BannerPrincipalAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = ('ordem', 'tipo_badge', 'preview_midia', 'url_botao', 'ativo', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('ordem',)
    ordering = ('ordem',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_banners
        invalidar_banners()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import invalidar_banners
        invalidar_banners()

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
        ('Link do banner', {
            'fields': ('url_botao',),
            'description': 'Ao clicar em qualquer parte do banner, o cliente é redirecionado para este link.',
        }),
        ('Enquadramento da imagem', {
            'fields': ('posicao_imagem',),
            'description': (
                'Define qual parte da foto fica visível quando o navegador corta a imagem para preencher o banner. '
                'Use "Esquerda" se o elemento principal (texto, rosto) estiver no início da foto e estiver sendo cortado.'
            ),
        }),
    )

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:conteudo_bannerprincipal_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_bannerprincipal_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este banner?')
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
class MiniBannerAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = ('posicao_label', 'posicao', 'preview_foto', 'url', 'ativo', 'acoes_linha')
    list_editable = ('posicao', 'ativo')
    list_display_links = ('posicao_label',)
    ordering = ('-posicao',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_banners
        invalidar_banners()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import invalidar_banners
        invalidar_banners()

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def changelist_view(self, request, extra_context=None):
        if request.method == 'POST' and '_save' in request.POST:
            total_forms = int(request.POST.get('form-TOTAL_FORMS', 0) or 0)
            ids = []
            payload = []

            for index in range(total_forms):
                obj_id = request.POST.get(f'form-{index}-id')
                posicao = request.POST.get(f'form-{index}-posicao')
                ativo_raw = request.POST.get(f'form-{index}-ativo')
                if not obj_id:
                    continue
                ids.append(int(obj_id))
                payload.append({
                    'id': int(obj_id),
                    'posicao': posicao,
                    'ativo': bool(ativo_raw),
                })

            if payload:
                posicoes = [item['posicao'] for item in payload]
                if sorted(posicoes) != ['dir', 'esq']:
                    self.message_user(
                        request,
                        'Nao foi possivel salvar: deve existir exatamente um mini banner na Esquerda e um na Direita.',
                        level=messages.ERROR,
                    )
                    return redirect(request.get_full_path())

                banners = {
                    banner.pk: banner
                    for banner in MiniBanner.objects.filter(pk__in=ids)
                }
                temp_values = {item['id']: f'x{idx}' for idx, item in enumerate(payload, start=1)}

                with transaction.atomic():
                    for item in payload:
                        banner = banners.get(item['id'])
                        if not banner:
                            continue
                        if banner.posicao != item['posicao']:
                            MiniBanner.objects.filter(pk=banner.pk).update(posicao=temp_values[banner.pk])

                    for item in payload:
                        banner = banners.get(item['id'])
                        if not banner:
                            continue
                        MiniBanner.objects.filter(pk=banner.pk).update(
                            posicao=item['posicao'],
                            ativo=item['ativo'],
                        )

                from apps.core_utils.cache_utils import invalidar_banners
                invalidar_banners()
                self.message_user(request, 'Mini banners atualizados com sucesso.', level=messages.SUCCESS)
                return redirect(request.get_full_path())

        return super().changelist_view(request, extra_context=extra_context)

    fieldsets = (
        ('Posição e visibilidade', {
            'fields': ('posicao', 'ativo'),
            'description': (
                'Esquerda = primeiro mini banner (lado esquerdo). '
                'Direita = segundo (lado direito). '
                'Cada posição aceita apenas um banner ativo por vez.'
            ),
        }),
        ('Conteúdo', {
            'fields': ('foto', 'url'),
        }),
    )

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:conteudo_minibanner_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_minibanner_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este mini banner?')
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
class PaginaEstaticaAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = ('get_slug_display', 'titulo', 'ativo', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('get_slug_display',)

    class Media:
        js = ('admin/js/pagina_editor.js', 'admin/js/admin_linhas.js')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_pagina
        invalidar_pagina(obj.slug)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import invalidar_pagina
        invalidar_pagina(obj.slug)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:conteudo_paginaestatica_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_paginaestatica_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir esta página?')
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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_config_loja, invalidar_manutencao
        invalidar_config_loja()
        invalidar_manutencao()

    fieldsets = (
        ('🚧 Modo Manutenção', {
            'fields': ('modo_manutencao',),
            'description': (
                '<strong style="color:#c9a96e">ATIVADO</strong>: somente o admin acessa o site — '
                'visitantes veem uma página "Em breve / Manutenção". '
                'Leva até 30 segundos para propagar após salvar.'
            ),
        }),
        ('Frete grátis', {
            'fields': ('frete_gratis_acima',),
            'description': (
                'Se preenchido, um aviso de frete grátis aparece no site quando '
                'o valor do carrinho está acima desse limite. Deixe em branco para desativar.'
            ),
        }),
    )

    def has_add_permission(self, request):
        return not ConfiguracaoLoja.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Redireciona direto para o único registro (ou para criação se não existir)."""
        obj = ConfiguracaoLoja.objects.first()
        if obj:
            return redirect(reverse('admin:conteudo_configuracaoloja_change', args=[obj.pk]))
        return redirect(reverse('admin:conteudo_configuracaoloja_add'))

    def response_change(self, request, obj):
        """Após salvar, fica na tela de edição."""
        from django.contrib import messages as msg_module
        msg_module.success(request, 'Configuração de frete grátis salva com sucesso.')
        return redirect(reverse('admin:conteudo_configuracaoloja_change', args=[obj.pk]))


@admin.register(LookDaSemana)
class LookDaSemanaAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = ('titulo', 'preview_foto', 'lista_produtos', 'ativo', 'criado_em', 'acoes_linha')
    list_editable = ('ativo',)
    list_display_links = ('titulo',)
    ordering = ('-criado_em',)
    readonly_fields = ('criado_em',)

    class Media:
        js = ('admin/js/look_editor.js', 'admin/js/admin_linhas.js')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_look
        invalidar_look()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import invalidar_look
        invalidar_look()

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
            'fields': ('produto_ponto1', 'foto_ponto1', ('ponto1_top', 'ponto1_esq')),
            'description': (
                'Selecione o produto e use o editor visual (acima) para clicar na foto e posicionar o ponto. '
                'Salve o look após escolher o produto para que as fotos disponíveis apareçam no campo "Foto do ponto". '
                'Deixe o produto em branco para não exibir este ponto.'
            ),
        }),
        ('Ponto "+" 2', {
            'fields': ('produto_ponto2', 'foto_ponto2', ('ponto2_top', 'ponto2_esq')),
            'description': (
                'Salve o look após escolher o produto para que as fotos disponíveis apareçam no campo "Foto do ponto". '
                'Deixe o produto em branco para não exibir este ponto.'
            ),
        }),
        ('Ponto "+" 3', {
            'fields': ('produto_ponto3', 'foto_ponto3', ('ponto3_top', 'ponto3_esq')),
            'description': (
                'Salve o look após escolher o produto para que as fotos disponíveis apareçam no campo "Foto do ponto". '
                'Deixe o produto em branco para não exibir este ponto.'
            ),
        }),
        ('Datas', {
            'fields': ('criado_em',),
            'classes': ('collapse',),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        from apps.produtos.models import ProdutoImagem
        form = super().get_form(request, obj, **kwargs)
        if obj:
            for n in (1, 2, 3):
                produto = getattr(obj, f'produto_ponto{n}', None)
                field = form.base_fields.get(f'foto_ponto{n}')
                if field:
                    if produto:
                        field.queryset = ProdutoImagem.objects.filter(
                            produto=produto
                        ).order_by('-principal', 'ordem')
                    else:
                        field.queryset = ProdutoImagem.objects.none()
        return form

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:conteudo_lookdasemana_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_lookdasemana_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este look?')
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
class InstagramPostAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display  = ('preview', 'instagram_id', 'media_type', 'timestamp', 'ativo', 'ordem', 'acoes_linha')
    list_editable = ('ativo', 'ordem')
    list_display_links = ('instagram_id',)
    list_filter   = ('ativo', 'media_type')
    ordering      = ('-ativo', 'ordem', '-timestamp')
    readonly_fields = ('instagram_id', 'media_type', 'permalink', 'timestamp', 'preview_grande')
    list_per_page = 200

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path('importar-instagram/', self.admin_site.admin_view(self.importar_historico), name='importar_instagram'),
            path('atualizar-instagram/', self.admin_site.admin_view(self.atualizar_instagram), name='atualizar_instagram'),
        ]
        return extra + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['importar_url'] = 'importar-instagram/'
        extra_context['atualizar_url'] = 'atualizar-instagram/'
        extra_context['total_ativos'] = InstagramPost.objects.filter(ativo=True).count()
        extra_context['total_posts']  = InstagramPost.objects.count()
        return super().changelist_view(request, extra_context=extra_context)

    def _executar_import(self, request, max_paginas, parar_se_sem_novos=False, since=None):
        """Lógica compartilhada de importação. max_paginas=None = sem limite (histórico completo)."""
        from django.conf import settings
        from django.core.files.base import ContentFile
        import requests as req
        from dateutil.parser import parse as parse_dt

        token      = getattr(settings, 'INSTAGRAM_ACCESS_TOKEN', '')
        account_id = getattr(settings, 'INSTAGRAM_ACCOUNT_ID', '')

        if not token or not account_id:
            self.message_user(request, 'Configure INSTAGRAM_ACCESS_TOKEN e INSTAGRAM_ACCOUNT_ID no .env', messages.ERROR)
            return redirect('..')

        since_param = f'&since={since}' if since else ''
        url = (
            f'https://graph.facebook.com/v19.0/{account_id}/media'
            f'?fields=id,media_type,media_url,thumbnail_url,permalink,caption,timestamp'
            f'&limit=30{since_param}&access_token={token}'
        )
        data = []
        paginas = 0
        while url:
            if max_paginas is not None and paginas >= max_paginas:
                break
            try:
                r = req.get(url, timeout=10)
                r.raise_for_status()
                payload = r.json()
            except Exception as e:
                self.message_user(request, f'Erro ao buscar posts: {e}', messages.ERROR)
                return redirect('..')
            pagina_items = payload.get('data', [])
            pagina_ids = [item['id'] for item in pagina_items]
            existentes = set(InstagramPost.objects.filter(instagram_id__in=pagina_ids).values_list('instagram_id', flat=True))
            novos_na_pagina = [item for item in pagina_items if item['id'] not in existentes]
            data.extend(novos_na_pagina)
            url = payload.get('paging', {}).get('next')
            paginas += 1
            if parar_se_sem_novos and not novos_na_pagina:
                break

        novos = 0
        erros = 0
        for item in data:
            media_type = item.get('media_type', 'IMAGE')
            if media_type == 'VIDEO':
                img_url = item.get('thumbnail_url') or ''
            else:
                img_url = item.get('media_url') or item.get('thumbnail_url') or ''

            if not img_url:
                continue

            try:
                img_resp = req.get(img_url, timeout=15)
                img_resp.raise_for_status()
                filename = f"{item['id']}.jpg"
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
            msg += f' {erros} imagem(ns) não puderam ser baixadas.'
        self.message_user(request, msg)
        return redirect('..')

    def importar_historico(self, request):
        """Importa posts desde 01/01/2025 até hoje, sem parada antecipada."""
        return self._executar_import(request, max_paginas=None, parar_se_sem_novos=False, since=1735689600)

    def atualizar_instagram(self, request):
        """Busca só a primeira página; para se tudo já foi importado."""
        return self._executar_import(request, max_paginas=1, parar_se_sem_novos=True)

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
        edit_url   = reverse('admin:conteudo_instagrampost_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_instagrampost_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir?')
    acoes_linha.short_description = 'Ações'


@admin.register(TarjaFrase)
class TarjaFraseAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display  = ('ordem', 'texto', 'ativa', 'acoes_linha')
    list_editable = ('ordem', 'ativa')
    list_display_links = ('texto',)
    ordering = ('ordem', 'id')

    def get_queryset(self, request):
        return super().get_queryset(request)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_tarja
        invalidar_tarja()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import invalidar_tarja
        invalidar_tarja()

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:conteudo_tarjafrase_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_tarjafrase_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Remover frase da tarja?')
    acoes_linha.short_description = 'Ações'


@admin.register(LinkBio)
class LinkBioAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display  = ('ordem', 'titulo', 'icone', 'link_clicavel', 'ativo', 'acoes_linha')
    list_editable = ('ordem', 'ativo')
    list_display_links = ('titulo',)
    ordering = ('ordem', 'id')
    search_fields = ('titulo', 'subtitulo', 'url')
    fields = ('titulo', 'subtitulo', 'url', 'icone', 'nova_aba', 'ordem', 'ativo')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_links_bio
        invalidar_links_bio()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import invalidar_links_bio
        invalidar_links_bio()

    def link_clicavel(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', obj.url, obj.url)
    link_clicavel.short_description = 'Link'

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:conteudo_linkbio_change', args=[obj.pk])
        delete_url = reverse('admin:conteudo_linkbio_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Remover este link da bio?')
    acoes_linha.short_description = 'Ações'


@admin.register(ContatoFormulario)
class ContatoFormularioAdmin(admin.ModelAdmin):
    list_display  = ('nome', 'email', 'telefone_exibido', 'mensagem_preview', 'recebido_em', 'status_badge')
    list_filter   = ('respondido', 'recebido_em')
    search_fields = ('nome', 'email', 'mensagem')
    readonly_fields = ('nome', 'email', 'telefone', 'mensagem', 'recebido_em', 'respondido_em')
    list_per_page = 30
    date_hierarchy = 'recebido_em'
    ordering      = ('-recebido_em',)
    actions       = ['action_marcar_respondido', 'action_marcar_pendente']

    fieldsets = (
        ('Dados do contato', {
            'fields': ('nome', 'email', 'telefone', 'mensagem', 'recebido_em'),
        }),
        ('Atendimento', {
            'fields': ('respondido', 'respondido_em', 'observacao'),
            'description': (
                'Marque "Respondido" apos entrar em contato com o cliente. '
                'A data de resposta e preenchida automaticamente.'
            ),
        }),
    )

    def save_model(self, request, obj, form, change):
        from django.utils import timezone as tz
        if change and obj.respondido and not obj.respondido_em:
            obj.respondido_em = tz.now()
        elif not obj.respondido:
            obj.respondido_em = None
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False

    @admin.action(description='Marcar selecionados como Respondido')
    def action_marcar_respondido(self, request, queryset):
        from django.utils import timezone as tz
        agora = tz.now()
        atualizados = queryset.filter(respondido=False).update(respondido=True, respondido_em=agora)
        self.message_user(request, f'{atualizados} formulario(s) marcado(s) como respondido.')

    @admin.action(description='Marcar selecionados como Pendente')
    def action_marcar_pendente(self, request, queryset):
        atualizados = queryset.filter(respondido=True).update(respondido=False, respondido_em=None)
        self.message_user(request, f'{atualizados} formulario(s) marcado(s) como pendente.')

    def status_badge(self, obj):
        if obj.respondido:
            return format_html(
                '<span style="background:#27ae60;color:#fff;padding:2px 10px;'
                'border-radius:3px;font-size:11px;font-weight:600;">Respondido</span>'
            )
        return format_html(
            '<span style="background:#e74c3c;color:#fff;padding:2px 10px;'
            'border-radius:3px;font-size:11px;font-weight:600;">Pendente</span>'
        )
    status_badge.short_description = 'Status'

    def mensagem_preview(self, obj):
        if len(obj.mensagem) > 80:
            return obj.mensagem[:80] + '...'
        return obj.mensagem
    mensagem_preview.short_description = 'Mensagem'

    def telefone_exibido(self, obj):
        return obj.telefone or '—'
    telefone_exibido.short_description = 'Telefone'
