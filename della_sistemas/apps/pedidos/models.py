from django.conf import settings
from django.db import models


class PedidoBling(models.Model):
    bling_id         = models.BigIntegerField(unique=True, db_index=True)
    numero           = models.CharField(max_length=30, blank=True)
    data_pedido      = models.DateField()
    cliente_nome     = models.CharField(max_length=255, blank=True)
    valor_total      = models.DecimalField(max_digits=12, decimal_places=2)
    situacao_id      = models.IntegerField()
    situacao_nome    = models.CharField(max_length=100, blank=True)
    forma_pagamento  = models.CharField(max_length=200, blank=True)
    data_pagamento   = models.DateField(null=True, blank=True)
    is_permuta       = models.BooleanField(default=False)
    forma_corrigida  = models.CharField(max_length=200, blank=True)
    data_corrigida   = models.DateField(null=True, blank=True)
    atualizado_em    = models.DateTimeField(auto_now=True)
    criado_em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pedido Bling"
        verbose_name_plural = "Pedidos Bling"
        ordering = ["-data_pedido", "-bling_id"]

    def __str__(self):
        return f"Pedido #{self.numero or self.bling_id} — {self.cliente_nome}"


class HistoricoSituacaoPedido(models.Model):
    pedido                 = models.ForeignKey(
        PedidoBling, on_delete=models.CASCADE, related_name="historico_situacoes"
    )
    situacao_id            = models.IntegerField()
    situacao_nome          = models.CharField(max_length=100, blank=True)
    situacao_anterior_id   = models.IntegerField(null=True, blank=True)
    situacao_anterior_nome = models.CharField(max_length=100, blank=True)
    registrado_em          = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Histórico de Situação"
        verbose_name_plural = "Histórico de Situações"
        ordering = ["registrado_em"]

    def __str__(self):
        return f"{self.pedido} → {self.situacao_nome} em {self.registrado_em:%d/%m/%Y %H:%M}"


class HistoricoDataPedido(models.Model):
    pedido        = models.ForeignKey(
        PedidoBling, on_delete=models.CASCADE, related_name="historico_datas"
    )
    data_anterior = models.DateField()
    data_nova     = models.DateField()
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Histórico de Data"
        verbose_name_plural = "Histórico de Datas"
        ordering = ["registrado_em"]

    def __str__(self):
        return f"{self.pedido}: {self.data_anterior} → {self.data_nova}"


class ParcelaPedido(models.Model):
    pedido             = models.ForeignKey(
        PedidoBling, on_delete=models.CASCADE, related_name="parcelas"
    )
    numero             = models.IntegerField(default=1)
    valor              = models.DecimalField(max_digits=12, decimal_places=2)
    data_vencimento    = models.DateField(null=True, blank=True)
    forma_pagamento    = models.CharField(max_length=200, blank=True)
    forma_pagamento_id = models.IntegerField(null=True, blank=True)
    baixada            = models.BooleanField(default=False)
    baixada_por        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parcelas_baixadas",
    )
    baixada_em         = models.DateTimeField(null=True, blank=True)
    forma_efetiva      = models.CharField(max_length=200, blank=True)
    data_efetiva       = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name        = "Parcela de Pedido"
        verbose_name_plural = "Parcelas de Pedidos"
        ordering            = ["pedido", "numero"]
        unique_together     = [("pedido", "numero")]

    def __str__(self):
        return f"Parcela {self.numero} — Pedido #{self.pedido.numero}"


class BaixaPedido(models.Model):
    pedido         = models.OneToOneField(
        PedidoBling, on_delete=models.CASCADE, related_name="baixa"
    )
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    confirmado_em  = models.DateTimeField(auto_now_add=True)
    observacao     = models.TextField(blank=True)
    forma_efetiva  = models.CharField(max_length=200, blank=True)
    data_efetiva   = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Baixa de Pagamento"
        verbose_name_plural = "Baixas de Pagamento"
        ordering = ["-confirmado_em"]

    def __str__(self):
        return f"Baixa #{self.pedido.numero} por {self.confirmado_por}"
