import os
from django.db import models
from django.utils.text import slugify
from django.urls import reverse
from django.core.exceptions import ValidationError
from apps.core_utils.sanitize import sanitize_text, sanitize_rich_html, validate_image_upload


def produto_imagem_path(instance, filename):
    """Salva imagens em subpastas por produto para evitar diretório flat gigante."""
    base, ext = os.path.splitext(os.path.basename(filename or 'imagem'))
    base = slugify(base) or 'imagem'
    nome = f'{base}{ext.lower()}'
    return f'produtos/{instance.produto.slug if hasattr(instance, "produto") else "temp"}/{nome}'


class Categoria(models.Model):
    nome = models.CharField('Nome', max_length=80)
    slug = models.SlugField('Slug', max_length=80, blank=True)
    parent = models.ForeignKey(
        'self', verbose_name='Categoria mãe', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='subcategorias',
    )
    ordem = models.PositiveSmallIntegerField('Ordem no menu', default=0)
    ativa = models.BooleanField('Ativa', default=True)

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ['ordem', 'nome']
        constraints = [
            models.UniqueConstraint(
                fields=['parent', 'nome'],
                condition=models.Q(parent__isnull=False),
                name='uniq_categoria_nome_por_parent',
            ),
            models.UniqueConstraint(
                fields=['parent', 'slug'],
                condition=models.Q(parent__isnull=False),
                name='uniq_categoria_slug_por_parent',
            ),
            models.UniqueConstraint(
                fields=['nome'],
                condition=models.Q(parent__isnull=True),
                name='uniq_categoria_mae_nome',
            ),
            models.UniqueConstraint(
                fields=['slug'],
                condition=models.Q(parent__isnull=True),
                name='uniq_categoria_mae_slug',
            ),
        ]

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        if self.parent_id:
            return reverse(
                'produtos:loja_subcategoria',
                kwargs={'parent_slug': self.parent.slug, 'categoria_slug': self.slug},
            )
        return reverse('produtos:loja_categoria', kwargs={'categoria_slug': self.slug})

    def clean(self):
        self.nome = sanitize_text(self.nome, max_length=80)
        if self.slug:
            self.slug = slugify(self.slug)
        else:
            self.slug = slugify(self.nome)

        conflitos = Categoria.objects.exclude(pk=self.pk).filter(parent=self.parent)
        if conflitos.filter(nome__iexact=self.nome).exists():
            raise ValidationError({'nome': 'Ja existe uma categoria com este nome neste mesmo nivel.'})
        if conflitos.filter(slug=self.slug).exists():
            raise ValidationError({'slug': 'Ja existe uma categoria com este slug nesta mesma categoria mae.'})

    def save(self, *args, **kwargs):
        self.full_clean()

        # Detecta se a flag `ativa` mudou em uma categoria PAI (sem parent),
        # para propagar a mudança para todas as subcategorias após salvar.
        propagar_ativa_para_subs = False
        if self.pk and self.parent_id is None:
            try:
                estado_db = Categoria.objects.only('ativa').get(pk=self.pk)
                if estado_db.ativa != self.ativa:
                    propagar_ativa_para_subs = True
            except Categoria.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        if propagar_ativa_para_subs:
            Categoria.objects.filter(parent_id=self.pk).update(ativa=self.ativa)


