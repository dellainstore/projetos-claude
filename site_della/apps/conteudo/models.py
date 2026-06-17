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


POSICAO_IMAGEM_BANNER = [
    ('center center', 'Centralizado (padrão)'),
    ('left center',   'Esquerda (mostra início da foto)'),
    ('right center',  'Direita (mostra fim da foto)'),
    ('center top',    'Topo (mostra parte superior)'),
    ('center bottom', 'Base (mostra parte inferior)'),
    ('left top',      'Esquerda superior'),
    ('right top',     'Direita superior'),
    ('left bottom',   'Esquerda inferior'),
    ('right bottom',  'Direita inferior'),
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

    url_botao   = models.CharField('Link do banner (ao clicar)', max_length=200, blank=True, default='/loja/',
                    help_text='Caminho relativo. Ao clicar em qualquer parte do banner, redireciona para este link. Ex: /loja/ ou /loja/bodies/')

    posicao_imagem = models.CharField(
        'Posição da imagem no banner', max_length=14, choices=POSICAO_IMAGEM_BANNER,
        default='center center',
        help_text='Define qual parte da foto fica visível quando o banner é cortado pelo navegador. Use "Esquerda" se o texto/elemento principal estiver no início da foto.')

    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Slide do banner principal'
        verbose_name_plural = 'Slides do banner principal'
        ordering = ['ordem']

    def __str__(self):
        return f'Slide {self.ordem} ({self.get_tipo_display()})'

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
                    help_text='Ideal: 900×1200px (retrato). Foco no assunto na parte superior.')
    url       = models.CharField('Link', max_length=200, default='/loja/',
                    help_text='Caminho relativo. Ex: /loja/bodies/')
    ativo     = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Mini banner'
        verbose_name_plural = 'Mini banners'
        # 'esq' > 'dir' em ordem descendente → Esquerda primeiro (fix do swap visual)
        ordering = ['-posicao']

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
    foto_ponto1 = models.ForeignKey(
        'produtos.ProdutoImagem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
        verbose_name='Foto do ponto 1',
        help_text='Foto específica para exibir. Se vazio, usa a foto principal do produto.')
    ponto1_top = models.DecimalField('Topo (%)', max_digits=5, decimal_places=1, default=30)
    ponto1_esq = models.DecimalField('Esquerda (%)', max_digits=5, decimal_places=1, default=42)

    # Ponto 2
    produto_ponto2 = models.ForeignKey(
        'produtos.Produto', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='look_ponto2',
        verbose_name='Produto do ponto 2',
        limit_choices_to={'ativo': True},
        help_text='Produto que o "+" 2 aponta.')
    foto_ponto2 = models.ForeignKey(
        'produtos.ProdutoImagem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
        verbose_name='Foto do ponto 2',
        help_text='Foto específica para exibir. Se vazio, usa a foto principal do produto.')
    ponto2_top = models.DecimalField('Topo (%)', max_digits=5, decimal_places=1, default=55)
    ponto2_esq = models.DecimalField('Esquerda (%)', max_digits=5, decimal_places=1, default=55)

    # Ponto 3
    produto_ponto3 = models.ForeignKey(
        'produtos.Produto', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='look_ponto3',
        verbose_name='Produto do ponto 3',
        limit_choices_to={'ativo': True},
        help_text='Produto que o "+" 3 aponta.')
    foto_ponto3 = models.ForeignKey(
        'produtos.ProdutoImagem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
        verbose_name='Foto do ponto 3',
        help_text='Foto específica para exibir. Se vazio, usa a foto principal do produto.')
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

    modo_manutencao = models.BooleanField(
        'Modo manutenção',
        default=False,
        help_text=(
            'Ativado: somente o admin consegue acessar o site. '
            'Visitantes veem uma página "Em breve". '
            'Desativado: site funciona normalmente.'
        ),
    )

    class Meta:
        verbose_name = 'Configurações da Loja'
        verbose_name_plural = 'Configurações da Loja'

    def __str__(self):
        return 'Configurações da Loja'

    @classmethod
    def get_config(cls):
        return cls.objects.first()


