import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from apps.core_utils.sanitize import validate_image_upload


def banner_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'banners/{uuid.uuid4().hex}.{ext}'


def mini_banner_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'mini-banners/{uuid.uuid4().hex}.{ext}'


def look_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'look-semana/{uuid.uuid4().hex}.{ext}'


TIPOS_BANNER = [
    ('video', 'Vídeo'),
    ('foto',  'Foto'),
]


class BannerPrincipal(models.Model):
    """
    Slides do banner principal (hero) da homepage.
    Ordem 1 = primeiro slide. Recomendado: ordem 1 para o vídeo.
    """
    ordem      = models.PositiveSmallIntegerField(
        'Ordem', default=1,
        help_text='1 = primeiro slide. Recomendado: ordem 1 para o vídeo.')
    tipo       = models.CharField('Tipo', max_length=5, choices=TIPOS_BANNER, default='foto')

    video      = models.FileField(
        'Vídeo (MP4) — Desktop', upload_to=banner_upload_path, blank=True,
        validators=[FileExtensionValidator(['mp4', 'webm'])],
        help_text='Somente se tipo = Vídeo. Formato MP4, paisagem 1920×1080px, até 50 MB.')
    video_mobile = models.FileField(
        'Vídeo (MP4) — Mobile', upload_to=banner_upload_path, blank=True,
        validators=[FileExtensionValidator(['mp4', 'webm'])],
        help_text='Opcional. Versão vertical para celular. Retrato 1080×1920px (9:16), até 30 MB.')
    foto       = models.ImageField(
        'Foto — Desktop', upload_to=banner_upload_path, blank=True,
        help_text='Somente se tipo = Foto. Paisagem 1920×1080px.')
    foto_mobile = models.ImageField(
        'Foto — Mobile', upload_to=banner_upload_path, blank=True,
        help_text='Opcional. Versão vertical para celular. Retrato 1080×1920px (9:16).')
    poster     = models.ImageField(
        'Poster do vídeo', upload_to=banner_upload_path, blank=True,
        help_text='Imagem exibida enquanto o vídeo carrega. Ideal: 1920×1080px.')

    pretitulo  = models.CharField('Pré-título', max_length=80, blank=True,
                    help_text='Opcional. Ex: "Nova Coleção 2025"')
    titulo     = models.CharField('Título', max_length=120, blank=True,
                    help_text='Opcional — deixe vazio se o vídeo/foto já tem o texto na imagem.')
    titulo_italico = models.CharField('Trecho em itálico', max_length=80, blank=True,
                    help_text='Parte final do título que aparece em itálico/dourado.')
    subtitulo  = models.CharField('Subtítulo', max_length=200, blank=True)
    texto_botao = models.CharField('Texto do botão', max_length=60, blank=True,
                    help_text='Opcional. Ex: "Explorar coleção". Deixe vazio para não exibir botão.')
    url_botao   = models.CharField('Link do botão', max_length=200, blank=True, default='/loja/',
                    help_text='Caminho relativo. Ex: /loja/ ou /loja/bodies/')

    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Slide do banner principal'
        verbose_name_plural = 'Slides do banner principal'
        ordering = ['ordem']

    def __str__(self):
        return f'Slide {self.ordem} — {self.titulo}'

    def clean(self):
        # Valida somente ao criar (pk ainda não existe)
        # Para edições posteriores o arquivo já existe na instância
        if not self.pk:
            if self.tipo == 'video' and not self.video:
                raise ValidationError({'video': 'Envie o arquivo de vídeo para este slide.'})
            if self.tipo == 'foto' and not self.foto:
                raise ValidationError({'foto': 'Envie a foto para este slide.'})
        # Valida magic bytes das imagens enviadas
        for campo in (self.foto, self.foto_mobile, self.poster):
            if campo and hasattr(campo, 'file'):
                validate_image_upload(campo)


class MiniBanner(models.Model):
    """Mini banners abaixo do hero — exibidos em 2 colunas."""

    POSICOES = [('esq', 'Esquerda'), ('dir', 'Direita')]

    posicao   = models.CharField('Posição', max_length=3, choices=POSICOES, unique=True)
    foto      = models.ImageField('Foto', upload_to=mini_banner_upload_path,
                    help_text='Ideal: 900×1200px (retrato). Foco no assunto na parte inferior.')
    pretitulo = models.CharField('Pré-título', max_length=80, blank=True,
                    help_text='Ex: "Combinação de Shapes + Cores"')
    titulo    = models.CharField('Título', max_length=80, blank=True,
                    help_text='Opcional — o banner já pode ter o texto na própria imagem.')
    url       = models.CharField('Link', max_length=200, default='/loja/',
                    help_text='Caminho relativo. Ex: /loja/bodies/')
    ativo     = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Mini banner'
        verbose_name_plural = 'Mini banners'
        ordering = ['posicao']

    def __str__(self):
        return f'Mini banner — {self.get_posicao_display()}'

    def clean(self):
        if self.foto and hasattr(self.foto, 'file'):
            validate_image_upload(self.foto)