class Produto(models.Model):

    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='produtos')
    cor_principal = models.ForeignKey(
        'CorPadrao',
        verbose_name='Cor principal',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='produtos_capa',
        help_text='Define qual cor abre a vitrine pública e fornece a foto de capa do produto.',
    )
    nome = models.CharField('Nome', max_length=200)
    slug = models.SlugField('Slug', max_length=220, unique=True, blank=True)
    descricao = models.TextField('Descrição', max_length=5000)
    composicao = models.TextField('Composição/Material', max_length=5000, blank=True)

    # Preços
    preco = models.DecimalField('Preço', max_digits=10, decimal_places=2)
    preco_promocional = models.DecimalField('Preço promocional', max_digits=10,
                                             decimal_places=2, null=True, blank=True)

    # Logística
    peso = models.PositiveSmallIntegerField(
        'Peso (g)', default=500,
        help_text='Peso da peça em gramas — usado no cálculo de frete (ex: 200, 300, 500)',
    )

    # Controle
    ativo = models.BooleanField('Ativo', default=True)
    destaque = models.BooleanField('Destaque na home', default=False)
    novo = models.BooleanField('Novo', default=True)
    ordem = models.PositiveIntegerField('Ordem', default=0)

    # Integração Bling (produto pai — SKU e ID do produto mãe no Bling)
    bling_id = models.CharField('ID Bling (produto pai)', max_length=50, blank=True, db_index=True,
                help_text='ID do produto pai no Bling. Cada variação tem seu próprio SKU e ID.')
    sku = models.CharField('SKU base', max_length=80, blank=True, db_index=True,
                help_text='SKU base/referência. O SKU individual fica em cada variação.')

    # SEO
    seo_titulo = models.CharField('Título SEO', max_length=70, blank=True,
                    help_text='Título para Google (máx. 70 caracteres). '
                              'Se vazio, usa o nome do produto.')
    seo_descricao = models.TextField('Descrição SEO', max_length=160, blank=True,
                    help_text='Descrição para Google (máx. 160 caracteres). '
                              'Se vazia, usa o início da descrição do produto.')
    seo_keywords = models.CharField('Palavras-chave', max_length=200, blank=True,
                    help_text='Separadas por vírgula. Ex: body preto, lingerie premium.')

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['ordem', '-criado_em']

    def __str__(self):
        return self.nome

    @property
    def variacao_referencia_preco(self):
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'variacoes' in cache:
            fonte = cache['variacoes']
        else:
            fonte = self.variacoes.all()
        variacoes = [v for v in fonte if v.ativa and v.preco_atual is not None]
        if not variacoes:
            return None
        return min(variacoes, key=lambda v: v.preco_atual)

    @property
    def preco_base_exibicao(self):
        variacao = self.variacao_referencia_preco
        if variacao:
            return variacao.preco_base
        return self.preco

    @property
    def preco_promocional_exibicao(self):
        variacao = self.variacao_referencia_preco
        if variacao:
            return variacao.preco_promocional_efetivo
        return self.preco_promocional

    @property
    def preco_atual(self):
        return self.preco_promocional_exibicao if self.preco_promocional_exibicao else self.preco_base_exibicao

    @property
    def em_promocao(self):
        preco_promo = self.preco_promocional_exibicao
        preco_base = self.preco_base_exibicao
        return bool(preco_promo and preco_base and preco_promo < preco_base)

    @property
    def percentual_desconto(self):
        if self.em_promocao:
            return int((1 - self.preco_promocional_exibicao / self.preco_base_exibicao) * 100)
        return 0

    @property
    def parcelamento_texto(self):
        """Retorna texto de parcelamento: 'ou 5x de R$ 200,00 sem juros'
        Regras: máx 5x, parcela mínima R$ 150,00."""
        from decimal import Decimal
        PARCELA_MINIMA = Decimal('150.00')
        preco = self.preco_atual
        if preco < PARCELA_MINIMA * 2:
            return ''
        for n in range(5, 1, -1):
            parcela = preco / n
            if parcela >= PARCELA_MINIMA:
                parcela_fmt = f'{parcela:.2f}'.replace('.', ',')
                return f'ou {n}x de R$ {parcela_fmt} sem juros'
        return ''

    def _imagens_cache(self):
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'imagens' in cache:
            return list(cache['imagens'])
        return list(self.imagens.select_related('cor').all())

    def _variacoes_cache(self):
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'variacoes' in cache:
            return list(cache['variacoes'])
        return list(self.variacoes.select_related('cor').all())

    def imagens_da_cor(self, cor_id=None):
        imagens = self._imagens_cache()
        if cor_id is None:
            filtradas = [img for img in imagens if img.cor_id is None]
            return sorted(filtradas, key=lambda img: (img.ordem, img.pk or 0))
        filtradas = [img for img in imagens if img.cor_id == cor_id]
        return sorted(filtradas, key=lambda img: (img.ordem, img.pk or 0))

    @property
    def cor_capa_efetiva_id(self):
        cores_disponiveis = {
            v.cor_id for v in self._variacoes_cache()
            if v.cor_id and v.disponivel
        }

        # 1. cor_principal com imagens e com variações disponíveis
        if (self.cor_principal_id
                and self.imagens_da_cor(self.cor_principal_id)
                and (self.cor_principal_id in cores_disponiveis or not cores_disponiveis)):
            return self.cor_principal_id

        # 2. Primeira cor com imagens e variações disponíveis
        for img in self._imagens_cache():
            if img.cor_id and img.cor_id in cores_disponiveis:
                return img.cor_id

        # 3. Fallback: cor_principal com imagens (produto totalmente sem estoque)
        if self.cor_principal_id and self.imagens_da_cor(self.cor_principal_id):
            return self.cor_principal_id

        # 4. Fallback: qualquer imagem com cor
        for img in self._imagens_cache():
            if img.cor_id:
                return img.cor_id

        # 5. Fallback: primeira variação ativa
        vistas = set()
        for variacao in self._variacoes_cache():
            if variacao.ativa and variacao.cor_id and variacao.cor_id not in vistas:
                vistas.add(variacao.cor_id)
                return variacao.cor_id
        return None

    @property
    def imagem_principal(self):
        cor_id = self.cor_capa_efetiva_id
        imagens_cor = self.imagens_da_cor(cor_id) if cor_id else []
        if imagens_cor:
            return imagens_cor[0]
        return self.imagens.filter(principal=True).first() or self.imagens.order_by('ordem', 'id').first()

    @property
    def imagem_hover(self):
        cor_id = self.cor_capa_efetiva_id
        imagens_cor = self.imagens_da_cor(cor_id) if cor_id else []
        if len(imagens_cor) > 1:
            return imagens_cor[1]
        if imagens_cor:
            return imagens_cor[0]
        return None

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('produtos:detalhe', kwargs={'slug': self.slug})

    def clean(self):
        self.nome = sanitize_text(self.nome, max_length=200).upper()
        erros = {}
        try:
            self.descricao = sanitize_rich_html(self.descricao, max_length=5000)
        except ValidationError as exc:
            erros['descricao'] = exc.messages
        try:
            self.composicao = sanitize_rich_html(self.composicao, max_length=5000)
        except ValidationError as exc:
            erros['composicao'] = exc.messages
        if erros:
            raise ValidationError(erros)
        # Trata 0 ou valores negativos como "sem promoção" (converte para NULL)
        if self.preco_promocional is not None and self.preco_promocional <= 0:
            self.preco_promocional = None
        # Valida que o preço promocional é menor que o preço original
        if self.preco_promocional is not None and self.preco_promocional >= self.preco:
            raise ValidationError({
                'preco_promocional': 'Preço promocional deve ser menor que o preço original. '
                                     'Deixe em branco se não há promoção.'
            })

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nome)
            slug = base
            n = 1
            while Produto.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        self.full_clean()
        super().save(*args, **kwargs)


