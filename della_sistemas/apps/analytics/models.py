from django.db import models


class RelatorioSemanal(models.Model):
    """Registro de cada relatorio semanal gerado em PDF."""

    semana_inicio = models.DateField('Inicio da semana')
    semana_fim    = models.DateField('Fim da semana')
    gerado_em     = models.DateTimeField('Gerado em', auto_now_add=True)
    arquivo       = models.CharField('Caminho do PDF (relativo a MEDIA_ROOT)', max_length=300)

    class Meta:
        ordering        = ['-semana_inicio']
        verbose_name    = 'Relatorio Semanal'
        verbose_name_plural = 'Relatorios Semanais'

    def __str__(self):
        return f'Semana {self.semana_inicio} a {self.semana_fim}'


class SessaoSite(models.Model):
    """Espelho somente-leitura de analytics_sessaoanalytics no banco della_site."""

    sessao_hash = models.CharField(max_length=64)
    utm_source = models.CharField(max_length=200, blank=True)
    utm_medium = models.CharField(max_length=200, blank=True)
    utm_campaign = models.CharField(max_length=200, blank=True)
    # Click ids: usados como fallback de atribuicao quando nao ha utm_source
    # (clique de anuncio sem UTM ainda carrega fbclid/gclid).
    fbclid = models.CharField(max_length=300, blank=True)
    gclid = models.CharField(max_length=300, blank=True)
    dispositivo = models.CharField(max_length=10, blank=True)
    iniciada_em = models.DateTimeField()
    ultima_acao_em = models.DateTimeField()
    total_paginas = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = 'analytics_site'
        db_table = 'analytics_sessaoanalytics'
        managed = False
        verbose_name = 'Sessao do Site'
        verbose_name_plural = 'Sessoes do Site'

    def __str__(self):
        return self.sessao_hash[:16]


class EventoSite(models.Model):
    """Espelho somente-leitura de analytics_eventoanalytics no banco della_site."""

    sessao = models.ForeignKey(
        SessaoSite,
        on_delete=models.DO_NOTHING,
        related_name='eventos',
        db_constraint=False,
    )
    tipo = models.CharField(max_length=30)
    ocorrido_em = models.DateTimeField()
    pagina_url = models.CharField(max_length=500, blank=True)
    produto_slug = models.CharField(max_length=200, blank=True)
    produto_nome = models.CharField(max_length=200, blank=True)
    categoria_nome = models.CharField(max_length=100, blank=True)
    variacao_desc = models.CharField(max_length=100, blank=True)
    quantidade = models.PositiveSmallIntegerField(null=True, blank=True)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pedido_numero = models.CharField(max_length=20, blank=True)
    forma_pagamento = models.CharField(max_length=20, blank=True)
    busca_termo = models.CharField(max_length=200, blank=True)
    busca_resultados = models.SmallIntegerField(null=True, blank=True)
    metodo = models.CharField(max_length=30, blank=True)
    cupom_codigo = models.CharField(max_length=50, blank=True)

    class Meta:
        app_label = 'analytics_site'
        db_table = 'analytics_eventoanalytics'
        managed = False
        verbose_name = 'Evento do Site'
        verbose_name_plural = 'Eventos do Site'

    def __str__(self):
        return f'{self.tipo} ({self.ocorrido_em})'
