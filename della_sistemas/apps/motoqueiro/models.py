from django.conf import settings
from django.db import models


class SolicitacaoEntrega(models.Model):
    """Corrida de motoboy (Lalamove ou Loggi) solicitada por um colaborador
    através do painel. Só corridas realmente finalizadas (confirmadas na
    plataforma) entram aqui — uma cotação sozinha nunca vira registro."""

    PLATAFORMA_LALAMOVE = "lalamove"
    PLATAFORMA_LOGGI = "loggi"
    PLATAFORMA_CHOICES = [
        (PLATAFORMA_LALAMOVE, "Lalamove"),
        (PLATAFORMA_LOGGI, "Loggi"),
    ]

    STATUS_AGUARDANDO_COLETA = "aguardando_coleta"
    STATUS_NO_PERCURSO = "no_percurso"
    STATUS_ENTREGA_REALIZADA = "entrega_realizada"
    STATUS_PROBLEMA_ENTREGA = "problema_entrega"
    STATUS_PROBLEMA_COLETA = "problema_coleta"
    STATUS_CHOICES = [
        (STATUS_AGUARDANDO_COLETA, "Aguardando Coleta"),
        (STATUS_NO_PERCURSO, "No Percurso"),
        (STATUS_ENTREGA_REALIZADA, "Entrega Realizada"),
        (STATUS_PROBLEMA_ENTREGA, "Problema na Entrega"),
        (STATUS_PROBLEMA_COLETA, "Problema na Coleta"),
    ]
    STATUS_FINAIS = {STATUS_ENTREGA_REALIZADA, STATUS_PROBLEMA_ENTREGA, STATUS_PROBLEMA_COLETA}

    colaborador = models.ForeignKey(
        "rh.Colaborador",
        on_delete=models.PROTECT,
        related_name="solicitacoes_entrega",
        help_text="Quem pediu a corrida (não quem só aprovou/lançou).",
    )
    solicitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="solicitacoes_entrega_lancadas",
        help_text="Login que efetivamente confirmou o pedido no painel (pode ser diferente do colaborador, ex: financeiro lançando por outra pessoa).",
    )

    FINALIDADE_COMERCIAL = "comercial"
    FINALIDADE_PRODUCAO = "producao"
    FINALIDADE_CHOICES = [
        (FINALIDADE_COMERCIAL, "Comercial"),
        (FINALIDADE_PRODUCAO, "Produção"),
    ]

    plataforma = models.CharField(max_length=10, choices=PLATAFORMA_CHOICES, default=PLATAFORMA_LALAMOVE)
    veiculo = models.CharField(
        max_length=60, blank=True,
        help_text="Ex: LalaGo (moto sem baú), LalaPro (moto com baú) — qual tipo/veículo foi escolhido na cotação.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AGUARDANDO_COLETA)
    finalidade = models.CharField(
        max_length=10, choices=FINALIDADE_CHOICES, blank=True,
        help_text="Se o frete é de venda (comercial) ou de produção — escolhido na confirmação da corrida.",
    )

    endereco_retirada = models.CharField(max_length=255)
    endereco_entrega = models.CharField(max_length=255)
    complemento_retirada = models.CharField(max_length=100, blank=True, help_text="Bloco, apto, andar, ponto de referência.")
    complemento_entrega = models.CharField(max_length=100, blank=True, help_text="Bloco, apto, andar, ponto de referência.")
    lat_retirada = models.FloatField(null=True, blank=True)
    lng_retirada = models.FloatField(null=True, blank=True)
    lat_entrega = models.FloatField(null=True, blank=True)
    lng_entrega = models.FloatField(null=True, blank=True)
    remetente = models.CharField(max_length=120)
    destinatario = models.CharField(max_length=120)
    valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observacao = models.TextField(blank=True)

    # Integração Lalamove (order criado por nós via API — dá o order_id que
    # permite consultar/receber webhook de status depois)
    lalamove_order_id = models.CharField(max_length=64, blank=True, db_index=True)
    lalamove_quotation_id = models.CharField(max_length=64, blank=True)
    lalamove_status_raw = models.CharField(max_length=40, blank=True, help_text="Último status bruto recebido da Lalamove, antes de traduzir para STATUS_CHOICES.")
    lalamove_share_link = models.URLField(max_length=500, blank=True, help_text="Link de rastreio ao vivo (mapa + motoboy) que a Lalamove devolve ao criar o pedido.")

    # Integração Loggi (envio criado por nós via API — ver services/loggi.py).
    # ESQUELETO: campos existem mas o fluxo de Solicitar ainda não chama a
    # Loggi de verdade (faltam credenciais — ver
    # memory/project_loggi_integracao_motoqueiro.md).
    loggi_tracking_code = models.CharField(max_length=100, blank=True, db_index=True, help_text="Código de rastreio — usado para consultar status e cancelar.")
    loggi_key = models.CharField(max_length=100, blank=True, help_text="Identificador definitivo do pacote devolvido pela Loggi (loggiKey).")
    loggi_status_raw = models.CharField(max_length=40, blank=True, help_text="Último código de status bruto recebido da Loggi, antes de traduzir para STATUS_CHOICES.")
    loggi_label_url = models.URLField(max_length=500, blank=True, help_text="Link da etiqueta (PDF) gerada para a corrida.")

    criado_em = models.DateTimeField(auto_now_add=True, help_text="Data/hora do pedido.")
    atualizado_em = models.DateTimeField(auto_now=True)
    concluido_em = models.DateTimeField(null=True, blank=True, help_text="Quando chegou a um status final.")

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Solicitação de Entrega"
        verbose_name_plural = "Solicitações de Entrega"
        indexes = [
            models.Index(fields=["criado_em"]),
            models.Index(fields=["colaborador", "criado_em"]),
        ]

    def __str__(self):
        return f"{self.get_plataforma_display()} #{self.pk} — {self.colaborador.nome} ({self.get_status_display()})"

    @property
    def eh_status_final(self) -> bool:
        return self.status in self.STATUS_FINAIS


class MovimentoSaldoLalamove(models.Model):
    """Ledger append-only do saldo da carteira Lalamove — a API de parceiro
    não expõe endpoint de saldo (testado e confirmado: /v3/wallet, /balance,
    /account etc. todos 404), então controlamos manualmente por enquanto.
    O saldo atual NUNCA é um campo guardado direto — é sempre a soma dos
    lançamentos (mesmo padrão do Private Label: estado é derivado, nunca
    sobrescrito). Toda corrida confirmada pelo sistema gera um débito aqui
    automaticamente; créditos (recarga) e débitos avulsos (corrida pedida
    fora do sistema, direto no app/site do Lalamove) são lançados manualmente
    só por quem tem `motoqueiro.gerir_saldo` (hoje: só superadmin)."""

    TIPO_CREDITO = "credito"
    TIPO_DEBITO = "debito"
    TIPO_CHOICES = [
        (TIPO_CREDITO, "Crédito (recarga)"),
        (TIPO_DEBITO, "Débito (saída)"),
    ]

    ORIGEM_MANUAL = "manual"
    ORIGEM_CORRIDA = "corrida"
    ORIGEM_CHOICES = [
        (ORIGEM_MANUAL, "Lançamento manual"),
        (ORIGEM_CORRIDA, "Corrida solicitada pelo sistema"),
    ]

    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    origem = models.CharField(max_length=10, choices=ORIGEM_CHOICES, default=ORIGEM_MANUAL)
    valor = models.DecimalField(max_digits=10, decimal_places=2, help_text="Sempre positivo — o campo 'tipo' define a direção.")
    descricao = models.CharField(max_length=255, blank=True)
    solicitacao = models.ForeignKey(
        SolicitacaoEntrega, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="movimentos_saldo",
        help_text="Preenchido só quando origem=corrida (débito automático).",
    )
    lancado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Movimento de Saldo Lalamove"
        verbose_name_plural = "Movimentos de Saldo Lalamove"

    def __str__(self):
        sinal = "+" if self.tipo == self.TIPO_CREDITO else "-"
        return f"{sinal}R$ {self.valor} ({self.get_origem_display()})"

    @staticmethod
    def saldo_atual():
        from django.db.models import Sum, Case, When, F, DecimalField

        agregado = MovimentoSaldoLalamove.objects.aggregate(
            total=Sum(
                Case(
                    When(tipo=MovimentoSaldoLalamove.TIPO_CREDITO, then=F("valor")),
                    When(tipo=MovimentoSaldoLalamove.TIPO_DEBITO, then=-F("valor")),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
        )["total"]
        from decimal import Decimal
        return agregado or Decimal("0.00")


class SolicitacaoEntregaEvento(models.Model):
    """Log de cada mudança de status recebida (webhook) ou lançada manualmente
    — auditoria e depuração de payloads da Lalamove/Loggi."""

    solicitacao = models.ForeignKey(SolicitacaoEntrega, on_delete=models.CASCADE, related_name="eventos")
    status_anterior = models.CharField(max_length=20, blank=True)
    status_novo = models.CharField(max_length=20)
    status_raw = models.CharField(max_length=40, blank=True)
    origem = models.CharField(max_length=20, default="webhook", help_text="webhook | manual | polling")
    payload = models.JSONField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Evento de Entrega"
        verbose_name_plural = "Eventos de Entrega"
