from django import forms
from django.utils.safestring import mark_safe

from .models import Avaliacao, Categoria, Produto, ProdutoCorFoto, ProdutoImagem, Variacao


class VariacaoInlineForm(forms.ModelForm):
    """Bloqueia visualmente o campo `estoque` quando a variação tem
    `usa_sync_bling=True` — o estoque passa a ser fonte do Bling. O JS
    `variacao_sync_lock.js` libera o campo dinamicamente se o usuário
    desmarcar o checkbox (sem precisar salvar antes)."""

    class Meta:
        model = Variacao
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)
        if instance and instance.pk and instance.usa_sync_bling:
            campo = self.fields.get('estoque')
            if campo is not None:
                campo.widget.attrs['readonly'] = 'readonly'
                campo.widget.attrs['style'] = 'background:#f5f5f5;cursor:not-allowed;'
                campo.widget.attrs['title'] = '🔒 Sincronizado pelo Bling'

    def clean(self):
        cleaned = super().clean()
        instance = self.instance
        sync_atual_no_post = cleaned.get('usa_sync_bling')
        sync_no_banco = bool(instance and instance.pk and instance.usa_sync_bling)
        if sync_no_banco and sync_atual_no_post:
            # Field may be absent from POST (disabled JS widget doesn't submit).
            # Clear any resulting validation error and restore the DB value.
            self.errors.pop('estoque', None)
            cleaned['estoque'] = instance.estoque
        return cleaned


PENDING_PREFIX = 'pending:'


class StarRatingWidget(forms.Widget):
    def __init__(self, attrs=None):
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        input_id = attrs.get('id', f'id_{name}')
        current = ''
        try:
            current = int(value) if value not in (None, '') else ''
        except (TypeError, ValueError):
            current = ''

        stars = []
        for nota in range(1, 6):
            active = ' is-active' if current and nota <= current else ''
            stars.append(
                f'<button type="button" class="star-rating__star{active}" '
                f'data-value="{nota}" aria-label="{nota} estrela{"s" if nota > 1 else ""}">★</button>'
            )

        html = (
            f'<div class="star-rating js-star-rating" data-current="{current or ""}">'
            f'<input type="hidden" name="{name}" id="{input_id}" value="{current or ""}" class="star-rating__control">'
            f'<div class="star-rating__stars">{"".join(stars)}</div>'
            '</div>'
        )
        return mark_safe(html)