class TarjaFrase(models.Model):
    """Frases exibidas na tarja animada no topo do site (máx. 6 ativas)."""

    texto = models.CharField('Texto', max_length=100,
        help_text='Ex: Frete grátis acima de R$ 500 · Parcelamento em até 10x')
    ativa = models.BooleanField('Ativa', default=True)
    ordem = models.PositiveSmallIntegerField('Ordem', default=0,
        help_text='Menor número aparece primeiro.')

    class Meta:
        verbose_name        = 'Tarja (Frase)'
        verbose_name_plural = 'Tarja (Frases)'
        ordering            = ['ordem', 'id']

    def __str__(self):
        return self.texto


class LinkBio(models.Model):
    """
    Botões da página /links (bio do Instagram). TODOS os botões da página vêm
    daqui (loja, WhatsApp, endereços e links de destaque), gerenciáveis no admin:
    texto, link, subtítulo, ícone/estilo, ordem e ativar/desativar.
    """

    ICONE_NENHUM   = 'nenhum'
    ICONE_LOJA     = 'loja'
    ICONE_WHATSAPP = 'whatsapp'
    ICONE_LOCAL    = 'local'
    ICONE_DESTAQUE = 'destaque'
    ICONES = [
        (ICONE_LOJA,     'Loja (botão principal preto)'),
        (ICONE_DESTAQUE, 'Destaque (dourado)'),
        (ICONE_WHATSAPP, 'WhatsApp (ícone verde)'),
        (ICONE_LOCAL,    'Endereço / Mapa (pino)'),
        (ICONE_NENHUM,   'Simples (sem ícone)'),
    ]

    titulo    = models.CharField('Título', max_length=60,
        help_text='Texto do botão. Ex: Loja online, WhatsApp Vendas, Nova Coleção.')
    subtitulo = models.CharField('Subtítulo', max_length=120, blank=True,
        help_text='Linha menor abaixo do título. Ex: o endereço completo da loja. Deixe vazio se não quiser.')
    url       = models.URLField('Link', max_length=500,
        help_text='Para onde o botão leva. Ex: https://www.dellainstore.com/ ou link do Google Maps.')
    icone     = models.CharField('Ícone / Estilo', max_length=10, choices=ICONES, default=ICONE_NENHUM,
        help_text='Define o ícone e o visual do botão.')
    nova_aba  = models.BooleanField('Abrir em nova aba', default=True,
        help_text='Recomendado para WhatsApp e mapas. Desmarque para a loja/home.')
    ordem     = models.PositiveSmallIntegerField('Ordem', default=0,
        help_text='Menor número aparece primeiro.')
    ativo     = models.BooleanField('Ativo', default=True,
        help_text='Desmarque para esconder sem precisar excluir.')

    class Meta:
        verbose_name        = 'Link da Bio (Instagram)'
        verbose_name_plural = 'Links da Bio (Instagram)'
        ordering            = ['ordem', 'id']

    def __str__(self):
        return self.titulo


class ContatoFormulario(models.Model):
    nome        = models.CharField('Nome', max_length=100)
    email       = models.EmailField('E-mail', max_length=254)
    telefone    = models.CharField('Telefone', max_length=20, blank=True)
    mensagem    = models.TextField('Mensagem', max_length=1000)
    recebido_em = models.DateTimeField('Recebido em', auto_now_add=True)
    respondido  = models.BooleanField('Respondido', default=False)
    respondido_em = models.DateTimeField('Respondido em', null=True, blank=True)
    observacao  = models.TextField('Observacao interna', blank=True,
                    help_text='Anotacoes internas sobre este contato (nao visiveis ao cliente).')

    class Meta:
        verbose_name        = 'Formulario de contato'
        verbose_name_plural = 'Formularios de contato'
        ordering            = ['-recebido_em']

    def __str__(self):
        from django.utils.formats import date_format
        data = date_format(self.recebido_em, 'd/m/Y H:i') if self.recebido_em else ''
        return f'{self.nome} ({self.email}) - {data}'


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
