import uuid
import random
import string
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core_utils.sanitize import sanitize_text, sanitize_address, sanitize_phone
import json


def gerar_codigo_vendedor():
    """Mantido para compatibilidade com migrations antigas."""
    chars = string.ascii_uppercase + string.digits
    while True:
        codigo = ''.join(random.choices(chars, k=8))
        if not CodigoVendedor.objects.filter(codigo=codigo).exists():
            return codigo


def gerar_numero_pedido():
    """Gera número sequencial: YYYY-0001, YYYY-0002, ..."""
    ano = timezone.now().year
    prefix = f'{ano}-'
    numeros_ano = Pedido.objects.filter(numero__startswith=prefix).values_list('numero', flat=True)
    nums_usados = set()
    for n in numeros_ano:
        try:
            parte = n[len(prefix):]
            if parte.isdigit():
                nums_usados.add(int(parte))
        except (IndexError, ValueError):
            pass
    seq = 1
    while seq in nums_usados:
        seq += 1
    return f'{ano}-{seq:04d}'


class CarrinhoAbandonado(models.Model):
    """
    Snapshot do carrinho de um cliente autenticado que não finalizou a compra.
    Gerado/atualizado cada vez que um item é adicionado ao carrinho.
    Deletado quando o checkout é concluído com sucesso.
    """
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='carrinhos_abandonados', verbose_name='Cliente',
    )
    email = models.EmailField('E-mail', max_length=254)
    nome  = models.CharField('Nome', max_length=240, blank=True)
    itens_json = models.JSONField('Itens do carrinho')
    total = models.DecimalField('Total', max_digits=10, decimal_places=2, default=0)

    email_enviado    = models.BooleanField('E-mail enviado', default=False)
    email_enviado_em = models.DateTimeField('E-mail enviado em', null=True, blank=True)
    recuperado       = models.BooleanField('Recuperado (compra feita)', default=False)

    criado_em     = models.DateTimeField('Criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name        = 'Carrinho Abandonado'
        verbose_name_plural = 'Carrinhos Abandonados'
        ordering            = ['-atualizado_em']
        unique_together     = [('cliente',)]

    def __str__(self):
        return f'{self.email} — R$ {self.total} ({self.atualizado_em.strftime("%d/%m/%Y %H:%M")})'

    @property
    def itens(self):
        return self.itens_json or []

    @property
    def quantidade_itens(self):
        return sum(item.get('quantidade', 1) for item in self.itens)


class Cupom(models.Model):
    TIPO_CHOICES = [
        ('percentual', 'Percentual (%)'),
        ('fixo',       'Valor fixo (R$)'),
    ]

    codigo = models.CharField('Código', max_length=50, unique=True,
                              help_text='Código que o cliente digita no checkout. Ex: DELLA10')
    tipo   = models.CharField('Tipo de desconto', max_length=10, choices=TIPO_CHOICES, default='percentual')
    valor  = models.DecimalField('Valor do desconto', max_digits=10, decimal_places=2,
                                  help_text='Percentual (ex: 10 = 10%) ou valor fixo em reais (ex: 30.00)')

    quantidade_total = models.PositiveIntegerField(
        'Quantidade total disponível', null=True, blank=True,
        help_text='Deixe em branco para uso ilimitado',
    )
    vezes_usado = models.PositiveIntegerField('Vezes usado', default=0, editable=False)

    um_por_cliente = models.BooleanField(
        'Apenas 1 uso por cliente', default=True,
        help_text='Se marcado, o mesmo CPF só pode usar este cupom uma vez',
    )

    valido_de  = models.DateField('Válido a partir de', null=True, blank=True)
    valido_ate = models.DateField('Válido até', null=True, blank=True)

    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Cupom'
        verbose_name_plural = 'Cupons'
        ordering = ['-id']

    def __str__(self):
        return self.codigo

    def esta_valido(self, cpf=None):
        """Retorna (ok: bool, motivo: str)."""
        if not self.ativo:
            return False, 'Cupom inativo.'
        hoje = timezone.now().date()
        if self.valido_de and hoje < self.valido_de:
            return False, 'Cupom ainda não está vigente.'
        if self.valido_ate and hoje > self.valido_ate:
            return False, 'Cupom expirado.'
        if self.quantidade_total is not None and self.vezes_usado >= self.quantidade_total:
            return False, 'Cupom esgotado.'
        if cpf and self.um_por_cliente:
            if Pedido.objects.filter(cpf=cpf, cupom=self).exclude(status='cancelado').exists():
                return False, 'Você já utilizou este cupom.'
        return True, ''

    def calcular_desconto(self, subtotal):
        """Retorna o valor de desconto a ser aplicado sobre o subtotal."""
        from decimal import Decimal
        if self.tipo == 'percentual':
            return (Decimal(str(self.valor)) / 100 * subtotal).quantize(Decimal('0.01'))
        return min(Decimal(str(self.valor)), subtotal)


class CodigoVendedor(models.Model):
    codigo = models.CharField('Código / Nome', max_length=50, unique=True,
                              help_text='Nome ou palavra-chave que identifica o vendedor. Ex: TINA')
    nome   = models.CharField('Nome completo', max_length=120)
    ativo  = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Código de vendedor'
        verbose_name_plural = 'Códigos de vendedor'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.codigo})'


