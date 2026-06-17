import csv
import io
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from django import forms
from django.contrib import admin
from django.contrib import messages as django_messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Avg
from django.db import transaction
from django.urls import path, reverse
from apps.core_utils.admin_mixin import DellaAdminMixin
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.admin.views.decorators import staff_member_required
from apps.core_utils.sanitize import sanitize_text
from .models import (
    Categoria, Produto, ProdutoImagem, Variacao, Avaliacao, CorPadrao,
    TamanhoPadrao, TabelaMedidas, TabelaMedidasLinha, ProdutoCorFoto,
    NewsletterInscricao,
)
from .forms import (
    ProdutoCorFotoForm, ProdutoAdminForm, CategoriaSubSelect,
    PENDING_PREFIX, StarRatingWidget, VariacaoInlineForm,
)


def _estilo_preview_cor(cor_primaria='', cor_secundaria=''):
    cor_primaria = cor_primaria or '#ccc'
    if cor_secundaria:
        return (
            f'background-color:{cor_primaria};'
            f'background-image:conic-gradient(from 135deg, {cor_primaria} 0deg 180deg, '
            f'{cor_secundaria} 180deg 360deg);'
        )
    return f'background-color:{cor_primaria};'


class CorPreviewSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-cor-hex'] = instance.codigo_hex or ''
            option['attrs']['data-cor-hex-secundario'] = instance.codigo_hex_secundario or ''
        return option


