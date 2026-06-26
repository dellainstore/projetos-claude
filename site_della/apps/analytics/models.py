from django.db import models

TIPOS_EVENTO = [
    ('pagina_vista',          'Pagina Vista'),
    ('produto_visualizado',   'Produto Visualizado'),
    ('lista_visualizada',     'Lista Visualizada'),
    ('busca_realizada',       'Busca Realizada'),
    ('produto_adicionado',    'Produto Adicionado'),
    ('produto_removido',      'Produto Removido'),
    ('carrinho_visualizado',  'Carrinho Visualizado'),
    ('checkout_iniciado',     'Checkout Iniciado'),
    ('pagamento_selecionado', 'Pagamento Selecionado'),
    ('pedido_finalizado',     'Pedido Finalizado'),
    ('pagamento_confirmado',  'Pagamento Confirmado'),
    ('wishlist_adicionado',   'Wishlist Adicionado'),
    ('cupom_aplicado',        'Cupom Aplicado'),
    ('cupom_invalido',        'Cupom Invalido'),
]

TIPOS_VALIDOS = {t[0] for t in TIPOS_EVENTO}


class SessaoAnalytics(models.Model):
    sessao_hash    = models.CharField(max_length=64, unique=True, db_index=True)
    utm_source     = models.CharField(max_length=200, blank=True)
    utm_medium     = models.CharField(max_length=200, blank=True)
    utm_campaign   = models.CharField(max_length=200, blank=True)
    utm_content    = models.CharField(max_length=200, blank=True)
    utm_term       = models.CharField(max_length=200, blank=True)
    gclid          = models.CharField(max_length=300, blank=True)
    fbclid         = models.CharField(max_length=300, blank=True)
    dispositivo    = models.CharField(max_length=10, choices=[
        ('desktop', 'Desktop'),
        ('mobile',  'Mobile'),
        ('tablet',  'Tablet'),
    ], default='desktop')
    iniciada_em    = models.DateTimeField(auto_now_add=True, db_index=True)
    ultima_acao_em = models.DateTimeField(auto_now=True, db_index=True)
    total_paginas  = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Sessao Analytics'
        verbose_name_plural = 'Sessoes Analytics'
        indexes = [
            models.Index(fields=['ultima_acao_em']),
            models.Index(fields=['iniciada_em']),
        ]

    def __str__(self):
        return f'{self.sessao_hash[:8]}... ({self.dispositivo})'


class EventoAnalytics(models.Model):
    sessao           = models.ForeignKey(
        SessaoAnalytics, on_delete=models.CASCADE,
        related_name='eventos', db_index=True,
    )
    tipo             = models.CharField(max_length=30, choices=TIPOS_EVENTO, db_index=True)
    ocorrido_em      = models.DateTimeField(auto_now_add=True, db_index=True)
    pagina_url       = models.CharField(max_length=500, blank=True)
    produto_slug     = models.CharField(max_length=200, blank=True, db_index=True)
    produto_nome     = models.CharField(max_length=200, blank=True)
    categoria_nome   = models.CharField(max_length=100, blank=True)
    variacao_desc    = models.CharField(max_length=100, blank=True)
    quantidade       = models.PositiveSmallIntegerField(null=True, blank=True)
    valor_unitario   = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor_total      = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pedido_numero    = models.CharField(max_length=20, blank=True)
    forma_pagamento  = models.CharField(max_length=20, blank=True)
    busca_termo      = models.CharField(max_length=200, blank=True)
    busca_resultados = models.PositiveSmallIntegerField(null=True, blank=True)
    metodo           = models.CharField(max_length=30, blank=True)
    cupom_codigo     = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'Evento Analytics'
        verbose_name_plural = 'Eventos Analytics'
        indexes = [
            models.Index(fields=['ocorrido_em']),
            models.Index(fields=['tipo', 'ocorrido_em']),
            models.Index(fields=['sessao', 'tipo']),
        ]
        ordering = ['-ocorrido_em']

    def __str__(self):
        return f'{self.tipo} ({self.ocorrido_em})'
