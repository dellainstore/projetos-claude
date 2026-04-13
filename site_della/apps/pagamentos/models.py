from django.db import models


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