class AvaliacaoAdminForm(forms.ModelForm):
    class Meta:
        model = Avaliacao
        fields = '__all__'
        widgets = {
            'nota_experiencia': StarRatingWidget(),
            'nota_produtos': StarRatingWidget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome_campo in ('nota_experiencia', 'nota_produtos'):
            campo = self.fields.get(nome_campo)
            if campo is not None:
                campo.required = True
                campo.help_text = ''
                campo.widget.attrs['class'] = 'avaliacao-stars-admin'

    def clean(self):
        cleaned = super().clean()
        pedido = cleaned.get('pedido')
        if not pedido:
            self.add_error('pedido', 'Selecione o pedido para vincular a avaliação.')
        return cleaned


def _texto_importacao_chave(valor):
    bruto = unicodedata.normalize('NFKD', str(valor or ''))
    sem_acentos = ''.join(ch for ch in bruto if not unicodedata.combining(ch))
    sem_acentos = sem_acentos.replace('\xa0', ' ')
    sem_acentos = sem_acentos.replace('\ufeff', '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
    return ' '.join(sem_acentos.upper().split())


def _limpar_celula_planilha(valor):
    if valor is None:
        return ''
    texto = str(valor).strip()
    return texto.replace('\ufeff', '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').strip()


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class ProdutoImagemInline(admin.TabularInline):
    model = ProdutoImagem
    extra = 1
    fields = ('thumb_preview', 'imagem', 'cor', 'principal', 'ordem')
    readonly_fields = ('thumb_preview',)
    ordering = ('cor__ordem', 'cor__nome', 'ordem', 'id')
    verbose_name = 'Foto por cor do produto'
    verbose_name_plural = 'Fotos por cor do produto'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'cor':
            formfield.widget = CorPreviewSelect(attrs=formfield.widget.attrs)
        return formfield

    def thumb_preview(self, obj):
        if obj.imagem:
            return mark_safe(
                f'<img src="{obj.imagem.url}" style="height:70px;width:70px;'
                f'object-fit:contain;background:#fafaf8;'
                f'border-radius:6px;border:1px solid #eee;" />'
            )
        return '—'
    thumb_preview.short_description = 'Preview'


class VariacaoInline(admin.TabularInline):
    model = Variacao
    form = VariacaoInlineForm
    extra = 1
    fields = (
        'cor', 'cor_preview', 'tamanho', 'preco', 'preco_promocional',
        'disponibilidade', 'comportamento_sem_estoque', 'prazo_confeccao_dias',
        'estoque', 'sku_variacao', 'bling_variacao_id', 'usa_sync_bling', 'ativa', 'clonar_btn'
    )
    readonly_fields = ('cor_preview', 'clonar_btn')
    ordering = ('cor__ordem', 'cor__nome', 'tamanho__ordem')
    autocomplete_fields = []
    verbose_name = 'Variação'
    verbose_name_plural = 'Variações'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'cor':
            formfield.widget = CorPreviewSelect(attrs=formfield.widget.attrs)
        return formfield

    def cor_preview(self, obj):
        hex_val = obj.cor.codigo_hex if obj.cor_id and obj.cor.codigo_hex else ''
        hex_sec = obj.cor.codigo_hex_secundario if obj.cor_id and obj.cor.codigo_hex_secundario else ''
        if hex_val:
            return mark_safe(
                f'<span style="display:inline-block;width:22px;height:22px;'
                f'border-radius:50%;{_estilo_preview_cor(hex_val, hex_sec)}'
                f'border:1px solid #ccc;vertical-align:middle;" '
                f'title="{hex_val}"></span>'
            )
        return '—'
    cor_preview.short_description = '●'

    def clonar_btn(self, obj):
        return format_html(
            '<button type="button" class="della-inline-clone" '
            'title="Clona esta linha para você ajustar a próxima variação antes de salvar">Clonar</button>'
        )
    clonar_btn.short_description = 'Clonar'


class ProdutoCorFotoInline(admin.TabularInline):
    """
    Vincula uma foto já cadastrada do produto a uma cor específica.
    Ao clicar na bolinha da cor no site, a galeria troca para essa foto.
    Basta vincular UMA variação de cada cor — vale para todos os tamanhos.
    """
    model = ProdutoCorFoto
    form = ProdutoCorFotoForm
    extra = 0
    fields = ('cor', 'cor_preview', 'imagem', 'foto_preview')
    readonly_fields = ('cor_preview', 'foto_preview')
    verbose_name = 'Foto por cor'
    verbose_name_plural = 'Fotos por Cor'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Aplica widget de preview de cor + filtra `imagem` por produto sendo editado."""
        if db_field.name == 'imagem':
            parent_id = request.resolver_match.kwargs.get('object_id')
            if parent_id:
                kwargs['queryset'] = ProdutoImagem.objects.filter(produto_id=parent_id)
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'cor':
            formfield.widget = CorPreviewSelect(attrs=formfield.widget.attrs)
        return formfield

    def cor_preview(self, obj):
        if obj.cor_id and obj.cor.codigo_hex:
            hex1 = obj.cor.codigo_hex
            hex2 = obj.cor.codigo_hex_secundario
            return mark_safe(
                f'<span style="display:inline-block;width:22px;height:22px;'
                f'border-radius:50%;{_estilo_preview_cor(hex1, hex2)}'
                f'border:1px solid #ccc;vertical-align:middle;"></span>'
            )
        return '—'
    cor_preview.short_description = '●'

    def foto_preview(self, obj):
        if obj.imagem_id and obj.imagem.imagem:
            return mark_safe(
                f'<img src="{obj.imagem.imagem.url}" '
                f'style="height:70px;width:70px;object-fit:contain;background:#fafaf8;'
                f'border-radius:4px;border:1px solid #eee;" />'
            )
        return '—'
    foto_preview.short_description = 'Preview'


class TabelaMedidasLinhaInline(admin.TabularInline):
    model = TabelaMedidasLinha
    extra = 5
    fields = (
        'ordem', 'medida', 'unidade',
        'valor_1', 'valor_2', 'valor_3', 'valor_4', 'valor_5', 'valor_6',
    )
    ordering = ('ordem', 'id')
    verbose_name = 'Linha da tabela'
    verbose_name_plural = (
        'Linhas da tabela de medidas. Exemplo: Manequim, Peso medio, Busto, '
        'Cintura, Quadril.'
    )


class AvaliacaoInline(admin.StackedInline):
    model = Avaliacao
    extra = 0
    fields = ('nome_publico', 'nota', 'comentario', 'aprovada', 'criada_em')
    readonly_fields = ('criada_em',)
    ordering = ('-criada_em',)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Categoria — visão em árvore (mãe → filhas indentadas)
# ---------------------------------------------------------------------------

@admin.register(Categoria)
class CategoriaAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = ('nome_arvore', 'nivel_badge', 'slug', 'ativa', 'total_produtos', 'acoes_linha')
    change_list_template = 'admin/produtos/categoria_changelist.html'
    list_display_links = ('nome_arvore',)
    list_filter = ('ativa', 'parent')
    search_fields = ('nome', 'slug')
    prepopulated_fields = {'slug': ('nome',)}
    ordering = ('parent__id', 'parent__ordem', 'parent__nome', 'nome')

    class Media:
        js = ('admin/js/admin_linhas.js', 'admin/js/categoria_sort.js')

    fieldsets = (
        (None, {
            'fields': ('nome', 'slug', 'parent', 'ativa'),
        }),
    )

    def nome_arvore(self, obj):
        if obj.parent:
            return format_html(
                '<span style="color:#aaa;margin-right:4px;">└─</span> {}', obj.nome
            )
        return format_html('<strong>{}</strong>', obj.nome)
    nome_arvore.short_description = 'Categoria'

    def nivel_badge(self, obj):
        if obj.parent:
            return format_html(
                '<span style="background:#e8d5b0;color:#6b4f1e;padding:1px 7px;'
                'border-radius:3px;font-size:11px;">Sub</span>'
            )
        return format_html(
            '<span style="background:#c9a96e;color:#fff;padding:1px 7px;'
            'border-radius:3px;font-size:11px;">Mãe</span>'
        )
    nivel_badge.short_description = 'Nível'

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:produtos_categoria_change', args=[obj.pk])
        delete_url = reverse('admin:produtos_categoria_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir esta categoria?')
    acoes_linha.short_description = 'Ações'

    def total_produtos(self, obj):
        return obj.produtos.filter(ativo=True).count()
    total_produtos.short_description = 'Ativos'

    def save_model(self, request, obj, form, change):
        parent_changed = change and 'parent' in form.changed_data
        if not change or parent_changed:
            irmaos = Categoria.objects.filter(parent=obj.parent).exclude(pk=obj.pk)
            ultima_ordem = irmaos.order_by('-ordem').values_list('ordem', flat=True).first() or 0
            obj.ordem = ultima_ordem + 1
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import invalidar_categorias, invalidar_categoria_produtos
        invalidar_categorias()
        invalidar_categoria_produtos(obj.pk)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import invalidar_categorias, invalidar_categoria_produtos
        invalidar_categorias()
        invalidar_categoria_produtos(obj.pk)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('parent')

    def get_urls(self):
        urls = super().get_urls()
        extras = [
            path(
                'salvar-ordem/',
                self.admin_site.admin_view(self._salvar_ordem),
                name='produtos_categoria_salvar_ordem',
            ),
        ]
        return extras + urls

    def _build_categorias_tree(self):
        categorias = list(
            Categoria.objects.select_related('parent').order_by('parent__ordem', 'parent__nome', 'ordem', 'nome', 'pk')
        )
        maes = sorted(
            [categoria for categoria in categorias if categoria.parent_id is None],
            key=lambda categoria: (categoria.ordem, categoria.nome.lower(), categoria.pk),
        )
        filhas_por_mae = {}
        for categoria in categorias:
            if categoria.parent_id:
                filhas_por_mae.setdefault(categoria.parent_id, []).append(categoria)
        for filhas in filhas_por_mae.values():
            filhas.sort(key=lambda categoria: (categoria.ordem, categoria.nome.lower(), categoria.pk))

        tree = []
        for mae in maes:
            tree.append({
                'parent': mae,
                'children': filhas_por_mae.get(mae.pk, []),
            })
        return tree

    def _salvar_ordem(self, request):
        if request.method != 'POST':
            return JsonResponse({'error': 'Método inválido.'}, status=405)

        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Payload inválido.'}, status=400)

        parent_ids = payload.get('parents') or []
        children_map = payload.get('children') or {}

        maes = list(Categoria.objects.filter(parent__isnull=True).order_by('pk'))
        maes_ids = [categoria.pk for categoria in maes]

        if sorted(parent_ids) != sorted(maes_ids) or len(parent_ids) != len(maes_ids):
            return JsonResponse({'error': 'Lista de categorias mãe incompleta.'}, status=400)

        filhas_por_mae = {
            categoria_mae.pk: list(
                Categoria.objects.filter(parent_id=categoria_mae.pk).order_by('pk')
            )
            for categoria_mae in maes
        }

        for mae in maes:
            child_ids = children_map.get(str(mae.pk), children_map.get(mae.pk, [])) or []
            esperados = [categoria.pk for categoria in filhas_por_mae[mae.pk]]
            if sorted(child_ids) != sorted(esperados) or len(child_ids) != len(esperados):
                return JsonResponse(
                    {'error': f'Subcategorias incompletas para {mae.nome}.'},
                    status=400,
                )

        with transaction.atomic():
            for ordem_mae, categoria_id in enumerate(parent_ids, start=1):
                Categoria.objects.filter(pk=categoria_id, parent__isnull=True).update(ordem=ordem_mae)

            for mae in maes:
                child_ids = children_map.get(str(mae.pk), children_map.get(mae.pk, [])) or []
                for ordem_filha, categoria_id in enumerate(child_ids, start=1):
                    Categoria.objects.filter(pk=categoria_id, parent_id=mae.pk).update(ordem=ordem_filha)

        from apps.core_utils.cache_utils import invalidar_categorias
        invalidar_categorias()
        return JsonResponse({'ok': True})

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            response.context_data['categorias_tree'] = self._build_categorias_tree()
            response.context_data['categoria_sort_save_url'] = 'salvar-ordem/'
        except Exception:
            pass
        return response


# ---------------------------------------------------------------------------
# Produto
# ---------------------------------------------------------------------------

@admin.register(Produto)
class ProdutoAdmin(DellaAdminMixin, admin.ModelAdmin):
    form = ProdutoAdminForm
    IMPORT_PREVIEW_SESSION_KEY = 'produtos_import_preview_v2'
    IMPORT_FOTOS_PREVIEW_SESSION_KEY = 'produtos_import_fotos_preview_v1'
    list_display = (
        'thumb_principal', 'nome', 'categoria', 'preco_fmt', 'preco_promo_fmt',
        'badge_promocao', 'total_estoque', 'media_avaliacao', 'ativo', 'destaque', 'novo',
        'acoes_linha',
    )
    list_display_links = ('thumb_principal', 'nome')
    list_editable = ('ativo', 'destaque', 'novo')
    list_filter = ('ativo', 'destaque', 'novo', 'categoria')
    search_fields = ('nome', 'slug', 'sku')
    ordering = ('ordem', '-criado_em')
    date_hierarchy = 'criado_em'
    readonly_fields = ('criado_em', 'atualizado_em', 'slug')
    change_list_template = 'admin/produtos/produto_changelist.html'

    class Media:
        js = (
            'admin/js/admin_linhas.js',
            'admin/js/produto_admin.js',
            'admin/js/produto_admin_por_cor.js',
            'admin/js/produto_text_editor.js',
            'admin/js/variacao_sync_lock.js',
        )

    fieldsets = (
        ('Identificação', {
            'fields': ('nome', 'slug', 'categoria_pai', 'categoria'),
        }),
        ('Textos', {
            'fields': ('descricao', 'composicao'),
            'description': (
                'Descrição e composição aceitam formatação rica. '
                'Você pode ajustar negrito, alinhamento, tamanho de fonte, listas e recuos.'
            ),
        }),
        ('Preços', {
            'fields': ('preco', 'preco_promocional'),
            'description': 'Digite o valor com ponto como separador decimal. Ex: 512.00',
        }),
        ('Logística', {
            'fields': ('peso',),
            'description': 'Peso da peça em gramas — usado no cálculo de frete.',
        }),
        ('Controle e ordem', {
            'fields': ('ativo', 'destaque', 'novo', 'ordem'),
            'description': 'Ordem: número menor aparece primeiro na listagem.',
        }),
        ('SEO — Google', {
            'fields': ('seo_titulo', 'seo_descricao', 'seo_keywords'),
            'classes': ('collapse',),
            'description': (
                'Otimização para mecanismos de busca. '
                'Se deixar vazio, o site usa o nome e a descrição do produto automaticamente.'
            ),
        }),
        ('Datas', {
            'fields': ('criado_em', 'atualizado_em'),
            'classes': ('collapse',),
        }),
    )

    inlines = [ProdutoImagemInline, VariacaoInline]
    actions = [
        'marcar_ativo', 'marcar_inativo', 'marcar_destaque', 'remover_destaque',
        'ativar_sync_bling_variacoes', 'desativar_sync_bling_variacoes',
    ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Aplica o widget custom CategoriaSubSelect (com data-parent em cada
        <option>) e o queryset filtrado por subcategorias no campo `categoria`.
        Forma idiomática para admin — Django gerencia choices/wrapper sozinho."""
        if db_field.name == 'categoria':
            kwargs['queryset'] = (
                Categoria.objects
                .filter(parent__isnull=False)
                .select_related('parent')
                .order_by('parent__nome', 'ordem', 'nome')
            )
            kwargs['widget'] = CategoriaSubSelect()
        elif db_field.name == 'cor_principal':
            # Renderizado como hidden input: o radio nos cards de cor e a unica
            # interface de selecao. O JS sincroniza o radio com este campo.
            kwargs['queryset'] = CorPadrao.objects.order_by('ordem', 'nome')
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'cor_principal':
            from django.forms import HiddenInput
            formfield.widget = HiddenInput()
            formfield.required = False
        return formfield

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.core_utils.cache_utils import HOME_DESTAQUES, invalidar_categoria_produtos
        from django.core.cache import cache
        cache.delete(HOME_DESTAQUES)
        if obj.categoria_id:
            invalidar_categoria_produtos(obj.categoria_id)

    def save_related(self, request, form, formsets, change):
        """Salva imagens primeiro, resolve refs 'pending:imagens-N' nos forms
        de Foto por Cor, e só então salva o resto. Isso permite que o usuário
        suba fotos novas e já as escolha no inline de Foto por Cor no mesmo
        save (sem precisar de um save intermediário)."""
        imagens_fs = None
        cor_fotos_fs = None
        outros = []
        for fs in formsets:
            model = getattr(fs, 'model', None)
            if model is ProdutoImagem:
                imagens_fs = fs
            elif model is ProdutoCorFoto:
                cor_fotos_fs = fs
            else:
                outros.append(fs)

        form.save_m2m()

        # Envolve o save de imagens em transacao atomica: se qualquer imagem
        # falhar (ex: timeout de processamento), nenhuma alteracao e persistida,
        # evitando delecoes parciais que corrompem o conjunto de fotos.
        if imagens_fs is not None:
            with transaction.atomic():
                imagens_fs.save()

        if cor_fotos_fs is not None:
            prefix_to_imagem = {}
            if imagens_fs is not None:
                for sub in imagens_fs.forms:
                    if sub.instance.pk:
                        prefix_to_imagem[sub.prefix] = sub.instance

            for sub in cor_fotos_fs.forms:
                ref = getattr(sub, '_pending_imagem_ref', None)
                if not ref:
                    continue
                key = ref[len(PENDING_PREFIX):]
                imagem_obj = prefix_to_imagem.get(key)
                if imagem_obj is not None:
                    sub.instance.imagem = imagem_obj
                else:
                    sub.cleaned_data['DELETE'] = True

            cor_fotos_fs.save()

        for fs in outros:
            fs.save()

        self._sincronizar_foto_capa(form.instance)

    def _sincronizar_foto_capa(self, produto):
        imagens = list(produto.imagens.select_related('cor').order_by('ordem', 'id'))
        if not imagens:
            return

        # Se a cor principal atual nao tem nenhuma variacao ativa, descarta e
        # escolhe outra — cobre o caso de inativar ou deletar a variacao principal.
        if produto.cor_principal_id:
            tem_variacao_ativa = (
                produto.variacoes
                .filter(ativa=True, cor_id=produto.cor_principal_id)
                .exists()
            )
            if not tem_variacao_ativa:
                produto.cor_principal_id = None

        if not produto.cor_principal_id:
            cor_sugerida = (
                produto.variacoes
                .filter(ativa=True, cor__isnull=False)
                .order_by('cor__ordem', 'cor__nome', 'pk')
                .values_list('cor_id', flat=True)
                .first()
            )
            if not cor_sugerida:
                cor_sugerida = next((img.cor_id for img in imagens if img.cor_id), None)
            if cor_sugerida:
                Produto.objects.filter(pk=produto.pk).update(cor_principal_id=cor_sugerida)
                produto.cor_principal_id = cor_sugerida

        alvo = None
        if produto.cor_principal_id:
            alvo = next((img for img in imagens if img.cor_id == produto.cor_principal_id), None)
        if alvo is None:
            alvo = imagens[0]

        ProdutoImagem.objects.filter(produto=produto, principal=True).exclude(pk=alvo.pk).update(principal=False)
        if not alvo.principal:
            ProdutoImagem.objects.filter(pk=alvo.pk).update(principal=True)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        from apps.core_utils.cache_utils import HOME_DESTAQUES, invalidar_categoria_produtos
        from django.core.cache import cache
        cache.delete(HOME_DESTAQUES)
        if obj.categoria_id:
            invalidar_categoria_produtos(obj.categoria_id)

    def get_urls(self):
        urls = super().get_urls()
        extras = [
            path('produtos/variacao/<int:pk>/clonar/',
                 self.admin_site.admin_view(self._clonar_variacao),
                 name='produtos_variacao_clonar'),
            path('importar/',
                 self.admin_site.admin_view(self._importar_view),
                 name='produtos_produto_importar'),
            path('importar-fotos/',
                 self.admin_site.admin_view(self._importar_fotos_view),
                 name='produtos_produto_importar_fotos'),
            path('modelo-csv/',
                 self.admin_site.admin_view(self._modelo_csv),
                 name='produtos_produto_modelo_csv'),
            path('exportar-csv/',
                 self.admin_site.admin_view(self._exportar_csv),
                 name='produtos_produto_exportar_csv'),
        ]
        return extras + urls

    # Mapeamento de nomes de cor → HEX automático
    _COR_HEX = {
        'PRETO': '#000000', 'BRANCO': '#FFFFFF', 'BRANCA': '#FFFFFF',
        'AZUL MARINHO': '#001F5B', 'MARINHO': '#001F5B',
        'AZUL': '#1E3A8A', 'AZUL ROYAL': '#2444B0', 'AZUL CELESTE': '#7EC8E3',
        'AZUL BEBÊ': '#BFDBFE', 'AZUL TURQUESA': '#06B6D4',
        'VERMELHO': '#DC2626', 'VINHO': '#7F1D1D', 'BORDÔ': '#6B1D1D', 'BORDO': '#6B1D1D',
        'ROSA': '#EC4899', 'ROSA CHÁ': '#E8B4A0', 'ROSA CHA': '#E8B4A0',
        'ROSA NUDE': '#E8B4A0', 'ROSE': '#FFB6C1', 'ROSA BEBÊ': '#FFD1DC',
        'VERDE': '#16A34A', 'VERDE MILITAR': '#4D6B47', 'MUSGO': '#4D6B47',
        'VERDE MENTA': '#98FF98', 'MENTA': '#98FF98',
        'AMARELO': '#FACC15', 'LARANJA': '#F97316', 'CORAL': '#FF7F50',
        'SALMÃO': '#FA8072', 'SALMAO': '#FA8072',
        'TERRACOTA': '#C2603D', 'CARAMELO': '#C27B3D', 'COBRE': '#B87333',
        'NUDE': '#D4A574', 'FENDI': '#E8D5B0', 'BEGE': '#D2B48C',
        'CREME': '#FFF8DC', 'OFF WHITE': '#F5F5F0', 'OFFWHITE': '#F5F5F0',
        'CINZA': '#6B7280', 'CINZA MESCLA': '#9CA3AF', 'CHUMBO': '#4B5563',
        'MARROM': '#92400E', 'CHOCOLATE': '#7B3F00',
        'ROXO': '#7C3AED', 'LILÁS': '#C084FC', 'LILAS': '#C084FC',
        'DOURADO': '#D4AF37', 'PRATA': '#C0C0C0',
        'ESTAMPADO': '#888888', 'ESTAMPA': '#888888',
    }

    def _hex_da_cor(self, nome_cor):
        """Retorna o HEX mais próximo para um nome de cor, ou '' se não encontrado."""
        chave = nome_cor.upper().strip()
        return self._COR_HEX.get(chave, '')

    def _parse_nome_variacao(self, nome_completo):
        """
        Faz parse de 'BODY GIU (AZUL MARINHO) (PP)' → (modelo, cor, tamanho).
        """
        import re as _re
        bruto = unicodedata.normalize('NFKC', str(nome_completo or ''))
        bruto = bruto.replace('\xa0', ' ').replace('（', '(').replace('）', ')')
        bruto = ' '.join(bruto.split())
        m = _re.match(r'^(.*?)\s*[\(]\s*(.+?)\s*[\)]\s*[\(]\s*(.+?)\s*[\)]\s*$', bruto)
        if not m:
            return None, None, None
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()

    def _ler_arquivo(self, arquivo):
        """
        Lê o arquivo enviado (CSV ou XLSX) e retorna lista de dicts.
        """
        nome = arquivo.name.lower()

        if nome.endswith('.xlsx') or nome.endswith('.xls'):
            import openpyxl
            wb = openpyxl.load_workbook(arquivo, data_only=True)
            ws = wb.active
            rows = list(ws.values)
            if not rows:
                return []
            headers = [_limpar_celula_planilha(h) if h else '' for h in rows[0]]
            data = []
            for row in rows[1:]:
                data.append({
                    headers[i]: (_limpar_celula_planilha(row[i]) if i < len(row) and row[i] is not None else '')
                    for i in range(len(headers))
                })
        else:
            decoded = arquivo.read().decode('utf-8-sig')
            sample = decoded[:4096]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
            except csv.Error:
                dialect = csv.excel
                dialect.delimiter = ';' if sample.count(';') > sample.count(',') else ','
            reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
            data = list(reader)
        return data

    def _get_valor_coluna(self, row, *aliases):
        aliases_norm = {alias.lower().strip() for alias in aliases}
        for chave, valor in row.items():
            chave_limpa = _limpar_celula_planilha(chave).lower()
            if chave_limpa in aliases_norm:
                return _limpar_celula_planilha(valor)
        return ''

    def _linha_vazia(self, row):
        return not any(str(v).strip() for v in row.values() if v is not None)

    def _parse_bool(self, valor):
        bruto = (str(valor or '')).strip().lower()
        if bruto in ('sim', 's', 'yes', 'y', '1', 'true', 'ativo', 'ativa'):
            return True, None
        if bruto in ('nao', 'não', 'n', 'no', '0', 'false', 'inativo', 'inativa'):
            return False, None
        return None, f'valor booleano inválido "{valor}"'

    def _parse_decimal(self, valor, campo, obrigatorio=False):
        bruto = str(valor or '').strip()
        if not bruto:
            if obrigatorio:
                return None, f'{campo} não informado'
            return None, None
        bruto = bruto.replace('R$', '').replace(' ', '')
        if ',' in bruto:
            bruto = bruto.replace('.', '').replace(',', '.')
        try:
            return Decimal(bruto), None
        except (InvalidOperation, ValueError):
            return None, f'{campo} inválido "{valor}"'

    def _parse_int(self, valor, campo, obrigatorio=False, minimo=None):
        bruto = str(valor or '').strip()
        if not bruto:
            if obrigatorio:
                return None, f'{campo} não informado'
            return None, None
        try:
            numero = int(float(bruto.replace(',', '.')))
        except (TypeError, ValueError):
            return None, f'{campo} inválido "{valor}"'
        if minimo is not None and numero < minimo:
            return None, f'{campo} deve ser maior ou igual a {minimo}'
        return numero, None

    def _parse_disponibilidade(self, valor):
        bruto = (str(valor or '')).strip().lower()
        if bruto in ('imediata', 'disponibilidade imediata', 'pronta entrega', 'pronta-entrega'):
            return Variacao.DISPONIBILIDADE_IMEDIATA, None
        if bruto in ('sob demanda', 'sob_demanda', 'sob encomenda', 'encomenda'):
            return Variacao.DISPONIBILIDADE_SOB_DEMANDA, None
        return None, f'disponibilidade inválida "{valor}"'

    def _resolver_categoria(self, categoria_pai_nome, subcategoria_nome=''):
        categoria_pai_nome = (categoria_pai_nome or '').strip()
        subcategoria_nome = (subcategoria_nome or '').strip()

        if subcategoria_nome:
            if not categoria_pai_nome:
                return None, 'categoria_pai não informada para a subcategoria'
            categoria_pai = Categoria.objects.filter(
                nome__iexact=categoria_pai_nome,
                parent__isnull=True,
            ).first()
            if not categoria_pai:
                return None, f'categoria pai "{categoria_pai_nome}" não cadastrada'
            subcategoria = Categoria.objects.filter(
                nome__iexact=subcategoria_nome,
                parent=categoria_pai,
            ).first()
            if not subcategoria:
                return None, f'subcategoria "{subcategoria_nome}" não cadastrada em "{categoria_pai_nome}"'
            return subcategoria, None

        if not categoria_pai_nome:
            return None, 'categoria_pai não informada'

        categoria_pai = Categoria.objects.filter(
            nome__iexact=categoria_pai_nome,
            parent__isnull=True,
        ).first()
        if not categoria_pai:
            return None, f'categoria pai "{categoria_pai_nome}" não cadastrada'
        return categoria_pai, None

    def _mapa_nomes_normalizados(self, queryset):
        mapa = {}
        duplicados = {}
        for obj in queryset:
            chave = _texto_importacao_chave(getattr(obj, 'nome', ''))
            if not chave:
                continue
            if chave in mapa:
                duplicados.setdefault(chave, [mapa[chave]]).append(obj)
            else:
                mapa[chave] = obj
        return mapa, duplicados

    def _mapa_subcategorias_normalizadas(self):
        mapa = {}
        duplicados = {}
        for categoria in Categoria.objects.select_related('parent').filter(parent__isnull=False):
            chave = (
                _texto_importacao_chave(categoria.parent.nome),
                _texto_importacao_chave(categoria.nome),
            )
            if chave in mapa:
                duplicados.setdefault(chave, [mapa[chave]]).append(categoria)
            else:
                mapa[chave] = categoria
        return mapa, duplicados

    def _resolver_cor(self, nome):
        cor = CorPadrao.objects.filter(nome__iexact=(nome or '').strip()).first()
        if not cor:
            return None, f'cor "{nome}" não cadastrada'
        return cor, None

    def _resolver_tamanho(self, nome):
        tamanho = TamanhoPadrao.objects.filter(nome__iexact=(nome or '').strip()).first()
        if not tamanho:
            return None, f'tamanho "{nome}" não cadastrado'
        return tamanho, None

    def _validar_planilha_produtos(self, rows):
        campos = {
            'nome': ('nome',),
            'categoria_pai': ('categoria_pai', 'categoria pai'),
            'subcategoria': ('subcategoria', 'sub categoria'),
            'descricao': ('descricao', 'descrição'),
            'composicao': ('composicao', 'composição'),
            'preco': ('preco_geral', 'preço_geral', 'preco geral', 'preco', 'preço'),
            'preco_promocional': ('preco_promocional_geral', 'preço promocional geral', 'preco promocional geral', 'preco_promocional', 'preço promocional'),
            'peso': ('peso',),
            'ativo': ('ativo',),
            'destaque': ('destaque',),
            'novo': ('novo',),
            'ordem': ('ordem',),
            'seo_titulo': ('seo_titulo', 'seo titulo'),
            'seo_descricao': ('seo_descricao', 'seo descrição', 'seo descricao'),
            'seo_keywords': ('palavra_chave', 'palavra chave', 'palavras_chave', 'seo_keywords'),
            'disponibilidade': ('disponibilidade',),
            'prazo_confeccao_dias': ('prazo_confeccao_dias', 'prazo confecção dias', 'prazo confeccao dias'),
            'estoque': ('estoque',),
            'sku_variacao': ('sku',),
            'bling_variacao_id': ('id_bling', 'id bling'),
            'preco_variacao': ('preco_variacao', 'preço_variacao', 'preco variação', 'preço variação'),
            'preco_promocional_variacao': (
                'preco_promocional_variacao', 'preço_promocional_variacao',
                'preco promocional variação', 'preço promocional variação'
            ),
        }

        grupos = {}
        erros = []
        avisos = []
        produtos_mapa, produtos_duplicados = self._mapa_nomes_normalizados(Produto.objects.all())
        cores_mapa, cores_duplicadas = self._mapa_nomes_normalizados(CorPadrao.objects.all())
        tamanhos_mapa, tamanhos_duplicados = self._mapa_nomes_normalizados(TamanhoPadrao.objects.all())
        categorias_mae_mapa, categorias_mae_duplicadas = self._mapa_nomes_normalizados(
            Categoria.objects.filter(parent__isnull=True)
        )
        subcategorias_mapa, subcategorias_duplicadas = self._mapa_subcategorias_normalizadas()

        for i, row in enumerate(rows, start=2):
            if self._linha_vazia(row):
                continue

            nome_completo = self._get_valor_coluna(row, *campos['nome'])
            modelo, cor_nome, tam_nome = self._parse_nome_variacao(nome_completo)
            if not modelo:
                erros.append(
                    f'Linha {i}: o campo nome deve estar no formato MODELO (COR) (TAMANHO). '
                    f'Valor lido: "{nome_completo}".'
                )
                continue

            grupo = grupos.setdefault(_texto_importacao_chave(modelo), {
                'modelo': modelo,
                'linhas': [],
                'produto': {k: '' for k in (
                    'categoria_pai', 'subcategoria', 'descricao', 'composicao', 'preco', 'preco_promocional',
                    'peso', 'ativo', 'destaque', 'novo', 'ordem',
                    'seo_titulo', 'seo_descricao', 'seo_keywords',
                )},
                'conflitos': [],
            })

            linha = {
                'linha': i,
                'nome_completo': nome_completo,
                'modelo': modelo,
                'cor_nome': cor_nome,
                'tam_nome': tam_nome,
                'disponibilidade_raw': self._get_valor_coluna(row, *campos['disponibilidade']),
                'prazo_confeccao_dias_raw': self._get_valor_coluna(row, *campos['prazo_confeccao_dias']),
                'estoque_raw': self._get_valor_coluna(row, *campos['estoque']),
                'sku_variacao': self._get_valor_coluna(row, *campos['sku_variacao']),
                'bling_variacao_id': self._get_valor_coluna(row, *campos['bling_variacao_id']),
                'preco_variacao_raw': self._get_valor_coluna(row, *campos['preco_variacao']),
                'preco_promocional_variacao_raw': self._get_valor_coluna(row, *campos['preco_promocional_variacao']),
            }
            grupo['linhas'].append(linha)

            for campo in grupo['produto'].keys():
                aliases = campos[campo]
                valor = self._get_valor_coluna(row, *aliases)
                if valor == '':
                    continue
                atual = grupo['produto'][campo]
                if atual == '':
                    grupo['produto'][campo] = valor
                elif str(atual).strip() != str(valor).strip():
                    grupo['conflitos'].append(
                        f'Linha {i}: conflito no campo "{campo}" para o produto "{modelo}".'
                    )

        preview_grupos = []
        total_variacoes = 0
        produtos_criar = 0
        produtos_atualizar = 0
        variacoes_criar = 0
        variacoes_atualizar = 0
        campos_opcionais = {
            'descricao', 'composicao', 'preco_promocional',
            'seo_titulo', 'seo_descricao', 'seo_keywords',
        }

        for _key, grupo in grupos.items():
            erros.extend(grupo['conflitos'])
            dados_produto = grupo['produto']
            modelo = grupo['modelo']
            modelo_chave = _texto_importacao_chave(modelo)
            if modelo_chave in produtos_duplicados:
                erros.append(
                    f'Produto "{modelo}": existem cadastros duplicados com o mesmo nome base, diferenciados apenas por acento ou caixa.'
                )
            produto_existente = produtos_mapa.get(modelo_chave)
            status_produto = 'Atualizar' if produto_existente else 'Criar'
            if produto_existente:
                produtos_atualizar += 1
            else:
                produtos_criar += 1

            categoria_obj = None
            categoria_pai_nome = dados_produto['categoria_pai']
            subcategoria_nome = dados_produto['subcategoria']
            if not categoria_pai_nome:
                erros.append(f'Produto "{modelo}": campo "categoria_pai" não informado.')
            else:
                categoria_pai_chave = _texto_importacao_chave(categoria_pai_nome)
                if categoria_pai_chave in categorias_mae_duplicadas:
                    erros.append(
                        f'Produto "{modelo}": existem categorias pai duplicadas para "{categoria_pai_nome}", diferenciadas apenas por acento ou caixa.'
                    )
                elif subcategoria_nome:
                    subcategoria_chave = (categoria_pai_chave, _texto_importacao_chave(subcategoria_nome))
                    if subcategoria_chave in subcategorias_duplicadas:
                        erros.append(
                            f'Produto "{modelo}": existem subcategorias duplicadas para "{subcategoria_nome}" em "{categoria_pai_nome}", diferenciadas apenas por acento ou caixa.'
                        )
                    else:
                        categoria_obj = subcategorias_mapa.get(subcategoria_chave)
                        if not categoria_obj:
                            erros.append(
                                f'Produto "{modelo}": subcategoria "{subcategoria_nome}" não cadastrada em "{categoria_pai_nome}".'
                            )
                else:
                    categoria_obj = categorias_mae_mapa.get(categoria_pai_chave)
                    if not categoria_obj:
                        erros.append(f'Produto "{modelo}": categoria pai "{categoria_pai_nome}" não cadastrada.')

            for campo_obrigatorio in ('preco', 'peso', 'ativo', 'destaque', 'novo'):
                if not str(dados_produto.get(campo_obrigatorio, '')).strip():
                    erros.append(f'Produto "{modelo}": campo "{campo_obrigatorio}" não informado.')
            for campo_opcional in campos_opcionais:
                if not str(dados_produto.get(campo_opcional, '')).strip():
                    avisos.append(f'Produto "{modelo}": campo "{campo_opcional}" não informado.')

            preco, erro_preco = self._parse_decimal(dados_produto['preco'], 'preço', obrigatorio=True)
            if erro_preco:
                erros.append(f'Produto "{modelo}": {erro_preco}.')

            preco_promocional, erro_promo = self._parse_decimal(
                dados_produto['preco_promocional'], 'preço promocional', obrigatorio=False
            )
            if erro_promo:
                erros.append(f'Produto "{modelo}": {erro_promo}.')

            peso, erro_peso = self._parse_int(dados_produto['peso'], 'peso', obrigatorio=True, minimo=1)
            if erro_peso:
                erros.append(f'Produto "{modelo}": {erro_peso}.')

            ativo, erro_ativo = self._parse_bool(dados_produto['ativo'])
            destaque, erro_destaque = self._parse_bool(dados_produto['destaque'])
            novo, erro_novo = self._parse_bool(dados_produto['novo'])
            for erro_bool in (erro_ativo, erro_destaque, erro_novo):
                if erro_bool:
                    erros.append(f'Produto "{modelo}": {erro_bool}.')

            ordem, erro_ordem = self._parse_int(dados_produto['ordem'], 'ordem', obrigatorio=False, minimo=0)
            if erro_ordem:
                erros.append(f'Produto "{modelo}": {erro_ordem}.')

            preview_linhas = []
            vistos = set()
            for linha in grupo['linhas']:
                chave_var = (
                    _texto_importacao_chave(linha['cor_nome']),
                    _texto_importacao_chave(linha['tam_nome']),
                )
                if chave_var in vistos:
                    erros.append(
                        f'Linha {linha["linha"]}: variação duplicada para "{modelo}" '
                        f'({linha["cor_nome"]} / {linha["tam_nome"]}).'
                    )
                vistos.add(chave_var)

                cor_obj = None
                cor_sera_criada = False
                cor_chave = _texto_importacao_chave(linha['cor_nome'])
                if cor_chave in cores_duplicadas:
                    erros.append(
                        f'Linha {linha["linha"]}: existem cores duplicadas para "{linha["cor_nome"]}", diferenciadas apenas por acento ou caixa.'
                    )
                else:
                    cor_obj = cores_mapa.get(cor_chave)
                if not cor_obj:
                    avisos.append(
                        f'Linha {linha["linha"]}: cor "{linha["cor_nome"]}" não cadastrada. A cor será criada sem código HEX.'
                    )
                    cor_sera_criada = True
                tamanho_obj = None
                tamanho_chave = _texto_importacao_chave(linha['tam_nome'])
                if tamanho_chave in tamanhos_duplicados:
                    erros.append(
                        f'Linha {linha["linha"]}: existem tamanhos duplicados para "{linha["tam_nome"]}", diferenciados apenas por acento ou caixa.'
                    )
                else:
                    tamanho_obj = tamanhos_mapa.get(tamanho_chave)
                if not tamanho_obj:
                    erros.append(f'Linha {linha["linha"]}: tamanho "{linha["tam_nome"]}" não cadastrado.')

                disponibilidade, erro_disp = self._parse_disponibilidade(linha['disponibilidade_raw'])
                if erro_disp:
                    erros.append(f'Linha {linha["linha"]}: {erro_disp}.')

                prazo_confeccao, erro_prazo = self._parse_int(
                    linha['prazo_confeccao_dias_raw'],
                    'prazo_confeccao_dias',
                    obrigatorio=False,
                    minimo=1,
                )
                if erro_prazo:
                    erros.append(f'Linha {linha["linha"]}: {erro_prazo}.')

                if disponibilidade == Variacao.DISPONIBILIDADE_SOB_DEMANDA and prazo_confeccao is None:
                    erros.append(
                        f'Linha {linha["linha"]}: informe prazo_confeccao_dias para variações sob demanda.'
                    )
                if disponibilidade == Variacao.DISPONIBILIDADE_IMEDIATA and prazo_confeccao is not None:
                    avisos.append(
                        f'Linha {linha["linha"]}: prazo_confeccao_dias preenchido para disponibilidade imediata '
                        f'— será usado apenas se "comportamento_sem_estoque" for "sob_demanda".'
                    )

                estoque, erro_estoque = self._parse_int(
                    linha['estoque_raw'],
                    'estoque',
                    obrigatorio=(disponibilidade == Variacao.DISPONIBILIDADE_IMEDIATA),
                    minimo=0,
                )
                if erro_estoque:
                    erros.append(f'Linha {linha["linha"]}: {erro_estoque}.')
                if disponibilidade == Variacao.DISPONIBILIDADE_SOB_DEMANDA and estoque is None:
                    estoque = 0

                preco_variacao, erro_preco_variacao = self._parse_decimal(
                    linha['preco_variacao_raw'], 'preco_variacao', obrigatorio=False
                )
                if erro_preco_variacao:
                    erros.append(f'Linha {linha["linha"]}: {erro_preco_variacao}.')

                preco_promocional_variacao, erro_promo_variacao = self._parse_decimal(
                    linha['preco_promocional_variacao_raw'], 'preco_promocional_variacao', obrigatorio=False
                )
                if erro_promo_variacao:
                    erros.append(f'Linha {linha["linha"]}: {erro_promo_variacao}.')
                preco_base_aplicado = preco_variacao if preco_variacao is not None else preco
                if (
                    preco_promocional_variacao is not None and
                    preco_base_aplicado is not None and
                    preco_promocional_variacao >= preco_base_aplicado
                ):
                    erros.append(
                        f'Linha {linha["linha"]}: preco_promocional_variacao deve ser menor que o preço aplicado.'
                    )

                variacao_existente = None
                if produto_existente and cor_obj and tamanho_obj:
                    variacao_existente = Variacao.objects.filter(
                        produto=produto_existente,
                        cor=cor_obj,
                        tamanho=tamanho_obj,
                    ).first()
                status_variacao = 'Atualizar' if variacao_existente else 'Criar'
                if variacao_existente:
                    variacoes_atualizar += 1
                else:
                    variacoes_criar += 1

                total_variacoes += 1
                preview_linhas.append({
                    'linha': linha['linha'],
                    'nome_completo': linha['nome_completo'],
                    'cor_nome': linha['cor_nome'],
                    'tam_nome': linha['tam_nome'],
                    'disponibilidade': disponibilidade or '',
                    'prazo_confeccao_dias': prazo_confeccao,
                    'estoque': estoque if estoque is not None else '',
                    'sku_variacao': linha['sku_variacao'],
                    'bling_variacao_id': linha['bling_variacao_id'],
                    'preco_variacao': str(preco_variacao) if preco_variacao is not None else '',
                    'preco_promocional_variacao': str(preco_promocional_variacao) if preco_promocional_variacao is not None else '',
                    'status_variacao': status_variacao,
                    'cor_sera_criada': cor_sera_criada,
                    'cor_id': cor_obj.pk if cor_obj else None,
                    'tamanho_id': tamanho_obj.pk if tamanho_obj else None,
                })

            preview_grupos.append({
                'modelo': modelo,
                'produto_id': produto_existente.pk if produto_existente else None,
                'status_produto': status_produto,
                'categoria': (
                    f'{categoria_pai_nome} > {subcategoria_nome}'
                    if subcategoria_nome else categoria_pai_nome
                ),
                'preview_linhas': preview_linhas,
                'produto': {
                    'categoria_pai': categoria_pai_nome,
                    'subcategoria': subcategoria_nome,
                    'descricao': dados_produto['descricao'],
                    'composicao': dados_produto['composicao'],
                    'preco': str(preco) if preco is not None else '',
                    'preco_promocional': str(preco_promocional) if preco_promocional is not None else '',
                    'peso': peso if peso is not None else '',
                    'ativo': ativo,
                    'destaque': destaque,
                    'novo': novo,
                    'ordem': ordem if ordem is not None else '',
                    'seo_titulo': dados_produto['seo_titulo'],
                    'seo_descricao': dados_produto['seo_descricao'],
                    'seo_keywords': dados_produto['seo_keywords'],
                },
                'categoria_id': categoria_obj.pk if categoria_obj else None,
            })

        return {
            'grupos': preview_grupos,
            'erros': erros,
            'avisos': avisos,
            'resumo': {
                'produtos_criar': produtos_criar,
                'produtos_atualizar': produtos_atualizar,
                'variacoes_criar': variacoes_criar,
                'variacoes_atualizar': variacoes_atualizar,
                'total_variacoes': total_variacoes,
            },
            'pode_importar': not erros and bool(preview_grupos),
        }

    def _modelo_csv(self, request):
        """Baixa um arquivo CSV modelo para validação/importação completa."""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="modelo_importacao_produtos.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'nome', 'categoria_pai', 'subcategoria', 'descricao', 'composicao',
            'preco_geral', 'preco_promocional_geral', 'peso',
            'ativo', 'destaque', 'novo', 'ordem',
            'seo_titulo', 'seo_descricao', 'palavra_chave',
            'preco_variacao', 'preco_promocional_variacao',
            'disponibilidade', 'prazo_confeccao_dias', 'estoque', 'sku', 'id_bling',
        ])
        writer.writerow([
            'Body Adriana (Preto) (P)', 'Moda Praia', 'Body', 'Descrição do produto', 'Poliéster 95% Elastano 5%',
            '299.90', '', '500',
            'sim', 'não', 'sim', '10',
            'Body Adriana Della', 'Body Adriana premium', 'body adriana, body preto, moda premium',
            '', '',
            'disponibilidade imediata', '', '5', '4334', '15819914733',
        ])
        writer.writerow([
            'Body Adriana (Preto) (M)', 'Moda Praia', 'Body', 'Descrição do produto', 'Poliéster 95% Elastano 5%',
            '299.90', '', '500',
            'sim', 'não', 'sim', '10',
            'Body Adriana Della', 'Body Adriana premium', 'body adriana, body preto, moda premium',
            '329.90', '279.90',
            'sob demanda', '7', '0', '4335', '15819914734',
        ])
        return response

    def _exportar_csv(self, request):
        """Exporta todos os produtos cadastrados no mesmo formato CSV da importação."""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="produtos_exportados.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'nome', 'categoria_pai', 'subcategoria', 'descricao', 'composicao',
            'preco_geral', 'preco_promocional_geral', 'peso',
            'ativo', 'destaque', 'novo', 'ordem',
            'seo_titulo', 'seo_descricao', 'palavra_chave',
            'preco_variacao', 'preco_promocional_variacao',
            'disponibilidade', 'prazo_confeccao_dias', 'estoque', 'sku', 'id_bling',
        ])
        produtos = Produto.objects.select_related('categoria').prefetch_related(
            'variacoes__cor', 'variacoes__tamanho'
        ).order_by('categoria__nome', 'nome')
        for produto in produtos:
            variacoes = list(
                produto.variacoes.filter(ativa=True).order_by('cor__nome', 'tamanho__ordem')
            )
            ativo = 'sim' if produto.ativo else 'não'
            destaque = 'sim' if produto.destaque else 'não'
            novo = 'sim' if produto.novo else 'não'
            for var in variacoes:
                nome_variacao = produto.nome
                if var.cor_id and var.tamanho_id:
                    nome_variacao = f'{produto.nome} ({var.cor.nome}) ({var.tamanho.nome})'
                writer.writerow([
                    nome_variacao,
                    produto.categoria.parent.nome if produto.categoria_id and produto.categoria.parent_id else (produto.categoria.nome if produto.categoria_id else ''),
                    produto.categoria.nome if produto.categoria_id and produto.categoria.parent_id else '',
                    produto.descricao or '',
                    produto.composicao or '',
                    str(produto.preco),
                    str(produto.preco_promocional) if produto.preco_promocional else '',
                    str(produto.peso or ''),
                    ativo, destaque, novo,
                    str(produto.ordem or ''),
                    produto.seo_titulo or '',
                    produto.seo_descricao or '',
                    produto.seo_keywords or '',
                    str(var.preco) if var.preco is not None else '',
                    str(var.preco_promocional) if var.preco_promocional is not None else '',
                    var.get_disponibilidade_display().lower(),
                    str(var.prazo_confeccao_dias or ''),
                    str(var.estoque),
                    var.sku_variacao or '',
                    var.bling_variacao_id or '',
                ])
            if not variacoes:
                writer.writerow([
                    produto.nome,
                    produto.categoria.parent.nome if produto.categoria_id and produto.categoria.parent_id else (produto.categoria.nome if produto.categoria_id else ''),
                    produto.categoria.nome if produto.categoria_id and produto.categoria.parent_id else '',
                    produto.descricao or '',
                    produto.composicao or '',
                    str(produto.preco),
                    str(produto.preco_promocional) if produto.preco_promocional else '',
                    str(produto.peso or ''),
                    ativo, destaque, novo,
                    str(produto.ordem or ''),
                    produto.seo_titulo or '',
                    produto.seo_descricao or '',
                    produto.seo_keywords or '',
                    '', '',
                    '', '', '', '', '',
                ])
        return response

    def _importar_preview_confirmado(self, preview):
        produtos_criados = 0
        produtos_atualizados = 0
        variacoes_criadas = 0
        variacoes_atualizadas = 0
        cores_criadas_no_import = {}

        with transaction.atomic():
            for grupo in preview['grupos']:
                dados = grupo['produto']
                categoria = Categoria.objects.get(pk=grupo['categoria_id'])
                produto = Produto.objects.filter(pk=grupo.get('produto_id')).first() if grupo.get('produto_id') else None
                criado = produto is None
                if criado:
                    produto = Produto(nome=grupo['modelo'])
                    produtos_criados += 1
                else:
                    produtos_atualizados += 1

                produto.categoria = categoria
                produto.descricao = (dados['descricao'] or produto.descricao or grupo['modelo']).strip()
                produto.composicao = (dados['composicao'] or produto.composicao or '').strip()
                produto.preco = Decimal(dados['preco'])
                produto.preco_promocional = Decimal(dados['preco_promocional']) if dados['preco_promocional'] else None
                produto.peso = int(dados['peso'])
                produto.ativo = bool(dados['ativo'])
                produto.destaque = bool(dados['destaque'])
                produto.novo = bool(dados['novo'])
                produto.ordem = int(dados['ordem']) if str(dados['ordem']).strip() else 0
                produto.seo_titulo = dados['seo_titulo']
                produto.seo_descricao = dados['seo_descricao']
                produto.seo_keywords = dados['seo_keywords']
                produto.save()

                for linha in grupo['preview_linhas']:
                    cor = CorPadrao.objects.filter(pk=linha.get('cor_id')).first() if linha.get('cor_id') else None
                    if not cor:
                        # Cache local protege contra duplicate na mesma rodada
                        # (várias linhas da planilha com a mesma cor nova) e o
                        # filter(nome__iexact) cobre criação concorrente por
                        # outro request entre a validação e o import.
                        cor_chave = _texto_importacao_chave(linha['cor_nome'])
                        cor = cores_criadas_no_import.get(cor_chave)
                        if not cor:
                            nome_upper = sanitize_text(linha['cor_nome'], max_length=50).upper()
                            cor = CorPadrao.objects.filter(nome__iexact=nome_upper).first()
                            if not cor:
                                cor = CorPadrao.objects.create(
                                    nome=nome_upper,
                                    codigo_hex='',
                                    codigo_hex_secundario='',
                                )
                            cores_criadas_no_import[cor_chave] = cor
                    tamanho = TamanhoPadrao.objects.get(pk=linha['tamanho_id'])
                    variacao = Variacao.objects.filter(produto=produto, cor=cor, tamanho=tamanho).first()
                    if variacao:
                        variacoes_atualizadas += 1
                    else:
                        variacao = Variacao(produto=produto, cor=cor, tamanho=tamanho)
                        variacoes_criadas += 1

                    variacao.disponibilidade = linha['disponibilidade']
                    variacao.prazo_confeccao_dias = linha['prazo_confeccao_dias'] or None
                    variacao.preco = Decimal(linha['preco_variacao']) if linha['preco_variacao'] else None
                    variacao.preco_promocional = (
                        Decimal(linha['preco_promocional_variacao'])
                        if linha['preco_promocional_variacao'] else None
                    )
                    variacao.estoque = int(linha['estoque'] or 0)
                    variacao.sku_variacao = linha['sku_variacao']
                    variacao.bling_variacao_id = linha['bling_variacao_id']
                    variacao.ativa = True
                    variacao.save()

        return produtos_criados, produtos_atualizados, variacoes_criadas, variacoes_atualizadas

    def _importar_view(self, request):
        """View de importação de produtos com validação prévia."""
        context = {
            'title': 'Importar produtos',
            'opts': self.model._meta,
            'has_view_permission': True,
        }
        if request.method == 'GET':
            request.session.pop(self.IMPORT_PREVIEW_SESSION_KEY, None)
            return render(request, 'admin/produtos/importar.html', context)

        preview_session = request.session.get(self.IMPORT_PREVIEW_SESSION_KEY)
        if preview_session:
            context['preview'] = preview_session

        if request.method == 'POST':
            acao = request.POST.get('acao', '').strip()
            if acao == 'validar' and request.FILES.get('arquivo_csv'):
                arquivo = request.FILES['arquivo_csv']
                try:
                    rows = self._ler_arquivo(arquivo)
                    preview = self._validar_planilha_produtos(rows)
                    preview['arquivo_nome'] = arquivo.name
                    request.session[self.IMPORT_PREVIEW_SESSION_KEY] = preview
                    context['preview'] = preview
                except Exception as e:
                    self.message_user(request, f'Erro ao validar arquivo: {e}', django_messages.ERROR)
            elif acao == 'importar_confirmado':
                preview = request.session.get(self.IMPORT_PREVIEW_SESSION_KEY)
                if not preview:
                    self.message_user(request, 'Valide a planilha antes de importar.', django_messages.WARNING)
                elif not preview.get('pode_importar'):
                    self.message_user(request, 'A planilha possui erros e não pode ser importada.', django_messages.ERROR)
                    context['preview'] = preview
                else:
                    try:
                        criados, atualizados, vars_criadas, vars_atualizadas = self._importar_preview_confirmado(preview)
                        request.session.pop(self.IMPORT_PREVIEW_SESSION_KEY, None)
                        self.message_user(
                            request,
                            (
                                f'{criados} produto(s) criado(s), {atualizados} atualizado(s), '
                                f'{vars_criadas} variação(ões) criada(s) e {vars_atualizadas} atualizada(s).'
                            ),
                            django_messages.SUCCESS,
                        )
                        return HttpResponseRedirect('/painel/produtos/produto/')
                    except Exception as e:
                        self.message_user(request, f'Erro ao importar arquivo: {e}', django_messages.ERROR)
                        context['preview'] = preview
            else:
                preview = request.session.get(self.IMPORT_PREVIEW_SESSION_KEY)
                if preview:
                    context['preview'] = preview

        return render(request, 'admin/produtos/importar.html', context)

    # ------------------------------------------------------------------
    # Importação de fotos via ZIP
    # ------------------------------------------------------------------
    EXTENSOES_FOTO_ZIP = {'.png', '.jpg', '.jpeg', '.webp'}

    def _importar_fotos_view(self, request):
        """View de importação de fotos via ZIP. Cada pasta de primeiro nível
        do ZIP corresponde ao nome de um produto pai cadastrado. Produtos que
        já têm fotos são ignorados."""
        import os

        context = {
            'title': 'Importar fotos via ZIP',
            'opts': self.model._meta,
            'has_view_permission': True,
        }

        def _limpar_temp(preview):
            zip_path = (preview or {}).get('zip_path')
            if zip_path:
                try:
                    os.unlink(zip_path)
                except OSError:
                    pass

        if request.method == 'GET':
            old = request.session.pop(self.IMPORT_FOTOS_PREVIEW_SESSION_KEY, None)
            _limpar_temp(old)
            return render(request, 'admin/produtos/importar_fotos.html', context)

        preview_session = request.session.get(self.IMPORT_FOTOS_PREVIEW_SESSION_KEY)
        if preview_session:
            context['preview'] = preview_session

        if request.method == 'POST':
            acao = request.POST.get('acao', '').strip()
            if acao == 'validar' and request.FILES.get('arquivo_zip'):
                arquivo = request.FILES['arquivo_zip']
                old = request.session.get(self.IMPORT_FOTOS_PREVIEW_SESSION_KEY)
                _limpar_temp(old)
                try:
                    preview = self._validar_zip_fotos(arquivo)
                    preview['arquivo_nome'] = arquivo.name
                    request.session[self.IMPORT_FOTOS_PREVIEW_SESSION_KEY] = preview
                    context['preview'] = preview
                except Exception as e:
                    self.message_user(request, f'Erro ao validar ZIP: {e}', django_messages.ERROR)
            elif acao == 'importar_confirmado':
                preview = request.session.get(self.IMPORT_FOTOS_PREVIEW_SESSION_KEY)
                if not preview:
                    self.message_user(request, 'Valide o ZIP antes de importar.', django_messages.WARNING)
                elif not preview.get('pode_importar'):
                    self.message_user(request, 'O ZIP possui erros e não pode ser importado.', django_messages.ERROR)
                    context['preview'] = preview
                else:
                    try:
                        produtos_atualizados, fotos_criadas = self._importar_fotos_zip_confirmado(preview)
                        _limpar_temp(preview)
                        request.session.pop(self.IMPORT_FOTOS_PREVIEW_SESSION_KEY, None)
                        self.message_user(
                            request,
                            f'{produtos_atualizados} produto(s) atualizado(s), {fotos_criadas} foto(s) importada(s).',
                            django_messages.SUCCESS,
                        )
                        return HttpResponseRedirect('/painel/produtos/produto/')
                    except Exception as e:
                        self.message_user(request, f'Erro ao importar ZIP: {e}', django_messages.ERROR)
                        context['preview'] = preview

        return render(request, 'admin/produtos/importar_fotos.html', context)

    def _validar_zip_fotos(self, arquivo_zip):
        """Lê o ZIP, agrupa por pasta e valida contra produtos cadastrados.
        Salva o ZIP num tempfile cujo path é gravado em preview['zip_path']
        para ser reusado no import confirmado."""
        import os
        import tempfile
        import zipfile

        fd, tmp_path = tempfile.mkstemp(prefix='della_import_fotos_', suffix='.zip')
        try:
            with os.fdopen(fd, 'wb') as f:
                for chunk in arquivo_zip.chunks():
                    f.write(chunk)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        produtos_por_chave = {}
        for p in Produto.objects.all().only('id', 'nome'):
            chave = _texto_importacao_chave(p.nome)
            if chave and chave not in produtos_por_chave:
                produtos_por_chave[chave] = (p.id, p.nome)

        produtos_com_foto_ids = set(
            ProdutoImagem.objects.values_list('produto_id', flat=True).distinct()
        )

        pastas = {}
        try:
            with zipfile.ZipFile(tmp_path) as zf:
                # Detecta se existe uma pasta wrapper única (ex: o usuário zipou
                # a pasta-pai inteira em vez de só o conteúdo) e desconta o prefixo
                primeiros = set()
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    nome = info.filename.replace('\\', '/')
                    if nome.startswith('__MACOSX'):
                        continue
                    base = os.path.basename(nome)
                    if not base or base.startswith('.'):
                        continue
                    parts = nome.split('/')
                    if len(parts) >= 2:
                        primeiros.add(parts[0])
                    else:
                        primeiros.add('')
                wrapper = None
                if len(primeiros) == 1:
                    candidato = next(iter(primeiros))
                    if candidato:
                        wrapper = candidato + '/'

                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    nome = info.filename.replace('\\', '/')
                    if nome.startswith('__MACOSX'):
                        continue
                    base = os.path.basename(nome)
                    if not base or base.startswith('.'):
                        continue
                    ext = os.path.splitext(base)[1].lower()
                    if ext not in self.EXTENSOES_FOTO_ZIP:
                        continue
                    rel = nome[len(wrapper):] if wrapper and nome.startswith(wrapper) else nome
                    parts = rel.split('/')
                    pasta = parts[0] if len(parts) >= 2 else '(raiz)'
                    pastas.setdefault(pasta, []).append((info.filename, base))
        except zipfile.BadZipFile:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise ValueError('O arquivo enviado não é um ZIP válido.')

        linhas = []
        avisos = []
        erros = []
        produtos_atualizar = 0
        fotos_total = 0
        pastas_ja_com_fotos = 0
        pastas_sem_produto = 0

        for pasta in sorted(pastas.keys(), key=lambda s: s.lower()):
            arquivos = pastas[pasta]
            chave = _texto_importacao_chave(pasta)
            match = produtos_por_chave.get(chave)

            if match is None:
                pastas_sem_produto += 1
                avisos.append(f'Pasta "{pasta}": produto não encontrado, será ignorada.')
                linhas.append({
                    'pasta': pasta,
                    'produto_id': None,
                    'produto_nome': None,
                    'status': 'sem_produto',
                    'qtd_fotos': len(arquivos),
                    'arquivos': [b for _, b in arquivos],
                })
                continue

            produto_id, produto_nome = match

            if produto_id in produtos_com_foto_ids:
                pastas_ja_com_fotos += 1
                avisos.append(
                    f'Pasta "{pasta}": produto "{produto_nome}" já tem fotos cadastradas, será ignorada.'
                )
                linhas.append({
                    'pasta': pasta,
                    'produto_id': produto_id,
                    'produto_nome': produto_nome,
                    'status': 'ja_tem_fotos',
                    'qtd_fotos': len(arquivos),
                    'arquivos': [b for _, b in arquivos],
                })
                continue

            produtos_atualizar += 1
            fotos_total += len(arquivos)
            linhas.append({
                'pasta': pasta,
                'produto_id': produto_id,
                'produto_nome': produto_nome,
                'status': 'ok',
                'qtd_fotos': len(arquivos),
                'arquivos': [b for _, b in arquivos],
                'arquivos_zip': [zn for zn, _ in arquivos],
            })

        if not pastas:
            erros.append('O ZIP não contém arquivos de imagem (.png/.jpg/.jpeg/.webp).')

        pode_importar = (produtos_atualizar > 0) and not erros

        try:
            tamanho_kb = round(os.path.getsize(tmp_path) / 1024, 1)
        except OSError:
            tamanho_kb = 0

        return {
            'arquivo_nome': '',
            'tamanho_kb': tamanho_kb,
            'zip_path': tmp_path,
            'resumo': {
                'pastas_total': len(pastas),
                'produtos_atualizar': produtos_atualizar,
                'fotos_total': fotos_total,
                'pastas_ja_com_fotos': pastas_ja_com_fotos,
                'pastas_sem_produto': pastas_sem_produto,
            },
            'linhas': linhas,
            'avisos': avisos,
            'erros': erros,
            'pode_importar': pode_importar,
        }

    def _importar_fotos_zip_confirmado(self, preview):
        """Lê o ZIP do tempfile salvo na validação e cria ProdutoImagem para
        cada pasta com status='ok'. Re-checa no momento do save que o produto
        ainda não tem fotos (proteção contra concorrência)."""
        import os
        import zipfile
        from django.core.files.base import ContentFile
        from apps.core_utils.cache_utils import invalidar_categoria_produtos

        zip_path = preview.get('zip_path')
        if not zip_path or not os.path.exists(zip_path):
            raise ValueError('Arquivo ZIP temporário não encontrado. Reenvie o arquivo.')

        produtos_atualizados = 0
        fotos_criadas = 0

        with zipfile.ZipFile(zip_path) as zf:
            for linha in preview.get('linhas', []):
                if linha.get('status') != 'ok':
                    continue
                produto_id = linha.get('produto_id')
                arquivos_zip = linha.get('arquivos_zip') or []
                if not produto_id or not arquivos_zip:
                    continue
                try:
                    produto = Produto.objects.get(id=produto_id)
                except Produto.DoesNotExist:
                    continue

                if ProdutoImagem.objects.filter(produto_id=produto_id).exists():
                    continue

                cor_padrao = produto.cor_principal
                if cor_padrao is None:
                    primeira_variacao = (
                        produto.variacoes
                        .filter(ativa=True, cor__isnull=False)
                        .select_related('cor')
                        .order_by('cor__ordem', 'cor__nome', 'pk')
                        .first()
                    )
                    cor_padrao = primeira_variacao.cor if primeira_variacao else None

                with transaction.atomic():
                    criou_alguma = False
                    for ordem, zn in enumerate(sorted(arquivos_zip)):
                        try:
                            data = zf.read(zn)
                        except KeyError:
                            continue
                        base = os.path.basename(zn.replace('\\', '/'))
                        img = ProdutoImagem(
                            produto=produto,
                            cor=cor_padrao,
                            principal=(not criou_alguma),
                            ordem=ordem,
                        )
                        img.imagem.save(base, ContentFile(data), save=False)
                        img.save()
                        fotos_criadas += 1
                        criou_alguma = True
                    if criou_alguma:
                        produtos_atualizados += 1
                        if produto.categoria_id:
                            invalidar_categoria_produtos(produto.categoria_id)

        return produtos_atualizados, fotos_criadas

    def _clonar_variacao(self, request, pk):
        var = get_object_or_404(Variacao, pk=pk)
        self.message_user(
            request,
            'Atualize a página e use o botão "Clonar" direto na linha da variação. '
            'O clone agora acontece antes de salvar, sem criar duplicatas escondidas.',
            django_messages.WARNING,
        )
        return HttpResponseRedirect(
            f'/painel/produtos/produto/{var.produto_id}/change/#variacoes'
        )

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:produtos_produto_change', args=[obj.pk])
        delete_url = reverse('admin:produtos_produto_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este produto?')
    acoes_linha.short_description = 'Ações'

    def thumb_principal(self, obj):
        img = obj.imagem_principal
        if img:
            return mark_safe(
                f'<img src="{img.imagem.url}" style="height:50px;width:50px;'
                f'object-fit:cover;border-radius:4px;" />'
            )
        return '—'
    thumb_principal.short_description = 'Foto'

    def preco_fmt(self, obj):
        return f'R$ {obj.preco:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    preco_fmt.short_description = 'Preço'

    def preco_promo_fmt(self, obj):
        if obj.preco_promocional:
            return format_html(
                '<span style="color:#27ae60;">R$ {}</span>',
                f'{obj.preco_promocional:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
            )
        return '—'
    preco_promo_fmt.short_description = 'Promoção'

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

    @admin.action(description='Ativar sync estoque Bling em TODAS as variações dos produtos selecionados')
    def ativar_sync_bling_variacoes(self, request, queryset):
        n = Variacao.objects.filter(produto__in=queryset).update(usa_sync_bling=True)
        self.message_user(
            request,
            f'{n} variação(ões) marcada(s) com sync Bling ativo em '
            f'{queryset.count()} produto(s). '
            'O cron a cada 15 min vai começar a sincronizar o estoque automaticamente.',
        )

    @admin.action(description='Desativar sync estoque Bling em TODAS as variações dos produtos selecionados')
    def desativar_sync_bling_variacoes(self, request, queryset):
        n = Variacao.objects.filter(produto__in=queryset).update(usa_sync_bling=False)
        self.message_user(
            request,
            f'{n} variação(ões) com sync Bling desativado em '
            f'{queryset.count()} produto(s).',
        )