class Pedido(models.Model):

    STATUS = [
        ('aguardando_pagamento', 'Aguardando Pagamento'),
        ('pagamento_confirmado', 'Pagamento Confirmado'),
        ('em_separacao',        'Em Separação'),
        ('enviado',             'Enviado'),
        ('entregue',            'Entregue'),
        ('cancelado',           'Cancelado'),
        ('estornado',           'Estornado'),
    ]

    FORMAS_PAGAMENTO = [
        ('cartao_credito', 'Cartão de Crédito'),
        ('pix',            'Pix'),
        ('boleto',         'Boleto'),
    ]

    GATEWAYS = [
        ('pagseguro', 'PagSeguro'),
        ('stone',     'Stone'),
    ]

    numero = models.CharField('Número', max_length=20, unique=True, default=gerar_numero_pedido, db_index=True)
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 related_name='pedidos', null=True, blank=True)

    # Dados do comprador (copiados no momento do pedido — não mudar se cliente editar perfil)
    nome_completo = models.CharField('Nome completo', max_length=240)
    email = models.EmailField('E-mail', max_length=254)
    cpf = models.CharField('CPF', max_length=11)
    telefone = models.CharField('Telefone', max_length=20, blank=True)

    # Endereço de entrega (copiado no momento do pedido)
    cep_entrega = models.CharField('CEP', max_length=8)
    logradouro = models.CharField('Logradouro', max_length=200)
    numero_entrega = models.CharField('Número', max_length=20)
    complemento = models.CharField('Complemento', max_length=100, blank=True)
    bairro = models.CharField('Bairro', max_length=100)
    cidade = models.CharField('Cidade', max_length=100)
    estado = models.CharField('Estado', max_length=2)

    # Cupom / vendedor
    cupom = models.ForeignKey(
        'Cupom', on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos',
        verbose_name='Cupom',
    )
    cupom_codigo = models.CharField('Código do cupom', max_length=50, blank=True,
                                     help_text='Copiado no momento da compra')
    codigo_vendedor = models.ForeignKey(
        'CodigoVendedor', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedidos', verbose_name='Código do vendedor',
    )
    codigo_vendedor_str = models.CharField('Código do vendedor', max_length=20, blank=True,
                                            help_text='Copiado no momento da compra')

    # Valores
    subtotal = models.DecimalField('Subtotal', max_digits=10, decimal_places=2, default=0)
    desconto = models.DecimalField('Desconto', max_digits=10, decimal_places=2, default=0)
    frete = models.DecimalField('Frete', max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField('Total', max_digits=10, decimal_places=2, default=0)

    # Pagamento
    status = models.CharField('Status', max_length=30, choices=STATUS, default='aguardando_pagamento', db_index=True)
    forma_pagamento = models.CharField('Forma de pagamento', max_length=20, choices=FORMAS_PAGAMENTO, blank=True)
    gateway = models.CharField('Gateway', max_length=15, choices=GATEWAYS, blank=True)
    gateway_id = models.CharField('ID no gateway', max_length=100, blank=True)
    parcelas = models.PositiveSmallIntegerField('Parcelas', default=1)

    # Entrega
    codigo_rastreio = models.CharField('Código de rastreio', max_length=50, blank=True)
    transportadora = models.CharField('Transportadora', max_length=80, blank=True)
    # Serviço Melhor Envio escolhido no checkout — usado para montar
    # transporte.volumes no payload do Bling (modalidade PAC=1 / SEDEX=2)
    frete_servico_id = models.CharField('ID serviço frete', max_length=20, blank=True)
    frete_prazo_dias = models.PositiveSmallIntegerField('Prazo frete (dias)', null=True, blank=True)

    # Integração Bling
    bling_pedido_id = models.CharField('ID pedido Bling', max_length=50, blank=True)
    bling_nfe_id = models.CharField('ID NF-e Bling', max_length=50, blank=True)
    nfe_chave = models.CharField('Chave NF-e', max_length=50, blank=True)

    observacao_cliente = models.TextField('Observação do cliente', max_length=300, blank=True)
    observacao_interna = models.TextField('Observação interna', max_length=500, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-criado_em']

    def __str__(self):
        return f'Pedido {self.numero} — {self.nome_completo}'

    def clean(self):
        # Sanitiza campos que o cliente pode ter preenchido
        self.nome_completo = sanitize_text(self.nome_completo, max_length=240)
        self.logradouro = sanitize_address(self.logradouro)
        self.numero_entrega = sanitize_text(self.numero_entrega, max_length=20)
        self.complemento = sanitize_text(self.complemento, max_length=100)
        self.bairro = sanitize_text(self.bairro, max_length=100)
        self.cidade = sanitize_text(self.cidade, max_length=100)
        self.telefone = sanitize_phone(self.telefone)
        self.observacao_cliente = sanitize_text(self.observacao_cliente, max_length=300)

    @property
    def pode_cancelar(self):
        return self.status in ('aguardando_pagamento',)

    # ── Display e timeline pro cliente ───────────────────────────────────────
    STATUS_PUBLICO = {
        'aguardando_pagamento': 'Aguardando pagamento',
        'pagamento_confirmado': 'Em separação',
        'em_separacao':         'Em separação',
        'enviado':              'Enviado',
        'entregue':             'Entregue',
        'cancelado':            'Cancelado',
        'estornado':            'Estornado',
    }

    @property
    def status_publico(self):
        """Display amigável do status pro cliente (mais simples que o interno)."""
        return self.STATUS_PUBLICO.get(self.status, self.get_status_display())

    def _data_primeira_transicao_para(self, status):
        h = self.historico.filter(status_novo=status).order_by('criado_em').first()
        return h.criado_em if h else None

    @property
    def data_pago(self):
        return self._data_primeira_transicao_para('pagamento_confirmado')

    @property
    def data_envio(self):
        return self._data_primeira_transicao_para('enviado')

    @property
    def data_entrega(self):
        return self._data_primeira_transicao_para('entregue')

    @property
    def data_cancelamento(self):
        return self._data_primeira_transicao_para('cancelado')

    @property
    def pode_confirmar_entrega(self):
        """Cliente pode marcar como entregue se já foi enviado."""
        return self.status == 'enviado'

    @property
    def link_rastreio(self):
        """URL para rastreamento via linkcorreios.com.br."""
        if not self.codigo_rastreio:
            return ''
        return f'https://www.linkcorreios.com.br/?id={self.codigo_rastreio}'

    def calcular_total(self):
        self.total = self.subtotal - self.desconto + self.frete
        return self.total


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT)
    variacao = models.ForeignKey('produtos.Variacao', on_delete=models.PROTECT, null=True, blank=True)

    # Dados copiados no momento da compra (produto pode mudar de preço depois)
    nome_produto = models.CharField('Produto', max_length=200)
    sku = models.CharField('SKU', max_length=80, blank=True)
    variacao_desc = models.CharField('Variação', max_length=100, blank=True)
    preco_unitario = models.DecimalField('Preço unitário', max_digits=10, decimal_places=2)
    quantidade = models.PositiveIntegerField('Quantidade', default=1)
    subtotal = models.DecimalField('Subtotal', max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Item do pedido'
        verbose_name_plural = 'Itens do pedido'

    def __str__(self):
        return f'{self.quantidade}x {self.nome_produto}'

    def save(self, *args, **kwargs):
        self.subtotal = self.preco_unitario * self.quantidade
        super().save(*args, **kwargs)


class HistoricoPedido(models.Model):
    """Log de todas as mudanças de status do pedido."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='historico')
    status_anterior = models.CharField(max_length=30, blank=True)
    status_novo = models.CharField(max_length=30)
    observacao = models.CharField(max_length=300, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico do pedido'
        verbose_name_plural = 'Histórico dos pedidos'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.pedido.numero}: {self.status_anterior} → {self.status_novo}'
