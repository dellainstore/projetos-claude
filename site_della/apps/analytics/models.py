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
    ('popup_saida_exibido',   'Popup de Saida Exibido'),
    ('pagamento_selecionado', 'Pagamento Selecionado'),
    ('pedido_finalizado',     'Pedido Finalizado'),
    ('pagamento_confirmado',  'Pagamento Confirmado'),
    ('wishlist_adicionado',   'Wishlist Adicionado'),
    ('cupom_aplicado',        'Cupom Aplicado'),
    ('cupom_invalido',        'Cupom Invalido'),
    ('link_bio_clicado',      'Link da Bio Clicado'),
]

TIPOS_VALIDOS = {t[0] for t in TIPOS_EVENTO}


class SessaoAnalytics(models.Model):
    sessao_hash    = models.CharField(max_length=64, unique=True, db_index=True)
    utm_source     = models.CharField(max_length=200, blank=True)
    utm_medium     = models.CharField(max_length=200, blank=True)
    utm_campaign   = models.CharField(max_length=200, blank=True)
    utm_content    = models.CharField(max_length=200, blank=True)
    utm_term       = models.CharField(max_length=200, blank=True)
    # Codigo da campanha na plataforma de anuncio ({{campaign.id}} da Meta).
    # Diferente de utm_campaign, que carrega o NOME e muda quando a campanha e
    # renomeada; o codigo nunca muda, e e por ele que o painel de Anuncios
    # cruza a visita com o gasto declarado pela Meta. O `Pedido` ja guardava
    # este campo desde o inicio, mas a sessao nao, entao a etiqueta chegava e
    # era descartada aqui.
    utm_id         = models.CharField(max_length=200, blank=True)
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
    # Deteccao de bot que falsifica User-Agent de navegador (o filtro de UA em
    # services.eh_bot so pega bots que se identificam). is_bot e marcado por
    # comportamento: volume anormal de paginas ou rajada de sessoes do mesmo IP.
    # O painel (della_sistemas) filtra is_bot=False. Flag, nao apaga: reversivel.
    is_bot         = models.BooleanField(default=False, db_index=True)
    # Hash salgado do IP (nunca o IP em texto). Usado so para detectar rajadas
    # ("mesmo IP criou N sessoes no mesmo minuto") -- pseudonimo, fim de seguranca.
    ip_hash        = models.CharField(max_length=64, blank=True, db_index=True)
    # Cidade/UF aproximadas resolvidas do IP via GeoLite2 (MaxMind) no momento
    # da criacao da sessao, antes do hash. O IP em si nunca e persistido.
    cidade         = models.CharField(max_length=100, blank=True)
    estado         = models.CharField(max_length=2, blank=True)

    class Meta:
        verbose_name = 'Sessao Analytics'
        verbose_name_plural = 'Sessoes Analytics'
        indexes = [
            models.Index(fields=['ultima_acao_em']),
            models.Index(fields=['iniciada_em']),
            models.Index(fields=['ip_hash', 'iniciada_em']),
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
