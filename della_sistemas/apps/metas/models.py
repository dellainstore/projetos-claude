from django.db import models


class MetaFuncionario(models.Model):
    """Meta individual mensal por colaborador (vendedor). O cadastro do colaborador
    é único, no módulo RH; aqui só vinculamos a meta a ele."""

    colaborador = models.ForeignKey(
        "rh.Colaborador",
        on_delete=models.CASCADE,
        related_name="metas",
        verbose_name="Colaborador",
    )
    ano = models.IntegerField(verbose_name="Ano")
    mes = models.IntegerField(
        verbose_name="Mes",
        choices=[(i, i) for i in range(1, 13)],
    )
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Meta (R$)")

    class Meta:
        verbose_name = "Meta Individual"
        verbose_name_plural = "Metas Individuais"
        unique_together = [("colaborador", "ano", "mes")]
        ordering = ["-ano", "-mes", "colaborador__nome"]

    def __str__(self) -> str:
        return f"{self.colaborador.nome} — {self.mes:02d}/{self.ano} — R$ {self.valor:,.2f}"


class MetaCanal(models.Model):
    """Meta mensal por canal de venda."""

    CANAL_CHOICES = [
        ("show_room_sp", "Show Room SP"),
        ("anaca", "Anaca SP"),
        ("atacado", "Atacado"),
        ("site_instagram", "Instagram / Site"),
    ]

    canal = models.CharField(
        max_length=50,
        choices=CANAL_CHOICES,
        verbose_name="Canal",
    )
    ano = models.IntegerField(verbose_name="Ano")
    mes = models.IntegerField(
        verbose_name="Mes",
        choices=[(i, i) for i in range(1, 13)],
    )
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Meta (R$)")

    class Meta:
        verbose_name = "Meta de Canal"
        verbose_name_plural = "Metas de Canal"
        unique_together = [("canal", "ano", "mes")]
        ordering = ["-ano", "-mes", "canal"]

    def __str__(self) -> str:
        return f"{self.get_canal_display()} — {self.mes:02d}/{self.ano} — R$ {self.valor:,.2f}"
