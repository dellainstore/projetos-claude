from decimal import Decimal

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
    STATUS_CANCELADO = "cancelado"
    STATUS_CHOICES = [
        (STATUS_AGUARDANDO_COLETA, "Aguardando Coleta"),
        (STATUS_NO_PERCURSO, "No Percurso"),
        (STATUS_ENTREGA_REALIZADA, "Entrega Realizada"),
        (STATUS_PROBLEMA_ENTREGA, "Problema na Entrega"),
        (STATUS_PROBLEMA_COLETA, "Problema na Coleta"),
        (STATUS_CANCELADO, "Cancelada"),
    ]
    STATUS_FINAIS = {
        STATUS_ENTREGA_REALIZADA, STATUS_PROBLEMA_ENTREGA, STATUS_PROBLEMA_COLETA,
        STATUS_CANCELADO,
    }

    # Degraus de taxa de prioridade (gorjeta pra achar motoboy mais rapido).
    # Na Lalamove cada valor SUBSTITUI o anterior, nao soma — entao subir de
    # R$ 3 pra R$ 5 deixa a prioridade em R$ 5, e o teto de R$ 10 aqui e o
    # teto do que a corrida pode custar a mais no total.
    PRIORIDADES = [Decimal("3.00"), Decimal("5.00"), Decimal("10.00")]

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
    lalamove_prioridade = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text="Taxa de prioridade em vigor (não é acumulada: o último valor substitui o anterior). Teto de R$ 10.",
    )

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

    @property
    def proxima_prioridade(self):
        """Proximo degrau de prioridade acima do que ja esta valendo.

        E' isto que trava o clique duplo: depois de aplicar R$ 3, o proximo
        degrau passa a ser R$ 5 — clicar de novo nunca repete o mesmo valor.
        Devolve None quando ja esta no teto de R$ 10.
        """
        for valor in self.PRIORIDADES:
            if valor > self.lalamove_prioridade:
                return valor
        return None

    @property
    def pode_priorizar(self) -> bool:
        """Se ainda da pra aumentar a prioridade.

        A Lalamove so aceita antes de um motoboy aceitar a corrida. O status
        local nao separa "procurando" de "motoboy a caminho" (os dois caem em
        aguardando_coleta), mas o status bruto separa — por isso a checagem e'
        no ASSIGNING_DRIVER. Registro antigo, sem status bruto, fica liberado
        e quem decide e' a API.
        """
        return (
            self.plataforma == self.PLATAFORMA_LALAMOVE
            and bool(self.lalamove_order_id)
            and self.status == self.STATUS_AGUARDANDO_COLETA
            and self.lalamove_status_raw in ("", "ASSIGNING_DRIVER")
            and self.proxima_prioridade is not None
        )

    @property
    def pode_cancelar(self) -> bool:
        """Se ainda da pra pedir cancelamento na plataforma.

        A Lalamove so aceita cancelar enquanto o pedido esta procurando
        motoboy (ASSIGNING_DRIVER) ou ate 5 min depois de casar com um
        (ON_GOING) — os dois caem em `aguardando_coleta` aqui. Depois disso
        responde 409 ERR_CANCELLATION_FORBIDDEN. Como a janela de 5 min nao
        da pra medir so com o status local, aqui e' apenas o filtro grosso
        que decide se o botao aparece; quem da a palavra final e' a API."""
        return (
            self.plataforma == self.PLATAFORMA_LALAMOVE
            and bool(self.lalamove_order_id)
            and self.status == self.STATUS_AGUARDANDO_COLETA
        )


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


class MonitoramentoCotacao(models.Model):
    """Fica cotando um trajeto de tempos em tempos (cron, ver
    services/monitoramento.py) até achar um preço igual ou menor que o alvo
    — aí avisa no Telegram. Nunca cria pedido sozinho: o clique em "Pedir
    agora" (no aviso ou na tela) sempre busca uma cotação nova na hora,
    porque a que disparou o alerta já pode ter expirado/mudado.

    Para de rodar sozinho em `expira_em`, sempre no mesmo dia em que foi
    criado (o campo do form é só um horário, tipo <input type=time> — não dá
    pra escolher outro dia, e o back-end também recusa hora já passada)."""

    VEICULO_QUALQUER = "qualquer"
    VEICULO_LALAGO = "LALAGO"
    VEICULO_LALAPRO = "LALAPRO"
    VEICULO_CHOICES = [
        (VEICULO_QUALQUER, "Qualquer um (o mais barato)"),
        (VEICULO_LALAGO, "LalaGo (moto, sem baú)"),
        (VEICULO_LALAPRO, "LalaPro (moto com baú)"),
    ]

    STATUS_ATIVO = "ativo"
    STATUS_ENCONTRADO = "encontrado"
    STATUS_EXPIRADO = "expirado"
    STATUS_CANCELADO = "cancelado"
    STATUS_CHOICES = [
        (STATUS_ATIVO, "Monitorando"),
        (STATUS_ENCONTRADO, "Preço encontrado"),
        (STATUS_EXPIRADO, "Expirado sem achar"),
        (STATUS_CANCELADO, "Cancelado"),
    ]

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="monitoramentos_cotacao",
    )

    endereco_retirada = models.CharField(max_length=255)
    complemento_retirada = models.CharField(max_length=100, blank=True)
    lat_retirada = models.FloatField()
    lng_retirada = models.FloatField()
    endereco_entrega = models.CharField(max_length=255)
    complemento_entrega = models.CharField(max_length=100, blank=True)
    lat_entrega = models.FloatField()
    lng_entrega = models.FloatField()

    veiculo = models.CharField(max_length=10, choices=VEICULO_CHOICES, default=VEICULO_QUALQUER)
    preco_alvo = models.DecimalField(max_digits=8, decimal_places=2, help_text="Avisa quando algum veículo cotar igual ou abaixo disso.")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ATIVO)

    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField(help_text="Horário (no mesmo dia da criação) em que o monitoramento para sozinho, mesmo sem achar o preço.")

    ultima_consulta_em = models.DateTimeField(null=True, blank=True)
    ultimo_preco_lalago = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    ultimo_preco_lalapro = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    ultimo_erro = models.CharField(max_length=255, blank=True, help_text="Última falha ao cotar (rota recusada, API fora etc.) — só informativo, não para o monitoramento.")

    encontrado_em = models.DateTimeField(null=True, blank=True)
    preco_encontrado = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    veiculo_encontrado = models.CharField(max_length=60, blank=True)

    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Monitoramento de Cotação"
        verbose_name_plural = "Monitoramentos de Cotação"
        indexes = [
            models.Index(fields=["status", "expira_em"]),
        ]

    def __str__(self):
        return f"Monitoramento #{self.pk} — {self.endereco_retirada} → {self.endereco_entrega} (alvo R$ {self.preco_alvo})"

    @property
    def pode_cancelar(self) -> bool:
        return self.status == self.STATUS_ATIVO

    @property
    def query_pedir_agora(self) -> str:
        """Querystring pro botão "Pedir agora" — import tardio pra não criar
        ciclo (o service importa este módulo lá em cima)."""
        from .services.monitoramento import montar_query_pedir_agora
        return montar_query_pedir_agora(self)


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