class CategoriaSubSelect(forms.Select):
    """Dropdown de subcategoria com `data-parent` em cada <option> — permite que o
    JS no admin filtre dinamicamente pelas subcategorias do pai selecionado."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent_map = None

    def _get_parent_map(self):
        if self._parent_map is None:
            self._parent_map = dict(Categoria.objects.values_list('id', 'parent_id'))
        return self._parent_map

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        # Em ChoiceFields normais `value` é string/int. No admin (ModelChoiceField via
        # ModelChoiceIterator) `value` é um `ModelChoiceIteratorValue` — int(value) falha,
        # mas str(value) retorna o ID corretamente em ambos os casos.
        try:
            value_int = int(str(value)) if value not in (None, '') else None
        except (ValueError, TypeError):
            return option
        if value_int is None:
            return option
        pid = self._get_parent_map().get(value_int)
        option['attrs']['data-parent'] = str(pid) if pid else ''
        return option


class ProdutoAdminForm(forms.ModelForm):
    """Form do admin de Produto que separa Categoria pai + Subcategoria.

    O campo `categoria` do model continua sendo a subcategoria salva. O `categoria_pai`
    é virtual (não vai pro banco) — só serve para o JS filtrar a lista de subcategorias.
    """
    categoria_pai = forms.ModelChoiceField(
        queryset=Categoria.objects.filter(parent__isnull=True, ativa=True).order_by('ordem', 'nome'),
        required=True,
        label='Categoria pai',
        empty_label='---------',
    )

    class Meta:
        model = Produto
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apenas relabel — queryset e widget custom são aplicados em
        # ProdutoAdmin.formfield_for_foreignkey (forma idiomática Django admin).
        cat_field = self.fields.get('categoria')
        if cat_field is not None:
            cat_field.label = 'Subcategoria'

        descricao_field = self.fields.get('descricao')
        if descricao_field is not None:
            descricao_field.help_text = (
                'Use a barra para formatar a descrição com negrito, alinhamento, '
                'tamanho de fonte, listas e recuos.'
            )
            descricao_field.widget.attrs.update({'rows': 10})

        composicao_field = self.fields.get('composicao')
        if composicao_field is not None:
            composicao_field.help_text = (
                'Monte a composição do jeito que preferir: em linha, quebrada por tecido '
                'ou com destaques de tamanho e alinhamento.'
            )
            composicao_field.widget.attrs.update({'rows': 8})

        # Pré-seleciona o pai a partir da subcategoria já vinculada (em edição)
        if self.instance and self.instance.pk and self.instance.categoria_id:
            cat = self.instance.categoria
            if cat.parent_id:
                self.fields['categoria_pai'].initial = cat.parent_id
            else:
                # Caso raro: produto vinculado direto à categoria pai (legado)
                self.fields['categoria_pai'].initial = cat.pk

    def clean(self):
        cleaned = super().clean()
        pai = cleaned.get('categoria_pai')
        sub = cleaned.get('categoria')

        if not pai:
            self.add_error('categoria_pai', 'Selecione a categoria pai.')
            return cleaned

        if not sub:
            self.add_error('categoria', 'Selecione a subcategoria.')
            return cleaned

        # Coerência: a subcategoria precisa ser filha do pai escolhido
        if sub.parent_id and sub.parent_id != pai.pk:
            self.add_error('categoria', f'A subcategoria "{sub.nome}" não pertence a "{pai.nome}".')

        return cleaned


class _PendingImagemField(forms.ModelChoiceField):
    """Aceita valores 'pending:imagens-N' (foto subida no inline de imagens mas
    ainda não persistida) sem falhar a validação. A resolução para o objeto
    ProdutoImagem real acontece em ProdutoAdmin.save_related, depois do save
    do formset de imagens."""

    def to_python(self, value):
        if isinstance(value, str) and value.startswith(PENDING_PREFIX):
            return None
        return super().to_python(value)

    def validate(self, value):
        if value is None and getattr(self, '_pending_ref', None):
            return
        super().validate(value)

    def clean(self, value):
        self._pending_ref = None
        if isinstance(value, str) and value.startswith(PENDING_PREFIX):
            self._pending_ref = value
            return None
        return super().clean(value)


class ProdutoCorFotoForm(forms.ModelForm):
    """Form do inline Foto por Cor que aceita refs pending para fotos novas."""

    class Meta:
        model = ProdutoCorFoto
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original = self.fields.get('imagem')
        if original is not None:
            self.fields['imagem'] = _PendingImagemField(
                queryset=original.queryset,
                required=original.required,
                widget=original.widget,
                empty_label=getattr(original, 'empty_label', '---------'),
                label=original.label,
                help_text=original.help_text,
            )

    def clean(self):
        cleaned = super().clean()
        imagem_field = self.fields.get('imagem')
        ref = getattr(imagem_field, '_pending_ref', None) if imagem_field else None
        if ref:
            self._pending_imagem_ref = ref
            cleaned['imagem'] = None
            self.instance.imagem = None
        return cleaned


class AvaliacaoCompraForm(forms.ModelForm):
    nota_experiencia = forms.IntegerField(
        label='Experiência da compra',
        min_value=1,
        max_value=5,
        widget=StarRatingWidget,
        error_messages={'required': 'Escolha de 1 a 5 estrelas para a experiência da compra.'},
    )
    nota_produtos = forms.IntegerField(
        label='Produtos comprados',
        min_value=1,
        max_value=5,
        widget=StarRatingWidget,
        error_messages={'required': 'Escolha de 1 a 5 estrelas para os produtos comprados.'},
    )
    comentario = forms.CharField(
        label='Comentário (opcional)',
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'rows': 5,
            'maxlength': 500,
            'placeholder': 'Se quiser, conte como foi sua experiência. Esse comentário pode aparecer no site após aprovação.',
        }),
    )

    class Meta:
        model = Avaliacao
        fields = ('nota_experiencia', 'nota_produtos', 'comentario')

    def clean_comentario(self):
        return (self.cleaned_data.get('comentario') or '').strip()
