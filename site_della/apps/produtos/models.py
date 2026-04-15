import os
import uuid
from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from apps.core_utils.sanitize import sanitize_text, validate_image_upload


def produto_imagem_path(instance, filename):
    """Salva imagens em subpastas por produto para evitar diretório flat gigante."""
    ext = filename.rsplit('.', 1)[-1].lower()
    nome = f'{uuid.uuid4().hex}.{ext}'
    return f'produtos/{instance.produto.slug if hasattr(instance, "produto") else "temp"}/{nome}'


class Categoria(models.Model):
    nome = models.CharField('Nome', max_length=80, unique=True)
    slug = models.SlugField('Slug', max_length=80, unique=True, blank=True)
    descricao = models.TextField('Descrição', blank=True, max_length=500)
    imagem = models.ImageField('Imagem', upload_to='categorias/', blank=True)
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

    def __str__(self):
        return self.nome

    def clean(self):
        self.nome = sanitize_text(self.nome, max_length=80)
        self.descricao = sanitize_text(self.descricao, max_length=500)
        if self.imagem and hasattr(self.imagem, 'file'):
            validate_image_upload(self.imagem)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        self.full_clean()
        super().save(*args, **kwargs)


class Produto(models.Model):
    GENEROS = [('F', 'Feminino'), ('U', 'Unissex')]

    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='produtos')
    nome = models.CharField('Nome', max_length=200)
    slug = models.SlugField('Slug', max_length=220, unique=True, blank=True)
    descricao = models.TextField('Descrição', max_length=2000)
    composicao = models.CharField('Composição/Material', max_length=200, blank=True)
    genero = models.CharField('Gênero', max_length=1, choices=GENEROS, default='F')

    # Preços
    preco = models.DecimalField('Preço', max_digits=10, decimal_places=2)
    preco_promocional = models.DecimalField('Preço promocional', max_digits=10,
                                             decimal_places=2, null=True, blank=True)

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
    def preco_atual(self):
        return self.preco_promocional if self.preco_promocional else self.preco

    @property
    def em_promocao(self):
        return bool(self.preco_promocional and self.preco_promocional < self.preco)

    @property
    def percentual_desconto(self):
        if self.em_promocao:
            return int((1 - self.preco_promocional / self.preco) * 100)
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

    @property
    def imagem_principal(self):
        return self.imagens.filter(principal=True).first() or self.imagens.first()

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('produtos:detalhe', kwargs={'slug': self.slug})

    def clean(self):
        self.nome = sanitize_text(self.nome, max_length=200)
        self.descricao = sanitize_text(self.descricao, max_length=2000)
        self.composicao = sanitize_text(self.composicao, max_length=200)
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
    alt = models.CharField('Texto alternativo', max_length=200, blank=True)
    principal = models.BooleanField('Principal', default=False)
    ordem = models.PositiveSmallIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Imagem do produto'
        verbose_name_plural = 'Imagens do produto'
        ordering = ['-principal', 'ordem']

    def clean(self):
        if self.imagem and hasattr(self.imagem, 'file'):
            validate_image_upload(self.imagem)
        self.alt = sanitize_text(self.alt, max_length=200)

    def save(self, *args, **kwargs):
        # Garante só uma imagem principal por produto
        if self.principal:
            ProdutoImagem.objects.filter(
                produto=self.produto, principal=True
            ).exclude(pk=self.pk).update(principal=False)
        super().save(*args, **kwargs)


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
        self.nome = sanitize_text(self.nome, max_length=50)
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

    estoque        = models.PositiveIntegerField('Estoque', default=0)
    sku_variacao   = models.CharField('SKU', max_length=80, blank=True, db_index=True,
                        help_text='SKU individual desta variação no Bling. Ex: 100')
    bling_variacao_id = models.CharField('ID Bling', max_length=50, blank=True,
                        help_text='ID do produto filho desta variação no Bling.')
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
    def disponivel(self):
        return self.estoque > 0


class TabelaMedidas(models.Model):
    """Tabela de medidas exibida ao clicar em 'Guia de tamanhos' no produto."""
    nome = models.CharField('Nome', max_length=80, default='Geral',
                help_text='Ex: Body, Beachwear, Geral')
    categoria = models.ForeignKey(
        Categoria, null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name='Categoria',
        help_text='Deixe em branco para usar como tabela padrão geral. '
                  'Se preenchida, é usada para produtos dessa categoria.',
    )
    conteudo = models.TextField(
        'Conteúdo da tabela',
        help_text=(
            'Descreva as medidas. Pode usar texto simples ou HTML básico. '
            'Exemplo: PP: busto 82cm | cintura 62cm | quadril 88cm'
        )
    )
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tabela de medidas'
        verbose_name_plural = 'Tabelas de medidas'
        ordering = ['nome']

    def __str__(self):
        if self.categoria:
            return f'{self.nome} — {self.categoria.nome}'
        return f'{self.nome} (padrão geral)'


class Avaliacao(models.Model):
    """Avaliações de clientes — moderadas antes de aparecer no site."""

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='avaliacoes')
    cliente = models.ForeignKey('usuarios.Cliente', on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='avaliacoes')
    nome_publico = models.CharField('Nome', max_length=80)
    nota = models.PositiveSmallIntegerField('Nota', choices=[(i, i) for i in range(1, 6)])
    titulo = models.CharField('Título', max_length=120, blank=True)
    comentario = models.TextField('Comentário', max_length=800, blank=True)
    aprovada = models.BooleanField('Aprovada', default=False)   # moderação manual
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Avaliação'
        verbose_name_plural = 'Avaliações'
        ordering = ['-criada_em']

    def __str__(self):
        return f'{self.produto.nome} — {self.nota}★ por {self.nome_publico}'

    def clean(self):
        # Sanitiza campos de texto livre do cliente
        self.nome_publico = sanitize_text(self.nome_publico, max_length=80)
        self.titulo = sanitize_text(self.titulo, max_length=120)
        self.comentario = sanitize_text(self.comentario, max_length=800)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