class ProdutoImagem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='imagens')
    imagem = models.ImageField('Imagem', upload_to=produto_imagem_path)
    cor = models.ForeignKey(
        'CorPadrao',
        verbose_name='Cor do produto',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='imagens_produto',
        help_text='Cada foto pertence a uma cor. A primeira foto da cor vira a principal daquela cor.',
    )
    alt = models.CharField('Texto alternativo', max_length=200, blank=True)
    principal = models.BooleanField('Principal', default=False)
    ordem = models.PositiveSmallIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Imagem do produto'
        verbose_name_plural = 'Imagens do produto'
        ordering = ['ordem', 'id']

    def __str__(self):
        arquivo = os.path.basename(self.imagem.name) if self.imagem else ''
        marcador = ' (principal)' if self.principal else ''
        return f'{arquivo or "imagem"}{marcador}'

    def clean(self):
        if self.imagem and hasattr(self.imagem, 'file'):
            validate_image_upload(self.imagem)
        self.alt = sanitize_text(self.alt, max_length=200)

    def save(self, *args, **kwargs):
        is_new_file = bool(self.imagem and hasattr(self.imagem, 'file'))
        # Garante só uma imagem principal por produto
        if self.principal:
            ProdutoImagem.objects.filter(
                produto=self.produto, principal=True
            ).exclude(pk=self.pk).update(principal=False)
        super().save(*args, **kwargs)
        if is_new_file:
            self._normalizar_imagem()

    def _normalizar_imagem(self, max_w=1200, max_h=1600):
        """Redimensiona e converte para WebP (formato padrao do projeto)."""
        try:
            from PIL import Image as PilImage
            path = self.imagem.path
            already_webp = path.lower().endswith('.webp')
            with PilImage.open(path) as img:
                w, h = img.size
                ratio = min(max_w / w, max_h / h)
                needs_resize = ratio < 0.98

                if not needs_resize and already_webp:
                    return

                if needs_resize:
                    new_w, new_h = round(w * ratio), round(h * ratio)
                    # Para imagens muito grandes (>3x o alvo), pre-reduz com BOX
                    # antes do LANCZOS final -- muito mais rapido sem perda visual.
                    if ratio < 0.35:
                        interim = img.reduce(max(1, int(1 / ratio / 2)))
                        out = interim.resize((new_w, new_h), PilImage.LANCZOS)
                    else:
                        out = img.resize((new_w, new_h), PilImage.LANCZOS)
                else:
                    out = img.copy()

                if out.mode not in ('RGB', 'RGBA'):
                    out = out.convert('RGB')

                base = os.path.splitext(path)[0]
                webp_path = base + '.webp'
                # Salva em arquivo temporario primeiro: se o processo morrer
                # durante o save, o arquivo original permanece intacto.
                tmp_path = webp_path + '.tmp'
                out.save(tmp_path, format='WEBP', quality=88, method=1)
                os.replace(tmp_path, webp_path)

            if not already_webp:
                os.remove(path)
                new_name = os.path.splitext(self.imagem.name)[0] + '.webp'
                ProdutoImagem.objects.filter(pk=self.pk).update(imagem=new_name)
        except Exception:
            # Limpa arquivo temporario se ficou para tras
            try:
                tmp = os.path.splitext(self.imagem.path)[0] + '.webp.tmp'
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass


