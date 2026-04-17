import csv
import io
from django.contrib import admin
from django.contrib import messages as django_messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Avg
from django.urls import path
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.admin.views.decorators import staff_member_required
from .models import Categoria, Produto, ProdutoImagem, Variacao, Avaliacao, CorPadrao, TamanhoPadrao, TabelaMedidas, ProdutoCorFoto, NewsletterInscricao


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class ProdutoImagemInline(admin.TabularInline):
    model = ProdutoImagem
    extra = 1
    fields = ('thumb_preview', 'imagem', 'alt', 'principal', 'ordem')
    readonly_fields = ('thumb_preview',)
    ordering = ('-principal', 'ordem')
    verbose_name = 'Foto do produto'
    verbose_name_plural = 'Fotos do produto (marque "Principal" na foto de capa)'

    def thumb_preview(self, obj):
        if obj.imagem:
            return mark_safe(
                f'<img src="{obj.imagem.url}" style="height:70px;width:70px;'
                f'object-fit:cover;border-radius:6px;border:1px solid #eee;" />'
            )
        return '—'
    thumb_preview.short_description = 'Preview'


class VariacaoInline(admin.TabularInline):
    model = Variacao
    extra = 1
    fields = ('cor', 'cor_preview', 'tamanho', 'estoque', 'sku_variacao', 'bling_variacao_id', 'ativa', 'clonar_btn')
    readonly_fields = ('cor_preview', 'clonar_btn')
    ordering = ('cor__ordem', 'cor__nome', 'tamanho__ordem')
    autocomplete_fields = []
    verbose_name = 'Variação'
    verbose_name_plural = (
        'Variações — cada linha = 1 combinação (Cor + Tamanho). '
        'Cadastre as cores em Produtos → Cores padrão antes de usar.'
    )

    def cor_preview(self, obj):
        hex_val = obj.cor.codigo_hex if obj.cor_id and obj.cor.codigo_hex else ''
        if hex_val:
            return mark_safe(
                f'<span style="display:inline-block;width:22px;height:22px;'
                f'border-radius:50%;background:{hex_val};'
                f'border:1px solid #ccc;vertical-align:middle;" '
                f'title="{hex_val}"></span>'
            )
        return '—'
    cor_preview.short_description = '●'

    def clonar_btn(self, obj):
        if obj.pk:
            from django.urls import reverse
            url = reverse('admin:produtos_variacao_clonar', args=[obj.pk])
            return format_html(
                '<a href="{}" '
                'style="background:#c9a96e;color:#fff;padding:3px 10px;'
                'border-radius:3px;font-size:11px;text-decoration:none;white-space:nowrap;" '
                'title="Duplica esta variação para editar">Clonar</a>',
                url,
            )
        return '—'
    clonar_btn.short_description = 'Clonar'


