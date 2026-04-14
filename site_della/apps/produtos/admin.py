from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Avg
from .models import Categoria, Produto, ProdutoImagem, Variacao, Avaliacao


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class ProdutoImagemInline(admin.TabularInline):
    model = ProdutoImagem
    extra = 1
    fields = ('thumb_preview', 'imagem', 'alt', 'principal', 'ordem')
    readonly_fields = ('thumb_preview',)
    ordering = ('-principal', 'ordem')

    def thumb_preview(self, obj):
        if obj.imagem:
            return mark_safe(
                f'<img src="{obj.imagem.url}" style="height:60px;width:60px;'
                f'object-fit:cover;border-radius:4px;" />'
            )
        return '—'
    thumb_preview.short_description = 'Preview'


class VariacaoInline(admin.TabularInline):
    model = Variacao
    extra = 1
    fields = ('tipo', 'nome', 'codigo_hex', 'estoque', 'sku_variacao', 'ativa')
    ordering = ('tipo', 'nome')


class AvaliacaoInline(admin.StackedInline):
    model = Avaliacao
    extra = 0
    fields = ('nome_publico', 'nota', 'titulo', 'comentario', 'aprovada', 'criada_em')
    readonly_fields = ('criada_em',)
    ordering = ('-criada_em',)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Categoria
# ---------------------------------------------------------------------------

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'slug', 'ordem', 'ativa', 'total_produtos', 'thumb_preview')
    list_editable = ('ordem', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome', 'slug')
    prepopulated_fields = {'slug': ('nome',)}
    ordering = ('ordem', 'nome')

    def thumb_preview(self, obj):
        if obj.imagem:
            return mark_safe(
                f'<img src="{obj.imagem.url}" style="height:40px;width:40px;'
                f'object-fit:cover;border-radius:4px;" />'
            )
        return '—'
    thumb_preview.short_description = 'Imagem'

    def total_produtos(self, obj):
        return obj.produtos.filter(ativo=True).count()
    total_produtos.short_description = 'Produtos ativos'


# ---------------------------------------------------------------------------
# Produto
# ---------------------------------------------------------------------------

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = (
        'thumb_principal', 'nome', 'categoria', 'preco', 'preco_promocional',
        'badge_promocao', 'total_estoque', 'media_avaliacao', 'ativo', 'destaque', 'novo',
    )
    list_editable = ('ativo', 'destaque', 'novo')
    list_filter = ('ativo', 'destaque', 'novo', 'categoria', 'genero')
    search_fields = ('nome', 'slug', 'sku', 'bling_id')
    prepopulated_fields = {'slug': ('nome',)}
    ordering = ('ordem', '-criado_em')
    date_hierarchy = 'criado_em'
    readonly_fields = ('criado_em', 'atualizado_em', 'slug')

    fieldsets = (
        ('Identificação', {
            'fields': ('nome', 'slug', 'categoria', 'genero', 'bling_id', 'sku'),
        }),
        ('Textos', {
            'fields': ('descricao', 'composicao'),
        }),
        ('Preços', {
            'fields': ('preco', 'preco_promocional'),
        }),
        ('Controle', {
            'fields': ('ativo', 'destaque', 'novo', 'ordem'),
        }),
        ('Datas', {
            'fields': ('criado_em', 'atualizado_em'),
            'classes': ('collapse',),
        }),
    )

    inlines = [ProdutoImagemInline, VariacaoInline, AvaliacaoInline]
    actions = ['marcar_ativo', 'marcar_inativo', 'marcar_destaque', 'remover_destaque']

    def thumb_principal(self, obj):
        img = obj.imagem_principal
        if img:
            return mark_safe(
                f'<img src="{img.imagem.url}" style="height:50px;width:50px;'
                f'object-fit:cover;border-radius:4px;" />'
            )
        return '—'
    thumb_principal.short_description = 'Foto'

    def badge_promocao(self, obj):
        if obj.em_promocao:
            return format_html(
                '<span style="background:#c9a96e;color:#fff;padding:2px 6px;'
                'border-radius:3px;font-size:11px;">-{}%</span>',
                obj.percentual_desconto,
            )
        return '—'
    badge_promocao.short_description = 'Desc.'

    def total_estoque(self, obj):
        total = sum(v.estoque for v in obj.variacoes.filter(ativa=True))
        if total == 0:
            cor = '#e74c3c'
        elif total < 5:
            cor = '#f39c12'
        else:
            cor = '#27ae60'
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>', cor, total
        )
    total_estoque.short_description = 'Estoque'

    def media_avaliacao(self, obj):
        media = obj.avaliacoes.filter(aprovada=True).aggregate(m=Avg('nota'))['m']
        if media is None:
            return '—'
        cheias = round(media)
        return format_html(
            '<span title="{:.1f}/5" style="color:#c9a96e;">{}{}</span>',
            media,
            '★' * cheias,
            '☆' * (5 - cheias),
        )
    media_avaliacao.short_description = 'Avaliação'

    @admin.action(description='Ativar produtos selecionados')
    def marcar_ativo(self, request, queryset):
        n = queryset.update(ativo=True)
        self.message_user(request, f'{n} produto(s) ativado(s).')

    @admin.action(description='Desativar produtos selecionados')
    def marcar_inativo(self, request, queryset):
        n = queryset.update(ativo=False)
        self.message_user(request, f'{n} produto(s) desativado(s).')

    @admin.action(description='Marcar como destaque na home')
    def marcar_destaque(self, request, queryset):
        n = queryset.update(destaque=True)
        self.message_user(request, f'{n} produto(s) marcado(s) como destaque.')

    @admin.action(description='Remover destaque da home')
    def remover_destaque(self, request, queryset):
        n = queryset.update(destaque=False)
        self.message_user(request, f'{n} produto(s) removido(s) do destaque.')


# ---------------------------------------------------------------------------
# Avaliação
# ---------------------------------------------------------------------------

@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    list_display = ('produto', 'nome_publico', 'nota_estrelas', 'titulo', 'aprovada', 'criada_em')
    list_filter = ('aprovada', 'nota')
    list_editable = ('aprovada',)
    search_fields = ('produto__nome', 'nome_publico', 'titulo', 'comentario')
    date_hierarchy = 'criada_em'
    readonly_fields = ('criada_em',)
    ordering = ('-criada_em',)
    actions = ['aprovar', 'reprovar']

    def nota_estrelas(self, obj):
        return format_html(
            '<span style="color:#c9a96e;">{}{}</span>',
            '★' * obj.nota,
            '☆' * (5 - obj.nota),
        )
    nota_estrelas.short_description = 'Nota'

    @admin.action(description='Aprovar avaliações selecionadas')
    def aprovar(self, request, queryset):
        n = queryset.update(aprovada=True)
        self.message_user(request, f'{n} avaliação(ões) aprovada(s).')

    @admin.action(description='Reprovar avaliações selecionadas')
    def reprovar(self, request, queryset):
        n = queryset.update(aprovada=False)
        self.message_user(request, f'{n} avaliação(ões) reprovada(s).')
