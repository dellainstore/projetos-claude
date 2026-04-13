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

    # Integração Bling
    bling_id = models.CharField('ID Bling', max_length=50, blank=True, db_index=True)
    sku = models.CharField('SKU', max_length=80, blank=True, db_index=True)

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
    def imagem_principal(self):
        return self.imagens.filter(principal=True).first() or self.imagens.first()

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('produtos:detalhe', kwargs={'slug': self.slug})

    def clean(self):
        self.nome = sanitize_text(self.nome, max_length=200)
        self.descricao = sanitize_text(self.descricao, max_length=2000)
        self.composicao = sanitize_text(self.composicao, max_length=200)
        if self.preco_promocional and self.preco_promocional >= self.preco:
            raise ValidationError({'preco_promocional': 'Preço promocional deve ser menor que o preço original.'})

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


class Variacao(models.Model):
    """Variações de tamanho/cor de um produto (ex: P, M, G / Preto, Branco)."""

    TIPOS = [('tamanho', 'Tamanho'), ('cor', 'Cor')]

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='variacoes')
    tipo = models.CharField('Tipo', max_length=10, choices=TIPOS)
    nome = models.CharField('Nome', max_length=50)           # ex: "P", "M", "Preto"
    codigo_hex = models.CharField('Cor hex', max_length=7, blank=True)  # ex: #000000
    estoque = models.PositiveIntegerField('Estoque', default=0)
    sku_variacao = models.CharField('SKU variação', max_length=80, blank=True)
    ativa = models.BooleanField('Ativa', default=True)

    class Meta:
        verbose_name = 'Variação'
        verbose_name_plural = 'Variações'
        ordering = ['tipo', 'nome']
        unique_together = [['produto', 'tipo', 'nome']]

    def __str__(self):
        return f'{self.produto.nome} — {self.get_tipo_display()}: {self.nome}'

    def clean(self):
        self.nome = sanitize_text(self.nome, max_length=50)
        if self.codigo_hex and not self.codigo_hex.startswith('#'):
            self.codigo_hex = f'#{self.codigo_hex}'

    @property
    def disponivel(self):
        return self.estoque > 0


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