# ---------------------------------------------------------------------------
# Cor e Tamanho padrão
# ---------------------------------------------------------------------------

@admin.register(CorPadrao)
class CorPadraoAdmin(DellaAdminMixin, admin.ModelAdmin):
    IMPORT_PREVIEW_SESSION_KEY = 'corpadrao_import_preview_v1'
    change_list_template = 'admin/produtos/corpadrao_changelist.html'
    list_display = ('cor_bolinha', 'nome', 'codigo_hex', 'ordem', 'acoes_linha')
    list_editable = ('ordem',)
    list_display_links = ('nome',)
    search_fields = ('nome',)
    ordering = ('ordem', 'nome')

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def get_urls(self):
        urls = super().get_urls()
        extras = [
            path(
                'importar/',
                self.admin_site.admin_view(self._importar_view),
                name='produtos_corpadrao_importar',
            ),
            path(
                'modelo-csv/',
                self.admin_site.admin_view(self._modelo_csv),
                name='produtos_corpadrao_modelo_csv',
            ),
            path(
                'exportar-csv/',
                self.admin_site.admin_view(self._exportar_csv),
                name='produtos_corpadrao_exportar_csv',
            ),
        ]
        return extras + urls

    def _ler_arquivo(self, arquivo):
        """Lê CSV/XLSX com colunas do cadastro de CorPadrao."""
        nome = arquivo.name.lower()

        if nome.endswith('.xlsx') or nome.endswith('.xls'):
            import openpyxl
            wb = openpyxl.load_workbook(arquivo, data_only=True)
            ws = wb.active
            rows = list(ws.values)
            if not rows:
                return []
            headers = [_limpar_celula_planilha(h) if h else '' for h in rows[0]]
            data = []
            for row in rows[1:]:
                data.append({
                    headers[i]: (_limpar_celula_planilha(row[i]) if i < len(row) and row[i] is not None else '')
                    for i in range(len(headers))
                })
            return data

        decoded = arquivo.read().decode('utf-8-sig')
        sample = decoded[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ';' if sample.count(';') > sample.count(',') else ','
        reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
        data = []
        for row in reader:
            data.append({
                _limpar_celula_planilha(chave): _limpar_celula_planilha(valor)
                for chave, valor in row.items()
            })
        return data

    def _get_valor_coluna(self, row, *nomes):
        for nome in nomes:
            for chave, valor in row.items():
                if _limpar_celula_planilha(chave).lower() == nome.lower():
                    return _limpar_celula_planilha(valor)
        return ''

    def _modelo_csv(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="modelo_importacao_cores_padrao.csv"'
        writer = csv.writer(response)
        writer.writerow(['nome', 'codigo_hex', 'codigo_hex_secundario', 'ordem'])
        writer.writerow(['PRETO', '#000000', '', '1'])
        writer.writerow(['PRETO/BRANCO', '#000000', '#FFFFFF', '2'])
        writer.writerow(['ROSA CHA', '#E8B4A0', '', '3'])
        return response

    def _exportar_csv(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="cores_padrao_exportadas.csv"'
        writer = csv.writer(response)
        writer.writerow(['nome', 'codigo_hex', 'codigo_hex_secundario', 'ordem'])
        for cor in CorPadrao.objects.order_by('ordem', 'nome'):
            writer.writerow([
                cor.nome,
                cor.codigo_hex or '',
                cor.codigo_hex_secundario or '',
                cor.ordem,
            ])
        return response

    def _linha_vazia(self, row):
        return not any(str(valor).strip() for valor in row.values() if valor is not None)

    def _normalizar_hex(self, valor):
        valor = str(valor or '').strip().upper()
        if not valor:
            return ''
        if not valor.startswith('#'):
            valor = f'#{valor}'
        return valor

    def _hex_valido(self, valor):
        if not valor:
            return True
        return bool(re.fullmatch(r'#[0-9A-F]{6}', valor))

    def _mapa_nomes_normalizados(self, queryset):
        mapa = {}
        duplicados = {}
        for obj in queryset:
            chave = _texto_importacao_chave(getattr(obj, 'nome', ''))
            if not chave:
                continue
            if chave in mapa:
                duplicados.setdefault(chave, [mapa[chave]]).append(obj)
            else:
                mapa[chave] = obj
        return mapa, duplicados

    def _validar_planilha_cores(self, rows):
        preview = {
            'erros': [],
            'avisos': [],
            'linhas': [],
            'resumo': {
                'criar': 0,
                'atualizar': 0,
            },
            'pode_importar': False,
        }
        nomes_vistos = set()
        cores_mapa, cores_duplicadas = self._mapa_nomes_normalizados(CorPadrao.objects.all())

        for i, row in enumerate(rows, start=2):
            if self._linha_vazia(row):
                continue

            nome = self._get_valor_coluna(row, 'nome', 'cor', 'nome da cor')
            if not nome:
                preview['erros'].append(f'Linha {i}: nome da cor não informado.')
                continue

            nome_sanitizado = sanitize_text(nome, max_length=50).upper()
            nome_chave = _texto_importacao_chave(nome_sanitizado)
            if not nome_sanitizado:
                preview['erros'].append(f'Linha {i}: nome da cor ficou vazio após a validação.')
                continue
            if nome_chave in nomes_vistos:
                preview['erros'].append(f'Linha {i}: cor duplicada no arquivo ({nome_sanitizado}).')
                continue
            nomes_vistos.add(nome_chave)

            codigo_hex = self._normalizar_hex(
                self._get_valor_coluna(row, 'codigo_hex', 'código hex', 'codigo hex')
            )
            codigo_hex_secundario = self._normalizar_hex(self._get_valor_coluna(
                row,
                'codigo_hex_secundario',
                'código hex secundário',
                'codigo hex secundario',
            ))
            ordem_raw = self._get_valor_coluna(row, 'ordem')

            if not self._hex_valido(codigo_hex):
                preview['erros'].append(f'Linha {i} ({nome_sanitizado}): código HEX principal inválido ({codigo_hex}).')
                continue
            if not self._hex_valido(codigo_hex_secundario):
                preview['erros'].append(
                    f'Linha {i} ({nome_sanitizado}): código HEX secundário inválido ({codigo_hex_secundario}).'
                )
                continue

            try:
                ordem = int(str(ordem_raw).strip()) if str(ordem_raw).strip() else 0
            except (TypeError, ValueError):
                preview['erros'].append(f'Linha {i}: ordem inválida "{ordem_raw}".')
                continue

            if nome_chave in cores_duplicadas:
                preview['erros'].append(
                    f'Linha {i} ({nome_sanitizado}): já existem cores cadastradas com o mesmo nome base, diferenciadas apenas por acento ou caixa.'
                )
                continue

            cor_existente = cores_mapa.get(nome_chave)
            status = 'Atualizar' if cor_existente else 'Criar'
            preview['resumo']['atualizar' if cor_existente else 'criar'] += 1
            preview['linhas'].append({
                'linha_numero': i,
                'nome': nome_sanitizado,
                'nome_chave': nome_chave,
                'codigo_hex': codigo_hex,
                'codigo_hex_secundario': codigo_hex_secundario,
                'ordem': ordem,
                'status': status,
                'cor_id': cor_existente.pk if cor_existente else None,
            })

        preview['pode_importar'] = bool(preview['linhas']) and not preview['erros']
        if not preview['linhas'] and not preview['erros']:
            preview['avisos'].append('Nenhuma linha válida foi encontrada na planilha.')
        return preview

    @transaction.atomic
    def _importar_preview_confirmado(self, preview):
        criadas = 0
        atualizadas = 0

        for linha in preview.get('linhas', []):
            cor = CorPadrao.objects.filter(pk=linha.get('cor_id')).first() if linha.get('cor_id') else None
            if cor:
                atualizadas += 1
            else:
                cor = CorPadrao()
                criadas += 1
            cor.nome = linha['nome']
            cor.codigo_hex = linha['codigo_hex']
            cor.codigo_hex_secundario = linha['codigo_hex_secundario']
            cor.ordem = linha['ordem']
            cor.save()

        return criadas, atualizadas

    def _importar_view(self, request):
        context = {
            'title': 'Importar cores padrão',
            'opts': self.model._meta,
            'has_view_permission': True,
        }
        if request.method == 'GET':
            request.session.pop(self.IMPORT_PREVIEW_SESSION_KEY, None)
            return render(request, 'admin/produtos/importar_cores.html', context)

        preview_session = request.session.get(self.IMPORT_PREVIEW_SESSION_KEY)
        if preview_session:
            context['preview'] = preview_session

        if request.method == 'POST':
            acao = request.POST.get('acao', '').strip()
            if acao == 'validar' and request.FILES.get('arquivo_csv'):
                arquivo = request.FILES['arquivo_csv']
                try:
                    rows = self._ler_arquivo(arquivo)
                    preview = self._validar_planilha_cores(rows)
                    preview['arquivo_nome'] = arquivo.name
                    request.session[self.IMPORT_PREVIEW_SESSION_KEY] = preview
                    context['preview'] = preview
                except Exception as e:
                    self.message_user(request, f'Erro ao validar arquivo: {e}', django_messages.ERROR)
            elif acao == 'importar_confirmado':
                preview = request.session.get(self.IMPORT_PREVIEW_SESSION_KEY)
                if not preview:
                    self.message_user(request, 'Valide a planilha antes de importar.', django_messages.WARNING)
                elif not preview.get('pode_importar'):
                    self.message_user(request, 'A planilha possui erros e não pode ser importada.', django_messages.ERROR)
                    context['preview'] = preview
                else:
                    try:
                        criadas, atualizadas = self._importar_preview_confirmado(preview)
                        request.session.pop(self.IMPORT_PREVIEW_SESSION_KEY, None)
                        self.message_user(
                            request,
                            f'{criadas} cor(es) criada(s) e {atualizadas} atualizada(s).',
                            django_messages.SUCCESS,
                        )
                        return HttpResponseRedirect('/painel/produtos/corpadrao/')
                    except Exception as e:
                        self.message_user(request, f'Erro ao importar arquivo: {e}', django_messages.ERROR)
                        context['preview'] = preview

        return render(request, 'admin/produtos/importar_cores.html', context)

    def cor_bolinha(self, obj):
        if obj.codigo_hex:
            return mark_safe(
                f'<span style="display:inline-block;width:24px;height:24px;'
                f'border-radius:50%;{_estilo_preview_cor(obj.codigo_hex, obj.codigo_hex_secundario)}'
                f'border:1px solid #ccc;vertical-align:middle;"></span>'
            )
        return '—'
    cor_bolinha.short_description = '●'

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:produtos_corpadrao_change', args=[obj.pk])
        delete_url = reverse('admin:produtos_corpadrao_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir esta cor?')
    acoes_linha.short_description = 'Ações'


@admin.register(TamanhoPadrao)
class TamanhoPadraoAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = ('nome', 'ordem', 'acoes_linha')
    list_editable = ('ordem',)
    list_display_links = ('nome',)
    search_fields = ('nome',)
    ordering = ('ordem', 'nome')

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:produtos_tamanhopadrao_change', args=[obj.pk])
        delete_url = reverse('admin:produtos_tamanhopadrao_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este tamanho?')
    acoes_linha.short_description = 'Ações'


# ---------------------------------------------------------------------------
# Tabela de medidas
# ---------------------------------------------------------------------------

@admin.register(TabelaMedidas)
class TabelaMedidasAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display = ('nome', 'ativo', 'acoes_linha')
    list_display_links = ('nome',)
    list_editable = ('ativo',)
    list_filter = ('ativo',)
    ordering = ('nome',)
    inlines = (TabelaMedidasLinhaInline,)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    fieldsets = (
        (None, {
            'fields': ('nome', 'ativo'),
        }),
        ('Cabeçalho das colunas', {
            'fields': (
                'cabecalho_1', 'cabecalho_2', 'cabecalho_3',
                'cabecalho_4', 'cabecalho_5', 'cabecalho_6',
            ),
            'description': (
                'Defina os tamanhos nas colunas da tabela. '
                'As quatro primeiras já vêm como P, M, G e GG.'
            ),
        }),
        ('Conteúdo legado', {
            'fields': ('conteudo',),
            'classes': ('collapse',),
            'description': (
                'Opcional. Se a tabela tiver linhas cadastradas abaixo, o site '
                'usa a versão estruturada e ignora este campo.'
            ),
        }),
    )

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:produtos_tabelamedidas_change', args=[obj.pk])
        delete_url = reverse('admin:produtos_tabelamedidas_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir esta tabela?')
    acoes_linha.short_description = 'Ações'

    def _invalidar_cache_tabelas(self):
        from apps.core_utils.cache_utils import invalidar_tabelas_medidas
        invalidar_tabelas_medidas()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._invalidar_cache_tabelas()

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        self._invalidar_cache_tabelas()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        self._invalidar_cache_tabelas()


# ---------------------------------------------------------------------------
# Avaliação
# ---------------------------------------------------------------------------

@admin.register(Avaliacao)
class AvaliacaoAdmin(DellaAdminMixin, admin.ModelAdmin):
    form = AvaliacaoAdminForm
    list_display = (
        'nome_publico', 'pedido_ref', 'nota_experiencia_estrelas',
        'nota_produtos_estrelas', 'nota_estrelas', 'comentario_resumo',
        'aprovada', 'criada_em', 'acoes_linha',
    )
    list_display_links = ('nome_publico',)
    list_filter = ('aprovada', 'nota', 'nota_experiencia', 'nota_produtos')
    list_editable = ('aprovada',)
    search_fields = ('nome_publico', 'comentario', 'pedido__numero', 'cliente__email')

    class Media:
        js = ('admin/js/admin_linhas.js', 'js/star-rating.js')
        css = {'all': ('admin/css/della_admin.css',)}
    date_hierarchy = 'criada_em'
    readonly_fields = ('cliente_resumo', 'nome_publico_resumo', 'criada_em')
    ordering = ('-criada_em',)
    actions = ['aprovar', 'reprovar']
    fields = (
        'pedido',
        'cliente_resumo',
        'nome_publico_resumo',
        'nota_experiencia',
        'nota_produtos',
        'comentario',
        'aprovada',
        'criada_em',
    )

    def cliente_resumo(self, obj):
        if obj.cliente_id:
            return obj.cliente.email
        if obj.pedido_id and obj.pedido.cliente_id:
            return obj.pedido.cliente.email
        return 'Será puxado automaticamente pelo pedido'
    cliente_resumo.short_description = 'Cliente'

    def nome_publico_resumo(self, obj):
        if obj.nome_publico:
            return obj.nome_publico
        if obj.pedido_id:
            nome = (obj.pedido.cliente.nome if obj.pedido.cliente_id and obj.pedido.cliente.nome else obj.pedido.nome_completo).split()[0]
            return nome
        return 'Será puxado automaticamente pelo pedido'
    nome_publico_resumo.short_description = 'Nome público'

    def pedido_ref(self, obj):
        return obj.pedido.numero if obj.pedido_id else '—'
    pedido_ref.short_description = 'Pedido'

    def save_model(self, request, obj, form, change):
        if obj.pedido_id:
            obj.cliente = obj.pedido.cliente
            nome_base = ''
            if obj.pedido.cliente_id and getattr(obj.pedido.cliente, 'nome', ''):
                nome_base = obj.pedido.cliente.nome
            else:
                nome_base = obj.pedido.nome_completo or ''
            obj.nome_publico = (nome_base.split()[0] if nome_base else 'Cliente')
            obj.produto = None
        super().save_model(request, obj, form, change)

    def nota_estrelas(self, obj):
        return format_html(
            '<span style="color:#c9a96e;">{}{}</span>',
            '★' * obj.nota,
            '☆' * (5 - obj.nota),
        )
    nota_estrelas.short_description = 'Nota'

    def nota_experiencia_estrelas(self, obj):
        if not obj.nota_experiencia:
            return '—'
        return format_html(
            '<span style="color:#c9a96e;">{}{}</span>',
            '★' * obj.nota_experiencia,
            '☆' * (5 - obj.nota_experiencia),
        )
    nota_experiencia_estrelas.short_description = 'Compra'

    def nota_produtos_estrelas(self, obj):
        if not obj.nota_produtos:
            return '—'
        return format_html(
            '<span style="color:#c9a96e;">{}{}</span>',
            '★' * obj.nota_produtos,
            '☆' * (5 - obj.nota_produtos),
        )
    nota_produtos_estrelas.short_description = 'Produtos'

    def comentario_resumo(self, obj):
        if obj.comentario:
            return obj.comentario[:80] + ('…' if len(obj.comentario) > 80 else '')
        return '—'
    comentario_resumo.short_description = 'Comentário'

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:produtos_avaliacao_change', args=[obj.pk])
        delete_url = reverse('admin:produtos_avaliacao_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir esta avaliação?')
    acoes_linha.short_description = 'Ações'

    @admin.action(description='Aprovar avaliações selecionadas')
    def aprovar(self, request, queryset):
        n = queryset.update(aprovada=True)
        self.message_user(request, f'{n} avaliação(ões) aprovada(s).')

    @admin.action(description='Reprovar avaliações selecionadas')
    def reprovar(self, request, queryset):
        n = queryset.update(aprovada=False)
        self.message_user(request, f'{n} avaliação(ões) reprovada(s).')


@admin.register(NewsletterInscricao)
class NewsletterInscricaoAdmin(DellaAdminMixin, admin.ModelAdmin):
    list_display  = ('email', 'inscrito_em', 'ativo', 'acoes_linha')
    list_display_links = ('email',)
    list_editable = ('ativo',)
    list_filter   = ('ativo',)
    search_fields = ('email',)
    readonly_fields = ('inscrito_em',)
    ordering = ('-inscrito_em',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def _resetar_flag_usuario(self, emails):
        """Zera recebe_newsletter dos Users com e-mail correspondente às inscrições removidas."""
        if not emails:
            return
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.filter(email__in=emails, recebe_newsletter=True).update(
            recebe_newsletter=False
        )

    def delete_model(self, request, obj):
        email = obj.email
        super().delete_model(request, obj)
        self._resetar_flag_usuario([email])

    def delete_queryset(self, request, queryset):
        emails = list(queryset.values_list('email', flat=True))
        super().delete_queryset(request, queryset)
        self._resetar_flag_usuario(emails)

    def acoes_linha(self, obj):
        edit_url   = reverse('admin:produtos_newsletterinscricao_change', args=[obj.pk])
        delete_url = reverse('admin:produtos_newsletterinscricao_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir esta inscrição?')
    acoes_linha.short_description = 'Ações'