class CorPadrao(models.Model):
    """Lista-mestre de cores usadas nas variações de produto."""
    nome                  = models.CharField('Nome da cor', max_length=50, unique=True,
                                help_text='Ex: Preto, Branco, Rosa Chá')
    codigo_hex            = models.CharField('Código hex', max_length=7, blank=True,
                                help_text='Ex: #000000 — cor principal (ou única) da bolinha.')
    codigo_hex_secundario = models.CharField(
        'Código hex secundário', max_length=7, blank=True,
        help_text='Opcional. Preencha para exibir bolinha com 2 cores (diagonal). '
                  'Ex: produto bicolor Preto/Branco → #000000 + #FFFFFF.',
    )
    ordem = models.PositiveSmallIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Cor padrão'
        verbose_name_plural = 'Cores padrão'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return self.nome

    def clean(self):
        self.nome = sanitize_text(self.nome, max_length=50).upper()
        if self.codigo_hex and not self.codigo_hex.startswith('#'):
            self.codigo_hex = f'#{self.codigo_hex}'
        if self.codigo_hex_secundario and not self.codigo_hex_secundario.startswith('#'):
            self.codigo_hex_secundario = f'#{self.codigo_hex_secundario}'

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProdutoCorFoto(models.Model):
    """
    Vincula uma foto do produto a uma cor específica.
    Ao clicar na bolinha da cor no site, a galeria muda para essa foto.

    Exemplo:
        Produto: Body Adriana  |  Cor: Preto  |  Foto: body_adriana_preto.jpg
        → clicar na bolinha Preto exibe a foto do body na cor preta.

    Uma entrada por (produto + cor) é suficiente — vale para todos os tamanhos.
    """
    produto = models.ForeignKey(
        Produto, on_delete=models.CASCADE, related_name='fotos_por_cor',
        verbose_name='Produto',
    )
    cor = models.ForeignKey(
        'CorPadrao', on_delete=models.CASCADE, related_name='fotos_produto',
        verbose_name='Cor',
        help_text='Selecione a cor. Ao clicar nessa bolinha no site, a galeria muda para a foto abaixo.',
    )
    imagem = models.ForeignKey(
        ProdutoImagem, on_delete=models.CASCADE, related_name='cor_fotos',
        verbose_name='Foto',
        help_text='Escolha uma das fotos já cadastradas neste produto para representar essa cor.',
        null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Foto por cor'
        verbose_name_plural = 'Fotos por cor'
        unique_together = ('produto', 'cor')
        ordering = ['cor__ordem', 'cor__nome']

    def __str__(self):
        cor_nome = self.cor.nome if self.cor_id else '—'
        return f'{self.produto.nome} — {cor_nome}'


class TamanhoPadrao(models.Model):
    """Lista-mestre de tamanhos usados nas variações de produto."""
    nome  = models.CharField('Tamanho', max_length=20, unique=True,
                help_text='Ex: P, M, G, GG, 38, 40')
    ordem = models.PositiveSmallIntegerField('Ordem', default=0,
                help_text='Menor número aparece primeiro. Ex: PP=0, P=1, M=2, G=3, GG=4')

    class Meta:
        verbose_name = 'Tamanho padrão'
        verbose_name_plural = 'Tamanhos padrão'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = sanitize_text(self.nome, max_length=20).upper()
        super().save(*args, **kwargs)


class Variacao(models.Model):
    """
    Variação de um produto — cada linha é uma combinação única de COR + TAMANHO.

    Exemplos:
        Cor: Preto  |  Tamanho: P  |  SKU: 100  |  ID Bling: 9876
        Cor: Preto  |  Tamanho: M  |  SKU: 101  |  ID Bling: 9877
        Cor: Branco |  Tamanho: P  |  SKU: 102  |  ID Bling: 9878

    Se o produto tiver apenas tamanho (sem cor), deixe o campo Cor vazio.
    Se tiver apenas cor (sem tamanho), deixe o campo Tamanho vazio.
    """

    DISPONIBILIDADE_IMEDIATA = 'imediata'
    DISPONIBILIDADE_SOB_DEMANDA = 'sob_demanda'
    DISPONIBILIDADE_CHOICES = [
        (DISPONIBILIDADE_IMEDIATA, 'Disponibilidade imediata'),
        (DISPONIBILIDADE_SOB_DEMANDA, 'Sob demanda'),
    ]

    SEM_ESTOQUE_INDISPONIVEL = 'indisponivel'
    SEM_ESTOQUE_SOB_DEMANDA  = 'sob_demanda'
    SEM_ESTOQUE_CHOICES = [
        (SEM_ESTOQUE_INDISPONIVEL, 'Tornar indisponível'),
        (SEM_ESTOQUE_SOB_DEMANDA,  'Continuar vendendo sob demanda'),
    ]

    produto   = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='variacoes')

    cor       = models.ForeignKey(
        CorPadrao, verbose_name='Cor',
        null=True, blank=True, on_delete=models.SET_NULL,
        help_text='Selecione da lista. Cadastre novas cores em Produtos → Cores padrão.',
    )
    tamanho   = models.ForeignKey(
        TamanhoPadrao, verbose_name='Tamanho',
        null=True, blank=True, on_delete=models.SET_NULL,
        help_text='Selecione da lista. Cadastre novos tamanhos em Produtos → Tamanhos padrão.',
    )

    preco = models.DecimalField(
        'Preço da variação',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Opcional. Se vazio, usa o preço geral do produto.',
    )
    preco_promocional = models.DecimalField(
        'Preço promocional da variação',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Opcional. Se vazio, não aplica promoção da variação.',
    )
    estoque        = models.PositiveIntegerField('Estoque', default=0)
    disponibilidade = models.CharField(
        'Disponibilidade',
        max_length=20,
        choices=DISPONIBILIDADE_CHOICES,
        default=DISPONIBILIDADE_IMEDIATA,
        help_text='Use "disponibilidade imediata" para peças a pronta entrega e "sob demanda" para peças confeccionadas após a compra.',
    )
    prazo_confeccao_dias = models.PositiveSmallIntegerField(
        'Prazo de confecção (dias úteis)',
        null=True,
        blank=True,
        help_text='Preencha apenas para variações sob demanda. Esse prazo será somado ao prazo do frete.',
    )
    sku_variacao   = models.CharField('SKU', max_length=80, blank=True, db_index=True,
                        help_text='SKU individual desta variação no Bling. Ex: 100')
    bling_variacao_id = models.CharField('ID Bling', max_length=50, blank=True,
                        help_text='ID do produto filho desta variação no Bling.')
    usa_sync_bling = models.BooleanField(
        'Sync estoque Bling',
        default=False,
        help_text='Quando ativo, o estoque é atualizado automaticamente pelo Bling.',
    )
    comportamento_sem_estoque = models.CharField(
        'Quando acabar o estoque',
        max_length=20,
        choices=SEM_ESTOQUE_CHOICES,
        default=SEM_ESTOQUE_INDISPONIVEL,
        help_text=(
            'Define o comportamento ao zerar o estoque '
            '(só se aplica a variações com disponibilidade imediata).'
        ),
    )
    ativa          = models.BooleanField('Ativa', default=True)

    class Meta:
        verbose_name = 'Variação'
        verbose_name_plural = 'Variações'
        ordering = ['cor__ordem', 'cor__nome', 'tamanho__ordem', 'tamanho__nome']

    def __str__(self):
        partes = []
        if self.cor_id:
            partes.append(self.cor.nome)
        if self.tamanho_id:
            partes.append(f'tam. {self.tamanho.nome}')
        descricao = ' / '.join(partes) if partes else 'sem variação'
        return f'{self.produto.nome} — {descricao}'

    def clean(self):
        if not self.cor_id and not self.tamanho_id:
            raise ValidationError('Informe pelo menos a cor ou o tamanho da variação.')
        # Aviso de duplicata
        if self.produto_id:
            qs = Variacao.objects.filter(produto_id=self.produto_id, cor=self.cor, tamanho=self.tamanho)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                cor_nome = self.cor.nome if self.cor_id else '—'
                tam_nome = self.tamanho.nome if self.tamanho_id else '—'
                raise ValidationError(
                    f'Já existe uma variação com cor "{cor_nome}" e tamanho "{tam_nome}" '
                    f'para este produto. Edite a variação existente.'
                )
        if self.disponibilidade == self.DISPONIBILIDADE_SOB_DEMANDA:
            if not self.prazo_confeccao_dias or self.prazo_confeccao_dias <= 0:
                raise ValidationError({
                    'prazo_confeccao_dias': 'Informe o prazo de confecção em dias úteis para variações sob demanda.'
                })
        elif self.comportamento_sem_estoque == self.SEM_ESTOQUE_SOB_DEMANDA:
            if not self.prazo_confeccao_dias or self.prazo_confeccao_dias <= 0:
                raise ValidationError({
                    'prazo_confeccao_dias': (
                        'Informe o prazo de confecção (dias úteis) — '
                        'necessário para vender sob demanda quando o estoque acabar.'
                    )
                })
        else:
            self.prazo_confeccao_dias = None
        if self.preco_promocional is not None and self.preco_promocional <= 0:
            self.preco_promocional = None
        preco_base = self.preco if self.preco is not None else (self.produto.preco if self.produto_id else None)
        if self.preco is not None and self.preco <= 0:
            raise ValidationError({'preco': 'Preço da variação deve ser maior que zero.'})
        if self.preco_promocional is not None and preco_base is not None and self.preco_promocional >= preco_base:
            raise ValidationError({
                'preco_promocional': 'Preço promocional da variação deve ser menor que o preço base aplicado.'
            })

    @property
    def label(self):
        """Rótulo amigável: 'Preto / tam. P'"""
        partes = []
        if self.cor_id:
            partes.append(self.cor.nome)
        if self.tamanho_id:
            partes.append(f'tam. {self.tamanho.nome}')
        return ' / '.join(partes)

    @property
    def modo_efetivo(self):
        """Retorna 'pronta_entrega', 'sob_demanda' ou 'indisponivel' conforme estado atual."""
        if self.disponibilidade == self.DISPONIBILIDADE_SOB_DEMANDA:
            return 'sob_demanda'
        if self.estoque > 0:
            return 'pronta_entrega'
        if self.comportamento_sem_estoque == self.SEM_ESTOQUE_SOB_DEMANDA:
            return 'sob_demanda'
        return 'indisponivel'

    @property
    def disponivel(self):
        return self.ativa and self.modo_efetivo != 'indisponivel'

    @property
    def usa_preco_proprio(self):
        return self.preco is not None or self.preco_promocional is not None

    @property
    def preco_base(self):
        if self.preco is not None:
            return self.preco
        return self.produto.preco

    @property
    def preco_promocional_efetivo(self):
        if self.preco_promocional is not None:
            return self.preco_promocional
        if not self.usa_preco_proprio:
            return self.produto.preco_promocional
        return None

    @property
    def preco_atual(self):
        return self.preco_promocional_efetivo if self.preco_promocional_efetivo else self.preco_base

    @property
    def em_promocao(self):
        return bool(self.preco_promocional_efetivo and self.preco_promocional_efetivo < self.preco_base)

    @property
    def pronta_entrega(self):
        return self.modo_efetivo == 'pronta_entrega'

    @property
    def sob_demanda(self):
        return self.modo_efetivo == 'sob_demanda'

    @property
    def prazo_total_adicional_dias(self):
        return self.prazo_confeccao_dias or 0

    @property
    def disponibilidade_label(self):
        if self.sob_demanda:
            dias = self.prazo_total_adicional_dias
            if dias:
                return f'Sob demanda: +{dias} dia{"s" if dias != 1 else ""} útil{"eis" if dias != 1 else ""} para confecção'
            return 'Sob demanda'
        return 'Disponibilidade imediata'


