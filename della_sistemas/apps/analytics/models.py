from django.db import models


class RelatorioSemanal(models.Model):
    """Registro de cada relatorio semanal gerado em PDF.

    Os campos de metricas + analise_ia sao a "memoria" do relatorio: cada
    semana nova le as semanas anteriores aqui para o Claude comparar
    tendencia em vez de comentar a semana como um evento isolado (ver
    management/commands/gerar_relatorio_semanal.py::_obter_historico).
    """

    semana_inicio = models.DateField('Inicio da semana')
    semana_fim    = models.DateField('Fim da semana')
    gerado_em     = models.DateTimeField('Gerado em', auto_now_add=True)
    arquivo       = models.CharField('Caminho do PDF (relativo a MEDIA_ROOT)', max_length=300)

    # Metricas-resumo da semana, gravadas junto com o PDF para servirem de
    # historico estruturado nas proximas geracoes (nao exigem reabrir o PDF).
    visitantes             = models.IntegerField('Visitantes unicos', default=0)
    paginas_vistas         = models.IntegerField('Paginas vistas', default=0)
    pedidos_pagos          = models.IntegerField('Vendas pagas', default=0)
    aguardando_pagamento   = models.IntegerField('Pedidos aguardando pagamento', default=0)
    itens_vendidos         = models.IntegerField('Itens vendidos', default=0)
    receita                = models.DecimalField('Receita total', max_digits=12, decimal_places=2, default=0)
    taxa_conversao         = models.DecimalField('Taxa de conversao (%)', max_digits=5, decimal_places=1, default=0)
    carrinhos_abandonados  = models.IntegerField('Carrinhos abandonados', default=0)
    checkouts_abandonados  = models.IntegerField('Checkouts abandonados', default=0)

    # Texto gerado pela IA nesta semana — reaproveitado como contexto de
    # continuidade (nao literal) na proxima geracao.
    analise_ia = models.TextField('Analise da IA', blank=True, default='')

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
    # Nome e codigo do anuncio/conjunto, quando a campanha esta etiquetada com
    # as macros da Meta. `utm_id` (codigo da campanha) e a chave estavel para
    # cruzar com o gasto declarado pela Meta: o nome muda ao renomear, o codigo
    # nunca. Capturado a partir de 2026-08-23 (migration analytics/0006 no
    # site_della), vazio para sessoes anteriores.
    utm_content = models.CharField(max_length=200, blank=True)
    utm_term = models.CharField(max_length=200, blank=True)
    utm_id = models.CharField(max_length=200, blank=True)
    # Click ids: usados como fallback de atribuicao quando nao ha utm_source
    # (clique de anuncio sem UTM ainda carrega fbclid/gclid).
    fbclid = models.CharField(max_length=300, blank=True)
    gclid = models.CharField(max_length=300, blank=True)
    dispositivo = models.CharField(max_length=10, blank=True)
    iniciada_em = models.DateTimeField()
    ultima_acao_em = models.DateTimeField()
    total_paginas = models.PositiveIntegerField(default=0)
    # Marcado na coleta (site_della) por comportamento de bot. O painel filtra
    # is_bot=False em todas as metricas para mostrar apenas pessoas reais.
    is_bot = models.BooleanField(default=False)
    ip_hash = models.CharField(max_length=64, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=2, blank=True)

    class Meta:
        app_label = 'analytics_site'
        db_table = 'analytics_sessaoanalytics'
        managed = False
        verbose_name = 'Sessao do Site'
        verbose_name_plural = 'Sessoes do Site'

    def __str__(self):
        return self.sessao_hash[:16]


class PedidoSite(models.Model):
    """Espelho somente-leitura de pedidos_pedido no banco della_site.

    Existe para o painel saber se um pedido foi PAGO. O evento
    `pedido_finalizado` do analytics e gravado na criacao do pedido, entao
    sozinho ele contaria PIX gerado e nao pago (ou pedido cancelado) como venda.
    """

    numero = models.CharField(max_length=20)
    status = models.CharField(max_length=30)
    forma_pagamento = models.CharField(max_length=20, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    criado_em = models.DateTimeField()

    # Quem comprou. `cliente_id` fica nulo em compra de convidada (checkout sem
    # cadastro), por isso "novos x recorrentes" casa por e-mail, nao pelo FK.
    cliente_id = models.BigIntegerField(null=True, blank=True)
    nome_completo = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)

    # Atribuicao gravada no proprio pedido. Vazia na maioria dos pedidos
    # anteriores a 2026-08-23 (o cookie do Safari expirava antes da compra, ver
    # apps/pedidos/views.py::_utms_da_sessao_analytics no site_della), por isso
    # o painel usa a origem da SESSAO como fonte principal e esta aqui como
    # complemento.
    utm_source = models.CharField(max_length=200, blank=True)
    utm_medium = models.CharField(max_length=200, blank=True)
    utm_campaign = models.CharField(max_length=200, blank=True)
    utm_content = models.CharField(max_length=200, blank=True)
    utm_id = models.CharField(max_length=200, blank=True)
    fbclid = models.CharField(max_length=300, blank=True)
    gclid = models.CharField(max_length=300, blank=True)

    class Meta:
        app_label = 'analytics_site'
        db_table = 'pedidos_pedido'
        managed = False
        verbose_name = 'Pedido do Site'
        verbose_name_plural = 'Pedidos do Site'

    def __str__(self):
        return f'{self.numero} ({self.status})'


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
