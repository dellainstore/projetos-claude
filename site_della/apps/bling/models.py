from django.db import models


class BlingToken(models.Model):
    """Armazena os tokens OAuth do Bling (access + refresh)."""
    access_token = models.TextField('Access Token')
    refresh_token = models.TextField('Refresh Token')
    expira_em = models.DateTimeField('Expira em')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Token Bling'
        verbose_name_plural = 'Tokens Bling'

    def __str__(self):
        return f'Token Bling — expira em {self.expira_em}'

    @property
    def valido(self):
        from django.utils import timezone
        return timezone.now() < self.expira_em


class BlingLog(models.Model):
    """Log de todas as chamadas à API do Bling para diagnóstico."""
    TIPOS = [('pedido', 'Pedido'), ('nfe', 'NF-e'), ('estoque', 'Estoque'), ('produto', 'Produto')]

    tipo = models.CharField('Tipo', max_length=10, choices=TIPOS)
    pedido = models.ForeignKey('pedidos.Pedido', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='bling_logs')
    sucesso = models.BooleanField('Sucesso', default=False)
    payload_enviado = models.JSONField('Payload enviado', default=dict, blank=True)
    resposta = models.JSONField('Resposta', default=dict, blank=True)
    erro = models.TextField('Erro', blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico Bling'
        verbose_name_plural = 'Histórico Bling'
        ordering = ['-criado_em']

    def __str__(self):
        status = 'OK' if self.sucesso else 'ERRO'
        return f'[{status}] {self.get_tipo_display()} — {self.criado_em}'