class LookDaSemana(models.Model):
    """
    Seção Look da semana da homepage.
    Cada ponto "+" tem seu próprio produto e posição na foto.
    """
    titulo    = models.CharField('Título', max_length=100, default='Look da semana')
    descricao = models.TextField('Descrição', max_length=400,
                    help_text='Texto que aparece ao lado da foto. Máx. 400 caracteres.')
    foto      = models.ImageField('Foto do look', upload_to=look_upload_path,
                    help_text='Ideal: 800×1100px (retrato). Exibida no lado esquerdo.')

    # Ponto 1
    produto_ponto1 = models.ForeignKey(
        'produtos.Produto', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='look_ponto1',
        verbose_name='Produto do ponto 1',
        limit_choices_to={'ativo': True},
        help_text='Produto que o "+" 1 aponta.')
    ponto1_top = models.DecimalField('Topo (%)', max_digits=5, decimal_places=1, default=30)
    ponto1_esq = models.DecimalField('Esquerda (%)', max_digits=5, decimal_places=1, default=42)

    # Ponto 2
    produto_ponto2 = models.ForeignKey(
        'produtos.Produto', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='look_ponto2',
        verbose_name='Produto do ponto 2',
        limit_choices_to={'ativo': True},
        help_text='Produto que o "+" 2 aponta.')
    ponto2_top = models.DecimalField('Topo (%)', max_digits=5, decimal_places=1, default=55)
    ponto2_esq = models.DecimalField('Esquerda (%)', max_digits=5, decimal_places=1, default=55)

    # Ponto 3
    produto_ponto3 = models.ForeignKey(
        'produtos.Produto', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='look_ponto3',
        verbose_name='Produto do ponto 3',
        limit_choices_to={'ativo': True},
        help_text='Produto que o "+" 3 aponta.')
    ponto3_top = models.DecimalField('Topo (%)', max_digits=5, decimal_places=1, default=70)
    ponto3_esq = models.DecimalField('Esquerda (%)', max_digits=5, decimal_places=1, default=30)

    ativo     = models.BooleanField('Ativo', default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Look da semana'
        verbose_name_plural = 'Looks da semana'
        ordering = ['-criado_em']

    def __str__(self):
        from django.utils.formats import date_format
        data = date_format(self.criado_em, 'd/m/Y') if self.criado_em else ''
        return f'{self.titulo} ({data})'

    def clean(self):
        if self.foto and hasattr(self.foto, 'file'):
            validate_image_upload(self.foto)


class PaginaEstatica(models.Model):
    """Páginas institucionais editáveis pelo admin (politica, trocas, sobre, etc.)."""

    SLUGS = [
        ('politica_privacidade', 'Política de privacidade'),
        ('trocas_devolucoes', 'Trocas e devoluções'),
        ('sobre', 'Nossa história'),
        ('termos_uso', 'Termos de uso'),
        ('perguntas_frequentes', 'Perguntas frequentes'),
        ('meios_pagamento', 'Meios de pagamento e frete'),
    ]

    slug     = models.CharField('Página', max_length=30, choices=SLUGS, unique=True)
    titulo   = models.CharField('Título', max_length=120)
    conteudo = models.TextField(
        'Conteúdo',
        help_text=(
            'Editor de texto rico — use a barra de ferramentas para formatar. '
            'Negrito, itálico, títulos, listas e links são suportados. '
            'O conteúdo é salvo como HTML.'
        )
    )
    imagem   = models.ImageField(
        'Imagem (opcional)',
        upload_to='paginas/',
        blank=True,
        help_text='Usada na página "Nossa história" ao lado do texto. Proporção recomendada: 3:4.',
    )
    ativo    = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Página estática'
        verbose_name_plural = 'Páginas estáticas'

    def __str__(self):
        return self.get_slug_display()


class ConfiguracaoLoja(models.Model):
    """Configurações gerais da loja (singleton — apenas 1 registro)."""

    frete_gratis_acima = models.DecimalField(
        'Frete grátis acima de (R$)',
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text='Deixe em branco para desativar. Ex: 500.00 para frete grátis acima de R$ 500.'
    )

    class Meta:
        verbose_name = 'Configuração da loja'
        verbose_name_plural = 'Configurações da loja'


class InstagramPost(models.Model):
    """
    Post do Instagram para exibição na homepage.
    Sincronizado manualmente pelo admin via botão "Importar do Instagram".
    O admin escolhe quais ficam ativos (visíveis no site).
    """
    instagram_id  = models.CharField('ID do post', max_length=50, unique=True)
    media_type    = models.CharField('Tipo', max_length=20, default='IMAGE')
    imagem_local  = models.ImageField(
        'Imagem', upload_to='instagram/', blank=True, null=True,
        help_text='Baixada automaticamente na importação.',
    )
    permalink     = models.URLField('Link do post', max_length=500)
    caption       = models.TextField('Legenda', blank=True)
    timestamp     = models.DateTimeField('Data do post', null=True, blank=True)
    ativo         = models.BooleanField(
        'Exibir no site', default=False,
        help_text='Marque os posts que devem aparecer na seção Instagram da homepage.',
    )
    ordem         = models.PositiveIntegerField(
        'Ordem', default=0,
        help_text='Menor número = aparece primeiro. Posts com a mesma ordem ficam por data.',
    )

    class Meta:
        verbose_name        = 'Post Instagram'
        verbose_name_plural = 'Posts Instagram'
        ordering            = ['ordem', '-timestamp']

    def __str__(self):
        return f'Post {self.instagram_id} ({self.media_type})'

    @property
    def imagem_url(self):
        if self.imagem_local:
            return self.imagem_local.url
        return ''
