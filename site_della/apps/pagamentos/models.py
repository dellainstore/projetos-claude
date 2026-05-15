from django.db import models
from django.conf import settings


class CartaoSalvo(models.Model):
    """
    Cartão tokenizado pelo PagBank. Nunca armazena PAN, CVV ou data completa.
    Somente: token do gateway, 4 últimos dígitos, nome no cartão, bandeira e mês/ano de validade.
    """
    BANDEIRAS = [
        ('visa',       'Visa'),
        ('mastercard', 'Mastercard'),
        ('elo',        'Elo'),
        ('amex',       'American Express'),
        ('hipercard',  'Hipercard'),
        ('outro',      'Outro'),
    ]

    cliente          = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cartoes_salvos',
    )
    token_pagbank    = models.CharField('Token PagBank', max_length=100)
    ultimos_4        = models.CharField('Últimos 4 dígitos', max_length=4)
    nome_titular     = models.CharField('Nome no cartão', max_length=120)
    bandeira         = models.CharField('Bandeira', max_length=20, choices=BANDEIRAS, default='outro')
    mes_expiracao    = models.PositiveSmallIntegerField('Mês de validade')
    ano_expiracao    = models.PositiveSmallIntegerField('Ano de validade')
    ativo            = models.BooleanField('Ativo', default=True)
    criado_em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name         = 'Cartão salvo'
        verbose_name_plural  = 'Cartões salvos'
        ordering             = ['-criado_em']

    def __str__(self):
        return f'{self.get_bandeira_display()} **** {self.ultimos_4} — {self.cliente.email}'

    @property
    def esta_vencido(self) -> bool:
        from django.utils import timezone
        hoje = timezone.now().date()
        if self.ano_expiracao < hoje.year:
            return True
        if self.ano_expiracao == hoje.year and self.mes_expiracao < hoje.month:
            return True
        return False

    @property
    def descricao(self) -> str:
        return f'{self.get_bandeira_display()} **** {self.ultimos_4}'

    @property
    def validade_display(self) -> str:
        return f'{self.mes_expiracao:02d}/{self.ano_expiracao}'


class Pagamento(models.Model):
    STATUS = [
        ('pendente',   'Pendente'),
        ('aprovado',   'Aprovado'),
        ('recusado',   'Recusado'),
        ('cancelado',  'Cancelado'),
        ('estornado',  'Estornado'),
    ]

    pedido = models.ForeignKey('pedidos.Pedido', on_delete=models.PROTECT, related_name='pagamentos')
    gateway = models.CharField('Gateway', max_length=15)
    gateway_id = models.CharField('ID no gateway', max_length=150, blank=True, db_index=True)
    status = models.CharField('Status', max_length=15, choices=STATUS, default='pendente')
    valor = models.DecimalField('Valor', max_digits=10, decimal_places=2)
    forma = models.CharField('Forma', max_length=20)
    parcelas = models.PositiveSmallIntegerField('Parcelas', default=1)
    dados_retorno = models.JSONField('Dados retorno gateway', default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pagamento'
        verbose_name_plural = 'Pagamentos'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.gateway} — {self.pedido.numero} — {self.get_status_display()}'
