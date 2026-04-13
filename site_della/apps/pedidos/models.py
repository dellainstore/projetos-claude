import uuid
from django.db import models
from django.conf import settings
from apps.core_utils.sanitize import sanitize_text, sanitize_address, sanitize_phone


def gerar_numero_pedido():
    """Gera número legível: DI-2024-XXXX"""
    from django.utils import timezone
    ano = timezone.now().year
    aleatorio = uuid.uuid4().hex[:6].upper()
    return f'DI-{ano}-{aleatorio}'


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
