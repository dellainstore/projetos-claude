from django.db import models


class Funcionario(models.Model):
    nome = models.CharField(max_length=100, verbose_name="Nome")
    nome_bling = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Nome no Bling",
        help_text="Nome exato como aparece como vendedora nos pedidos Bling (ex: TINA DIAS)",
    )
    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Funcionario"
        verbose_name_plural = "Funcionarios"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class MetaFuncionario(models.Model):
    """Meta individual mensal por funcionaria (a partir de jul/2026)."""

    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="metas",
        verbose_name="Funcionaria",
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
        unique_together = [("funcionario", "ano", "mes")]
        ordering = ["-ano", "-mes", "funcionario__nome"]

    def __str__(self) -> str:
        return f"{self.funcionario.nome} — {self.mes:02d}/{self.ano} — R$ {self.valor:,.2f}"


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