class TabelaMedidas(models.Model):
    """Tabela de medidas exibida ao clicar em 'Guia de tamanhos' no produto."""
    nome = models.CharField('Nome', max_length=80, default='Geral',
                help_text='Ex: Body, Beachwear, Geral')
    cabecalho_1 = models.CharField('Coluna 1', max_length=20, blank=True, default='P')
    cabecalho_2 = models.CharField('Coluna 2', max_length=20, blank=True, default='M')
    cabecalho_3 = models.CharField('Coluna 3', max_length=20, blank=True, default='G')
    cabecalho_4 = models.CharField('Coluna 4', max_length=20, blank=True, default='GG')
    cabecalho_5 = models.CharField('Coluna 5', max_length=20, blank=True)
    cabecalho_6 = models.CharField('Coluna 6', max_length=20, blank=True)
    conteudo = models.TextField(
        'Conteúdo legado da tabela',
        blank=True,
        help_text=(
            'Opcional. Mantido por compatibilidade para tabelas antigas em texto/HTML. '
            'Se você cadastrar linhas abaixo, o site usará a tabela estruturada.'
        )
    )
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tabela de medidas'
        verbose_name_plural = 'Tabelas de medidas'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def clean(self):
        self.nome = sanitize_text(self.nome, max_length=80)
        for idx in range(1, 7):
            campo = f'cabecalho_{idx}'
            valor = getattr(self, campo, '')
            setattr(self, campo, sanitize_text(valor, max_length=20))

    @property
    def colunas_configuradas(self):
        colunas = []
        for idx in range(1, 7):
            valor = getattr(self, f'cabecalho_{idx}', '').strip()
            if valor:
                colunas.append((idx, valor))
        return colunas

    @property
    def usa_tabela_estruturada(self):
        return bool(self.colunas_configuradas and self.linhas.exists())

    @property
    def linhas_formatadas(self):
        colunas = self.colunas_configuradas
        linhas = []
        for linha in self.linhas.all():
            valores = []
            for idx, _rotulo in colunas:
                valores.append(getattr(linha, f'valor_{idx}', ''))
            linhas.append({
                'rotulo': linha.rotulo,
                'valores': valores,
            })
        return linhas

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TabelaMedidasLinha(models.Model):
    tabela = models.ForeignKey(
        TabelaMedidas, on_delete=models.CASCADE, related_name='linhas',
        verbose_name='Tabela',
    )
    ordem = models.PositiveSmallIntegerField('Ordem', default=0)
    medida = models.CharField('Medida', max_length=80)
    unidade = models.CharField(
        'Unidade', max_length=20, blank=True,
        help_text='Opcional. Ex: cm, kg'
    )
    valor_1 = models.CharField('Valor coluna 1', max_length=40, blank=True)
    valor_2 = models.CharField('Valor coluna 2', max_length=40, blank=True)
    valor_3 = models.CharField('Valor coluna 3', max_length=40, blank=True)
    valor_4 = models.CharField('Valor coluna 4', max_length=40, blank=True)
    valor_5 = models.CharField('Valor coluna 5', max_length=40, blank=True)
    valor_6 = models.CharField('Valor coluna 6', max_length=40, blank=True)

    class Meta:
        verbose_name = 'Linha da tabela'
        verbose_name_plural = 'Linhas da tabela'
        ordering = ['ordem', 'id']

    def __str__(self):
        return f'{self.tabela.nome} — {self.rotulo}'

    @property
    def rotulo(self):
        if self.unidade:
            return f'{self.medida} ({self.unidade})'
        return self.medida

    def clean(self):
        self.medida = sanitize_text(self.medida, max_length=80)
        self.unidade = sanitize_text(self.unidade, max_length=20)
        for idx in range(1, 7):
            campo = f'valor_{idx}'
            valor = getattr(self, campo, '')
            setattr(self, campo, sanitize_text(valor, max_length=40))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Avaliacao(models.Model):
    """Avaliações da loja — moderadas antes de aparecer no site."""

    pedido = models.OneToOneField(
        'pedidos.Pedido',
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name='avaliacao_compra',
        verbose_name='Pedido',
    )
    produto = models.ForeignKey(
        Produto, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='avaliacoes',
        verbose_name='Produto (opcional)',
    )
    cliente = models.ForeignKey('usuarios.Cliente', on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='avaliacoes')
    nome_publico = models.CharField('Nome', max_length=80)
    nota = models.PositiveSmallIntegerField('Nota', choices=[(i, i) for i in range(1, 6)])
    nota_experiencia = models.PositiveSmallIntegerField(
        'Experiência da compra',
        choices=[(i, i) for i in range(1, 6)],
        null=True, blank=True,
    )
    nota_produtos = models.PositiveSmallIntegerField(
        'Produtos comprados',
        choices=[(i, i) for i in range(1, 6)],
        null=True, blank=True,
    )
    comentario = models.TextField('Comentário', max_length=800, blank=True)
    aprovada = models.BooleanField('Aprovada', default=False)   # moderação manual
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Avaliação'
        verbose_name_plural = 'Avaliações'
        ordering = ['-criada_em']

    def __str__(self):
        if self.pedido_id:
            prod = f'Pedido {self.pedido.numero}'
        else:
            prod = self.produto.nome if self.produto_id else 'Loja'
        return f'{prod} — {self.nota}★ por {self.nome_publico}'

    def clean(self):
        # Sanitiza campos de texto livre do cliente
        self.nome_publico = sanitize_text(self.nome_publico, max_length=80)
        self.comentario = sanitize_text(self.comentario, max_length=800)
        if self.nota_experiencia and self.nota_produtos:
            self.nota = round((self.nota_experiencia + self.nota_produtos) / 2)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class NewsletterInscricao(models.Model):
    email = models.EmailField('E-mail', max_length=254, unique=True)
    inscrito_em = models.DateTimeField('Inscrito em', auto_now_add=True)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Inscrição Newsletter'
        verbose_name_plural = 'Inscrições Newsletter'
        ordering = ['-inscrito_em']

    def __str__(self):
        return self.email