class ProdutoCorFotoInline(admin.TabularInline):
    """
    Vincula uma foto já cadastrada do produto a uma cor específica.
    Ao clicar na bolinha da cor no site, a galeria troca para essa foto.
    Basta vincular UMA variação de cada cor — vale para todos os tamanhos.
    """
    model = ProdutoCorFoto
    extra = 0
    fields = ('cor', 'cor_preview', 'imagem', 'foto_preview')
    readonly_fields = ('cor_preview', 'foto_preview')
    verbose_name = 'Foto por cor'
    verbose_name_plural = (
        'Fotos por cor — ao clicar na bolinha, a galeria muda para essa foto. '
        'Cadastre UMA entrada por cor (vale para todos os tamanhos).'
    )

    def cor_preview(self, obj):
        if obj.cor_id and obj.cor.codigo_hex:
            hex1 = obj.cor.codigo_hex
            hex2 = obj.cor.codigo_hex_secundario
            if hex2:
                bg = f'conic-gradient({hex1} 0deg 180deg, {hex2} 180deg 360deg)'
            else:
                bg = hex1
            return mark_safe(
                f'<span style="display:inline-block;width:22px;height:22px;'
                f'border-radius:50%;background:{bg};'
                f'border:1px solid #ccc;vertical-align:middle;"></span>'
            )
        return '—'
    cor_preview.short_description = '●'

    def foto_preview(self, obj):
        if obj.imagem_id and obj.imagem.imagem:
            return mark_safe(
                f'<img src="{obj.imagem.imagem.url}" '
                f'style="height:55px;width:55px;object-fit:cover;border-radius:4px;border:1px solid #eee;" />'
            )
        return '—'
    foto_preview.short_description = 'Preview'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filtra o campo 'imagem' para mostrar apenas imagens do produto sendo editado."""
        if db_field.name == 'imagem':
            parent_id = request.resolver_match.kwargs.get('object_id')
            if parent_id:
                kwargs['queryset'] = ProdutoImagem.objects.filter(produto_id=parent_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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
# Categoria — visão em árvore (mãe → filhas indentadas)
# ---------------------------------------------------------------------------

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nome_arvore', 'nivel_badge', 'slug', 'ordem', 'ativa', 'total_produtos', 'thumb_preview')
    list_editable = ('ordem', 'ativa')
    list_filter = ('ativa', 'parent')
    search_fields = ('nome', 'slug')
    prepopulated_fields = {'slug': ('nome',)}
    ordering = ('parent__ordem', 'parent__nome', 'ordem', 'nome')

    fieldsets = (
        ('Identificação', {
            'fields': ('nome', 'slug', 'parent', 'ordem', 'ativa'),
            'description': (
                'Categoria mãe = deixe "Categoria mãe" vazio.<br>'
                'Subcategoria = selecione a "Categoria mãe" à qual pertence.<br>'
                'A ordem controla a posição no menu.'
            ),
        }),
        ('Conteúdo', {
            'fields': ('descricao', 'imagem'),
            'classes': ('collapse',),
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

    def thumb_preview(self, obj):
        if obj.imagem:
            return mark_safe(
                f'<img src="{obj.imagem.url}" style="height:36px;width:36px;'
                f'object-fit:cover;border-radius:4px;" />'
            )
        return '—'
    thumb_preview.short_description = 'Img'

    def total_produtos(self, obj):
        return obj.produtos.filter(ativo=True).count()
    total_produtos.short_description = 'Ativos'

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('parent')
        return qs

    def get_ordering(self, request):
        """Ordena: mães primeiro por ordem, depois as filhas logo abaixo da mãe."""
        return []  # ordenação feita no Python abaixo

    def changelist_view(self, request, extra_context=None):
        # Força ordenação: mãe (parent=None) por ordem, depois filhas logo abaixo
        response = super().changelist_view(request, extra_context)
        try:
            cl = response.context_data['cl']
            qs = cl.queryset.select_related('parent')
            # Separar mães e filhas
            maes = sorted([c for c in qs if c.parent_id is None], key=lambda x: (x.ordem, x.nome))
            filhas_map = {}
            for c in qs:
                if c.parent_id:
                    filhas_map.setdefault(c.parent_id, []).append(c)
            for pid in filhas_map:
                filhas_map[pid].sort(key=lambda x: (x.ordem, x.nome))
            # Monta lista final: mãe, suas filhas, próxima mãe, ...
            ordenadas = []
            for mae in maes:
                ordenadas.append(mae)
                ordenadas.extend(filhas_map.get(mae.pk, []))
            # Injeta as órfãs (filhas cujas mães não estão no qs — raro)
            ids_vistos = {c.pk for c in ordenadas}
            for c in qs:
                if c.pk not in ids_vistos:
                    ordenadas.append(c)
            # Substitui o queryset por lista ordenada (Django suporta lista aqui)
            cl.queryset = ordenadas
        except (AttributeError, KeyError, TypeError):
            pass
        return response


# ---------------------------------------------------------------------------
# Produto
# ---------------------------------------------------------------------------

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = (
        'thumb_principal', 'nome', 'categoria', 'preco_fmt', 'preco_promo_fmt',
        'badge_promocao', 'total_estoque', 'media_avaliacao', 'ativo', 'destaque', 'novo',
        'acoes_linha',
    )
    list_display_links = ('thumb_principal', 'nome')
    list_editable = ('ativo', 'destaque', 'novo')
    list_filter = ('ativo', 'destaque', 'novo', 'categoria', 'genero')
    search_fields = ('nome', 'slug', 'sku', 'bling_id')
    ordering = ('ordem', '-criado_em')
    date_hierarchy = 'criado_em'
    readonly_fields = ('criado_em', 'atualizado_em', 'slug')
    change_list_template = 'admin/produtos/produto_changelist.html'

    class Media:
        js = ('admin/js/admin_linhas.js',)

    fieldsets = (
        ('Identificação', {
            'fields': ('nome', 'slug', 'categoria', 'genero'),
        }),
        ('Integração Bling', {
            'fields': ('bling_id', 'sku'),
            'description': (
                'Bling ID e SKU são do produto pai. '
                'Cada variação tem seu próprio SKU e ID Bling no bloco de Variações abaixo.'
            ),
            'classes': ('collapse',),
        }),
        ('Textos', {
            'fields': ('descricao', 'composicao'),
        }),
        ('Preços', {
            'fields': ('preco', 'preco_promocional'),
            'description': 'Digite o valor com ponto como separador decimal. Ex: 512.00',
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

    inlines = [ProdutoImagemInline, ProdutoCorFotoInline, VariacaoInline, AvaliacaoInline]
    actions = ['marcar_ativo', 'marcar_inativo', 'marcar_destaque', 'remover_destaque']

    def get_urls(self):
        urls = super().get_urls()
        extras = [
            path('produtos/variacao/<int:pk>/clonar/',
                 self.admin_site.admin_view(self._clonar_variacao),
                 name='produtos_variacao_clonar'),
            path('importar/',
                 self.admin_site.admin_view(self._importar_view),
                 name='produtos_produto_importar'),
            path('modelo-csv/',
                 self.admin_site.admin_view(self._modelo_csv),
                 name='produtos_produto_modelo_csv'),
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

    def _parse_bling_descricao(self, descricao):
        """
        Faz parse de 'BODY GIU (AZUL MARINHO) (PP)' → (modelo, cor, tamanho).
        Retorna (None, None, None) se não reconhecer o padrão.
        """
        import re as _re
        m = _re.match(r'^(.+?)\s*\((.+?)\)\s*\((.+?)\)\s*$', descricao.strip())
        if m:
            return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        # Só um parêntese — tenta (MODELO) (TAMANHO_ou_COR)
        m2 = _re.match(r'^(.+?)\s*\((.+?)\)\s*$', descricao.strip())
        if m2:
            return m2.group(1).strip(), '', m2.group(2).strip()
        return descricao.strip(), '', ''

    def _ler_arquivo(self, arquivo):
        """
        Lê o arquivo enviado (CSV ou XLSX) e retorna lista de dicts.
        Detecta automaticamente o formato Bling (colunas ID/Código/Descrição)
        ou o formato legado (nome/categoria/...).
        """
        nome = arquivo.name.lower()

        if nome.endswith('.xlsx') or nome.endswith('.xls'):
            import openpyxl
            wb = openpyxl.load_workbook(arquivo, data_only=True)
            ws = wb.active
            rows = list(ws.values)
            if not rows:
                return [], 'bling'
            headers = [str(h).strip() if h else '' for h in rows[0]]
            data = []
            for row in rows[1:]:
                data.append({headers[i]: (str(row[i]).strip() if row[i] is not None else '') for i in range(len(headers))})
        else:
            decoded = arquivo.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(decoded))
            data = list(reader)
            if data:
                headers = list(data[0].keys())
            else:
                return [], 'bling'

        # Detecta formato: Bling tem colunas "ID", "Código", "Descrição"
        headers_norm = [h.lower().strip() for h in (headers if data else [])]
        is_bling = any(h in headers_norm for h in ['id', 'código', 'codigo', 'descrição', 'descricao'])
        formato = 'bling' if is_bling else 'legado'
        return data, formato

    def _modelo_csv(self, request):
        """Baixa um arquivo CSV modelo (formato legado) para preenchimento."""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="modelo_importacao_produtos.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'nome', 'categoria', 'descricao', 'composicao', 'genero',
            'preco', 'preco_promocional', 'ativo', 'destaque', 'novo',
            'bling_id', 'sku',
            'var_cor', 'var_tamanho', 'var_estoque', 'var_sku', 'var_bling_id',
        ])
        writer.writerow([
            'Body Adriana', 'Body', 'Descrição do produto', 'Poliéster 95% Elastano 5%', 'F',
            '299.90', '', 'sim', 'não', 'sim', '9876', '100',
            'Preto', 'P', '5', '100', '9876',
        ])
        writer.writerow([
            '', '', '', '', '', '', '', '', '', '', '', '',
            'Preto', 'M', '3', '101', '9877',
        ])
        return response

    def _importar_bling(self, rows, categoria_padrao):
        """
        Processa linhas do CSV/XLSX exportado pelo Bling.
        Colunas: ID, Código, Descrição (MODELO (COR) (TAMANHO)), Preço, Situação
        Agrupa por modelo → cria Produto + Variações.
        """
        criados = 0
        variacoes_criadas = 0
        erros = []

        # Normaliza nomes de colunas
        def get(row, *keys):
            for k in keys:
                for rk in row:
                    if rk and rk.lower().strip() == k.lower():
                        return row[rk].strip() if row[rk] else ''
            return ''

        # Agrupa por modelo
        from collections import OrderedDict
        produtos_map = OrderedDict()

        for i, row in enumerate(rows, start=2):
            descricao_raw = get(row, 'Descrição', 'Descricao', 'descrição', 'descricao', 'description')
            if not descricao_raw:
                continue

            modelo, cor_nome, tam_nome = self._parse_bling_descricao(descricao_raw)
            if not modelo:
                erros.append(f'Linha {i}: não foi possível extrair modelo da descrição "{descricao_raw}"')
                continue

            preco_raw = get(row, 'Preço', 'Preco', 'preço', 'preco', 'price')
            try:
                preco = float(preco_raw.replace(',', '.')) if preco_raw else 0
            except ValueError:
                preco = 0

            situacao = get(row, 'Situação', 'Situacao', 'situação', 'situacao', 'status').lower()
            ativo = situacao in ('ativo', 'ativa', 'active', 'a', '', '1')

            bling_id  = get(row, 'ID', 'id')
            sku_var   = get(row, 'Código', 'Codigo', 'código', 'codigo', 'code', 'sku')

            key = modelo.upper()
            if key not in produtos_map:
                produtos_map[key] = {
                    'nome': modelo,
                    'preco': preco,
                    'ativo': ativo,
                    'variacoes': [],
                }
            if preco > produtos_map[key]['preco']:
                produtos_map[key]['preco'] = preco

            produtos_map[key]['variacoes'].append({
                'cor_nome': cor_nome,
                'tam_nome': tam_nome,
                'bling_id': bling_id,
                'sku_var':  sku_var,
                'ativo':    ativo,
                'linha':    i,
            })

        # Cria produtos e variações
        for key, info in produtos_map.items():
            try:
                produto, criado = Produto.objects.update_or_create(
                    nome=info['nome'],
                    defaults={
                        'categoria':    categoria_padrao,
                        'descricao':    info['nome'],
                        'preco':        info['preco'] or 1,
                        'ativo':        info['ativo'],
                    },
                )
                if criado:
                    criados += 1
            except Exception as e:
                erros.append(f'Produto "{info["nome"]}": {e}')
                continue

            for var in info['variacoes']:
                try:
                    cor_obj = None
                    if var['cor_nome']:
                        hex_val = self._hex_da_cor(var['cor_nome'])
                        cor_obj, _ = CorPadrao.objects.get_or_create(
                            nome__iexact=var['cor_nome'],
                            defaults={'nome': var['cor_nome'].title(), 'codigo_hex': hex_val},
                        )
                        if not cor_obj.codigo_hex and hex_val:
                            cor_obj.codigo_hex = hex_val
                            cor_obj.save(update_fields=['codigo_hex'])

                    tam_obj = None
                    if var['tam_nome']:
                        tam_obj, _ = TamanhoPadrao.objects.get_or_create(
                            nome__iexact=var['tam_nome'],
                            defaults={'nome': var['tam_nome'].upper()},
                        )

                    Variacao.objects.update_or_create(
                        produto=produto,
                        cor=cor_obj,
                        tamanho=tam_obj,
                        defaults={
                            'sku_variacao':     var['sku_var'],
                            'bling_variacao_id': var['bling_id'],
                            'ativa':            var['ativo'],
                        },
                    )
                    variacoes_criadas += 1
                except Exception as e:
                    erros.append(f'Linha {var["linha"]} ({info["nome"]} / {var["cor_nome"]} / {var["tam_nome"]}): {e}')

        return criados, variacoes_criadas, erros

    def _importar_legado(self, rows):
        """Processa o CSV no formato legado (colunas nome/categoria/var_cor/...)."""
        criados = 0
        variacoes_criadas = 0
        erros = []
        produto_atual = None

        for i, row in enumerate(rows, start=2):
            nome = row.get('nome', '').strip()
            try:
                if nome:
                    cat_nome = row.get('categoria', '').strip()
                    categoria, _ = Categoria.objects.get_or_create(
                        nome__iexact=cat_nome or 'Geral',
                        defaults={'nome': cat_nome or 'Geral', 'ativa': True, 'ordem': 99},
                    )
                    preco_raw = row.get('preco', '0').strip().replace(',', '.')
                    preco = float(preco_raw) if preco_raw else 0
                    promo_raw = row.get('preco_promocional', '').strip().replace(',', '.')
                    promo = float(promo_raw) if promo_raw else None

                    produto_atual, criado = Produto.objects.update_or_create(
                        nome=nome,
                        defaults={
                            'categoria':       categoria,
                            'descricao':       row.get('descricao', '').strip() or nome,
                            'composicao':      row.get('composicao', '').strip(),
                            'genero':          'F' if row.get('genero', 'F').strip().upper() != 'U' else 'U',
                            'preco':           preco,
                            'preco_promocional': promo,
                            'ativo':           row.get('ativo', 'sim').strip().lower() in ('sim','s','yes','1','true'),
                            'destaque':        row.get('destaque', 'não').strip().lower() in ('sim','s','yes','1','true'),
                            'novo':            row.get('novo', 'sim').strip().lower() in ('sim','s','yes','1','true'),
                            'bling_id':        row.get('bling_id', '').strip(),
                            'sku':             row.get('sku', '').strip(),
                        },
                    )
                    if criado:
                        criados += 1

                var_cor_nome = row.get('var_cor', '').strip()
                var_tam_nome = row.get('var_tamanho', '').strip()

                if produto_atual and (var_cor_nome or var_tam_nome):
                    cor_obj = None
                    if var_cor_nome:
                        hex_val = row.get('var_hex', '').strip() or self._hex_da_cor(var_cor_nome)
                        cor_obj, _ = CorPadrao.objects.get_or_create(
                            nome__iexact=var_cor_nome,
                            defaults={'nome': var_cor_nome.title(), 'codigo_hex': hex_val},
                        )
                    tam_obj = None
                    if var_tam_nome:
                        tam_obj, _ = TamanhoPadrao.objects.get_or_create(
                            nome__iexact=var_tam_nome,
                            defaults={'nome': var_tam_nome.upper()},
                        )
                    var_est_raw = row.get('var_estoque', '0').strip()
                    Variacao.objects.update_or_create(
                        produto=produto_atual,
                        cor=cor_obj,
                        tamanho=tam_obj,
                        defaults={
                            'estoque':          int(var_est_raw) if var_est_raw.isdigit() else 0,
                            'sku_variacao':     row.get('var_sku', '').strip(),
                            'bling_variacao_id': row.get('var_bling_id', '').strip(),
                            'ativa':            True,
                        },
                    )
                    variacoes_criadas += 1

            except Exception as e:
                erros.append(f'Linha {i}: {e}')

        return criados, variacoes_criadas, erros

    def _importar_view(self, request):
        """View de importação de produtos via CSV ou XLSX (formato Bling ou legado)."""
        context = {
            'title': 'Importar produtos',
            'opts': self.model._meta,
            'has_view_permission': True,
        }

        if request.method == 'POST' and request.FILES.get('arquivo_csv'):
            arquivo = request.FILES['arquivo_csv']
            categoria_nome = request.POST.get('categoria', '').strip()

            try:
                rows, formato = self._ler_arquivo(arquivo)

                if formato == 'bling':
                    # Categoria padrão para importação Bling
                    if categoria_nome:
                        categoria_padrao, _ = Categoria.objects.get_or_create(
                            nome__iexact=categoria_nome,
                            defaults={'nome': categoria_nome, 'ativa': True, 'ordem': 99},
                        )
                    else:
                        categoria_padrao, _ = Categoria.objects.get_or_create(
                            nome='Importado',
                            defaults={'ativa': True, 'ordem': 99},
                        )
                    criados, variacoes_criadas, erros = self._importar_bling(rows, categoria_padrao)
                else:
                    criados, variacoes_criadas, erros = self._importar_legado(rows)

                msg = (
                    f'{criados} produto(s) criado(s) / atualizado(s) e '
                    f'{variacoes_criadas} variação(ões) importada(s).'
                )
                if erros:
                    msg += ' Erros: ' + ' | '.join(erros[:5])
                    if len(erros) > 5:
                        msg += f' (+ {len(erros)-5} outros)'
                self.message_user(
                    request, msg,
                    django_messages.SUCCESS if not erros else django_messages.WARNING,
                )
                return HttpResponseRedirect('/painel/produtos/produto/')

            except Exception as e:
                self.message_user(request, f'Erro ao processar arquivo: {e}', django_messages.ERROR)

        context['categorias'] = Categoria.objects.filter(ativa=True, parent__isnull=True).order_by('ordem', 'nome')
        return render(request, 'admin/produtos/importar.html', context)

    def _clonar_variacao(self, request, pk):
        var = get_object_or_404(Variacao, pk=pk)
        nova = Variacao(
            produto=var.produto,
            cor=var.cor,
            tamanho=var.tamanho,
            estoque=0,
            sku_variacao='',
            bling_variacao_id='',
            ativa=False,
        )
        nova.save()
        self.message_user(
            request,
            f'Variação clonada com sucesso! Edite os campos da nova linha e ative quando estiver pronto.',
            django_messages.SUCCESS,
        )
        return HttpResponseRedirect(
            f'/painel/produtos/produto/{var.produto_id}/change/#variacoes'
        )

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:produtos_produto_change', args=[obj.pk])
        delete_url = reverse('admin:produtos_produto_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir este produto?\')">✕</a>',
            edit_url, delete_url,
        )
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


# ---------------------------------------------------------------------------
# Cor e Tamanho padrão
# ---------------------------------------------------------------------------

@admin.register(CorPadrao)
class CorPadraoAdmin(admin.ModelAdmin):
    list_display = ('cor_bolinha', 'nome', 'codigo_hex', 'ordem')
    list_editable = ('ordem',)
    search_fields = ('nome',)
    ordering = ('ordem', 'nome')

    def cor_bolinha(self, obj):
        if obj.codigo_hex:
            return mark_safe(
                f'<span style="display:inline-block;width:24px;height:24px;'
                f'border-radius:50%;background:{obj.codigo_hex};'
                f'border:1px solid #ccc;vertical-align:middle;"></span>'
            )
        return '—'
    cor_bolinha.short_description = '●'


@admin.register(TamanhoPadrao)
class TamanhoPadraoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ordem')
    list_editable = ('ordem',)
    search_fields = ('nome',)
    ordering = ('ordem', 'nome')


# ---------------------------------------------------------------------------
# Tabela de medidas
# ---------------------------------------------------------------------------

@admin.register(TabelaMedidas)
class TabelaMedidasAdmin(admin.ModelAdmin):
    list_display = ('nome', 'categoria', 'ativo')
    list_editable = ('ativo',)
    list_filter = ('ativo', 'categoria')
    ordering = ('categoria', 'nome')

    fieldsets = (
        (None, {
            'fields': ('nome', 'categoria', 'ativo'),
            'description': (
                'Crie uma tabela geral (categoria em branco) como padrão, '
                'e tabelas específicas por categoria quando necessário.'
            ),
        }),
        ('Conteúdo da tabela', {
            'fields': ('conteudo',),
            'description': (
                'Descreva as medidas. Pode usar texto simples ou HTML básico. '
                'Exemplo:<br>'
                '<strong>PP</strong> — Busto: 82cm | Cintura: 62cm | Quadril: 88cm<br>'
                '<strong>P</strong> — Busto: 86cm | Cintura: 66cm | Quadril: 92cm'
            ),
        }),
    )


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


@admin.register(NewsletterInscricao)
class NewsletterInscricaoAdmin(admin.ModelAdmin):
    list_display  = ('email', 'inscrito_em', 'ativo')
    list_filter   = ('ativo',)
    search_fields = ('email',)
    readonly_fields = ('email', 'inscrito_em')
    ordering = ('-inscrito_em',)
