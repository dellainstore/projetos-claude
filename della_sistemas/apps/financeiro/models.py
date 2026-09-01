"""Módulo financeiro — submenu "Private Label".

Lançamento 100% manual (sem integração com Bling). Ver o plano aprovado em
`/home/neto/.claude/plans/cozy-sparking-forest.md` para o desenho completo
(fluxos, fórmulas, estratégia de recorrência, constraints).

Convenções deste app:
- Todo valor monetário é `DecimalField(max_digits=12, decimal_places=2)`,
  nunca float.
- `estado_estrutural` é persistido e só muda por mutação real (baixa,
  estorno, cancelamento). `situacao_temporal` (vencido/pendente/previsto)
  NUNCA é persistida — é sempre calculada na hora a partir de hoje, para não
  poder ficar desatualizada (ver `situacao_temporal()` abaixo).
- `MovimentoConta` é o razão único (ledger append-only) de onde o saldo de
  cada `ContaBancaria` é calculado — nunca um campo de saldo editável.
- Operações compostas (baixa, transferência, estorno, cancelamento, ajuste)
  são implementadas em `services/private_label/`, sempre dentro de
  `transaction.atomic()` — os models aqui só expõem estrutura e cálculos de
  leitura (properties), não mutação composta.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

# ─────────────────────────────────────────────────────────────────────────
# Choices compartilhados
# ─────────────────────────────────────────────────────────────────────────

ESTADO_ABERTO = "aberto"
ESTADO_PARCIAL = "parcial"
ESTADO_QUITADO = "quitado"
ESTADO_CANCELADO = "cancelado"

ESTADO_ESTRUTURAL_CHOICES = [
    (ESTADO_ABERTO, "Aberto"),
    (ESTADO_PARCIAL, "Parcial"),
    (ESTADO_QUITADO, "Quitado"),
    (ESTADO_CANCELADO, "Cancelado"),
]

TIPO_LANCAMENTO_CHOICES = [
    ("receita", "Receita"),
    ("despesa", "Despesa"),
]

TIPOS_SAIDA = {"despesa"}
TIPOS_ENTRADA = {"receita"}


def sinal_movimento(tipo: str) -> int:
    """-1 para despesa (saída), +1 para receita (entrada). Usado ao criar o
    MovimentoConta de uma baixa."""
    return -1 if tipo in TIPOS_SAIDA else 1


def rotulo_situacao(tipo: str, situacao: str) -> str:
    """Rótulo de status ciente do tipo — pedido do dono (2026-09-02): nada
    de "conta a pagar" separado de "despesa" (é a mesma coisa, só muda se
    já foi baixado ou não). "Pendente"/"previsto" viram um único "A pagar"/
    "A receber"; "quitado" vira "Pago"/"Recebido"."""
    if situacao == "cancelado":
        return "Cancelado"
    if situacao == "vencido":
        return "Vencido"
    if situacao == "parcial":
        return "Parcial"
    if situacao == "quitado":
        return "Pago" if tipo == "despesa" else "Recebido"
    return "A pagar" if tipo == "despesa" else "A receber"

NATUREZA_CHOICES = [
    ("receita", "Receita"),
    ("deducao", "Dedução / imposto sobre venda"),
    ("custo", "Custo direto"),
    ("despesa_operacional", "Despesa operacional"),
    ("receita_financeira", "Receita financeira"),
    ("despesa_financeira", "Despesa financeira"),
    ("fora_do_dre", "Fora do DRE"),
]

# Quais naturezas de categoria aparecem pra cada tipo de lançamento — usado
# no filtro do formulário (JS) E validado de novo no servidor (nunca confia
# só no frontend). "Dedução" entra do lado da despesa porque, na prática,
# é dinheiro saindo (imposto sobre venda), mesmo classificada à parte no DRE.
NATUREZAS_DESPESA = {"custo", "despesa_operacional", "despesa_financeira", "deducao"}
NATUREZAS_RECEITA = {"receita", "receita_financeira"}


def naturezas_permitidas(tipo: str) -> set[str]:
    return NATUREZAS_DESPESA if tipo == "despesa" else NATUREZAS_RECEITA

FREQUENCIA_CHOICES = [
    ("semanal", "Semanal"),
    ("mensal", "Mensal"),
    ("trimestral", "Trimestral"),
    ("semestral", "Semestral"),
    ("anual", "Anual"),
]


def situacao_temporal(estado: str, data_vencimento, saldo_restante: Decimal, hoje=None) -> str:
    """Calcula a situação temporal (vencido/pendente/previsto/quitado/
    cancelado) SEMPRE na hora, a partir do estado estrutural persistido +
    data de hoje. Nunca é salva em banco — ver docstring do módulo."""
    hoje = hoje or timezone.localdate()
    if estado == ESTADO_CANCELADO:
        return "cancelado"
    if estado == ESTADO_QUITADO:
        return "quitado"
    # aberto ou parcial:
    if data_vencimento and data_vencimento < hoje and saldo_restante and saldo_restante > 0:
        return "vencido"
    if data_vencimento == hoje:
        return "pendente"
    return "previsto"


def derivar_estado_lancamento(estados_parcelas: list[str]) -> str:
    """Deriva o estado estrutural do lançamento a partir do estado de todas
    as suas parcelas. Chamada pelo service após qualquer baixa/estorno."""
    if not estados_parcelas:
        return ESTADO_ABERTO
    unicos = set(estados_parcelas)
    if unicos == {ESTADO_CANCELADO}:
        return ESTADO_CANCELADO
    # cancelada isolada não conta pro agregado (parcela cancelada = fora do jogo)
    ativos = [e for e in estados_parcelas if e != ESTADO_CANCELADO] or list(estados_parcelas)
    if all(e == ESTADO_QUITADO for e in ativos):
        return ESTADO_QUITADO
    if all(e == ESTADO_ABERTO for e in ativos):
        return ESTADO_ABERTO
    return ESTADO_PARCIAL


def caminho_anexo_financeiro(instance, filename: str) -> str:
    """Nome no disco sempre randomizado — nome original só fica no banco
    (`AnexoFinanceiro.nome_original`), nunca no path. Ver plano, seção 15."""
    extensao = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    nome = uuid.uuid4().hex + (f".{extensao}" if extensao else "")
    hoje = timezone.localdate()
    return f"financeiro_privatelabel/anexos/{hoje:%Y/%m}/{nome}"


# ─────────────────────────────────────────────────────────────────────────
# Operação financeira — substitui "Empresa"/tenant (ver plano, seção 1.1)
# ─────────────────────────────────────────────────────────────────────────

class OperacaoFinanceira(models.Model):
    """Uma operação/conta segregada dentro do mesmo CNPJ (hoje só existe
    "Private Label"). NÃO é empresa/tenant — é só o rótulo que agrupa as
    entidades financeiras abaixo, pensado para permitir uma 2ª operação no
    futuro sem duplicar o módulo. Enquanto houver 1 só, ela é resolvida
    automaticamente (`services/private_label/operacao.py`) e não aparece em
    formulário nenhum."""

    nome = models.CharField(max_length=120)
    codigo = models.SlugField(max_length=60, unique=True)
    status = models.CharField(
        max_length=10,
        choices=[("ativa", "Ativa"), ("inativa", "Inativa")],
        default="ativa",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Operação Financeira"
        verbose_name_plural = "Operações Financeiras"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class ContaBancaria(models.Model):
    TIPO_CHOICES = [
        ("corrente", "Conta Corrente"),
        ("poupanca", "Poupança"),
        ("carteira_digital", "Carteira Digital"),
        ("caixa", "Caixa / Dinheiro"),
    ]

    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="contas")
    nome = models.CharField(max_length=120, verbose_name="Nome da conta")
    banco = models.CharField(max_length=120, blank=True)
    tipo_conta = models.CharField(max_length=20, choices=TIPO_CHOICES, default="corrente")
    agencia = models.CharField(max_length=20, blank=True)
    conta_mascarada = models.CharField(max_length=30, blank=True, verbose_name="Conta (mascarada)")
    cor = models.CharField(max_length=7, default="#c9a96e", verbose_name="Cor")
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    data_saldo_inicial = models.DateField()
    ativa = models.BooleanField(default=True)
    incluir_consolidado = models.BooleanField(default=True, verbose_name="Incluir no saldo consolidado")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="contas_bancarias_criadas",
    )

    class Meta:
        verbose_name = "Conta Bancária"
        verbose_name_plural = "Contas Bancárias"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome

    def saldo_atual(self) -> Decimal:
        """Saldo = saldo_inicial + soma dos movimentos confirmados (ledger).
        NUNCA um campo editável — ver `MovimentoConta`."""
        total = self.movimentos.aggregate(total=models.Sum("valor"))["total"] or Decimal("0.00")
        return self.saldo_inicial + total


class CategoriaFinanceira(models.Model):
    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="categorias")
    nome = models.CharField(max_length=120)
    categoria_pai = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="subcategorias",
    )
    natureza = models.CharField(max_length=25, choices=NATUREZA_CHOICES)
    icone = models.CharField(max_length=10, blank=True, help_text="Glifo/emoji — sem lib de ícone nova")
    cor = models.CharField(max_length=7, default="#c9a96e")
    ordem = models.PositiveIntegerField(default=0)
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Categoria Financeira"
        verbose_name_plural = "Categorias Financeiras"
        ordering = ["ordem", "nome"]
        constraints = [
            models.CheckConstraint(
                check=Q(natureza__in=[c[0] for c in NATUREZA_CHOICES]),
                name="categoria_financeira_natureza_valida",
            ),
        ]

    def __str__(self) -> str:
        if self.categoria_pai_id:
            return f"{self.categoria_pai.nome} › {self.nome}"
        return self.nome

    @property
    def entra_dre(self) -> bool:
        return self.natureza != "fora_do_dre"


class CentroCusto(models.Model):
    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="centros_custo")
    nome = models.CharField(max_length=120)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Centro de Custo"
        verbose_name_plural = "Centros de Custo"
        ordering = ["ordem", "nome"]

    def __str__(self) -> str:
        return self.nome


class ContatoFinanceiro(models.Model):
    TIPO_CHOICES = [
        ("cliente", "Cliente"),
        ("fornecedor", "Fornecedor"),
        ("ambos", "Cliente e Fornecedor"),
    ]

    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="contatos")
    nome = models.CharField(max_length=160)
    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES, default="fornecedor")
    documento = models.CharField(max_length=20, blank=True, verbose_name="CPF/CNPJ")
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Contato Financeiro"
        verbose_name_plural = "Contatos Financeiros"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class FormaPagamento(models.Model):
    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="formas_pagamento")
    nome = models.CharField(max_length=60)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"
        ordering = ["ordem", "nome"]

    def __str__(self) -> str:
        return self.nome


class TagFinanceira(models.Model):
    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="tags")
    nome = models.CharField(max_length=60)

    class Meta:
        verbose_name = "Tag Financeira"
        verbose_name_plural = "Tags Financeiras"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["operacao", "nome"], name="tag_financeira_unica_por_operacao"),
        ]

    def __str__(self) -> str:
        return self.nome


# ─────────────────────────────────────────────────────────────────────────
# Lançamentos, parcelas e baixas
# ─────────────────────────────────────────────────────────────────────────

class LancamentoFinanceiro(models.Model):
    """SEM `data_pagamento` — datas efetivas vêm sempre das `Baixa`s (ver
    plano, seção 8). `estado_estrutural` é cache atualizado só por mutação
    real; `situacao_temporal` (vencido etc.) nunca é persistida."""

    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="lancamentos")
    tipo = models.CharField(max_length=20, choices=TIPO_LANCAMENTO_CHOICES)
    descricao = models.CharField(max_length=200)
    contato = models.ForeignKey(
        ContatoFinanceiro, on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos",
    )
    categoria = models.ForeignKey(
        CategoriaFinanceira, on_delete=models.PROTECT, related_name="lancamentos",
    )
    centro_custo = models.ForeignKey(
        CentroCusto, on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos",
    )
    conta_prevista = models.ForeignKey(
        ContaBancaria, on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos_previstos",
        help_text="Opcional — conta sugerida na baixa. A conta real fica em cada Baixa.",
    )
    valor_original = models.DecimalField(max_digits=12, decimal_places=2)
    data_competencia = models.DateField()
    data_vencimento = models.DateField()
    forma_pagamento = models.ForeignKey(
        FormaPagamento, on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos",
    )
    numero_documento = models.CharField(max_length=60, blank=True)
    observacoes = models.TextField(blank=True)
    tags = models.ManyToManyField(TagFinanceira, blank=True, related_name="lancamentos")
    estado_estrutural = models.CharField(
        max_length=10, choices=ESTADO_ESTRUTURAL_CHOICES, default=ESTADO_ABERTO,
    )
    cancelado_em = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lancamentos_cancelados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lancamentos_criados",
    )

    class Meta:
        verbose_name = "Lançamento Financeiro"
        verbose_name_plural = "Lançamentos Financeiros"
        ordering = ["-data_vencimento", "-id"]
        indexes = [
            models.Index(fields=["operacao", "data_competencia"]),
            models.Index(fields=["operacao", "data_vencimento"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(valor_original__gt=0), name="lancamento_valor_original_positivo"),
        ]

    def __str__(self) -> str:
        return f"{self.descricao} — R$ {self.valor_original}"

    # ── cálculos (leitura) ──────────────────────────────────────────────
    @property
    def saldo_restante(self) -> Decimal:
        total = Decimal("0.00")
        for parcela in self.parcelas.all():
            total += parcela.saldo_restante
        return total

    @property
    def data_primeira_baixa(self):
        baixa = Baixa.objects.filter(
            parcela__lancamento=self, estornada=False,
        ).order_by("data", "id").first()
        return baixa.data if baixa else None

    @property
    def data_ultima_baixa(self):
        baixa = Baixa.objects.filter(
            parcela__lancamento=self, estornada=False,
        ).order_by("-data", "-id").first()
        return baixa.data if baixa else None

    @property
    def data_quitacao(self):
        """Data da baixa cujo acumulado (em ordem cronológica) fez a soma de
        `valor_principal` atingir o valor original pela primeira vez."""
        if self.estado_estrutural != ESTADO_QUITADO:
            return None
        baixas = Baixa.objects.filter(
            parcela__lancamento=self, estornada=False,
        ).order_by("data", "id")
        acumulado = Decimal("0.00")
        for baixa in baixas:
            acumulado += baixa.valor_principal
            if acumulado >= self.valor_original:
                return baixa.data
        return self.data_ultima_baixa

    def situacao_temporal(self, hoje=None) -> str:
        """Agrega a situação temporal de todas as parcelas: se qualquer uma
        estiver vencida (e o lançamento não estiver quitado/cancelado), o
        lançamento aparece como vencido."""
        hoje = hoje or timezone.localdate()
        if self.estado_estrutural == ESTADO_CANCELADO:
            return "cancelado"
        if self.estado_estrutural == ESTADO_QUITADO:
            return "quitado"
        situacoes = [p.situacao_temporal(hoje) for p in self.parcelas.all()]
        if "vencido" in situacoes:
            return "vencido"
        if "pendente" in situacoes:
            return "pendente"
        return "previsto"

    def recalcular_estado(self, salvar: bool = True) -> str:
        """Deriva `estado_estrutural` a partir das parcelas. Chamado pelo
        service sempre dentro da mesma `transaction.atomic()` de uma
        baixa/estorno/cancelamento."""
        estados = list(self.parcelas.values_list("estado_estrutural", flat=True))
        novo_estado = derivar_estado_lancamento(estados)
        if novo_estado != self.estado_estrutural:
            self.estado_estrutural = novo_estado
            if salvar:
                self.save(update_fields=["estado_estrutural", "atualizado_em"])
        return novo_estado


class Parcela(models.Model):
    lancamento = models.ForeignKey(LancamentoFinanceiro, on_delete=models.CASCADE, related_name="parcelas")
    numero = models.PositiveIntegerField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    data_vencimento = models.DateField()
    # Conta PREVISTA desta parcela específica — pedido do dono (2026-09-02):
    # "quando entrei na parcela 1 para ajustar só ela, mudou todas pra
    # Santander" — o campo antigo (LancamentoFinanceiro.conta_prevista) é
    # compartilhado por todas as parcelas do mesmo lançamento, então editar
    # numa mudava em todas. Cada parcela agora tem a sua própria (opcional
    # — cai no fallback do lançamento via `conta_prevista_efetiva` quando
    # em branco, então lançamentos antigos continuam funcionando).
    conta_prevista = models.ForeignKey(
        ContaBancaria, on_delete=models.PROTECT, null=True, blank=True, related_name="parcelas_previstas",
    )
    estado_estrutural = models.CharField(
        max_length=10, choices=ESTADO_ESTRUTURAL_CHOICES, default=ESTADO_ABERTO,
    )

    class Meta:
        verbose_name = "Parcela"
        verbose_name_plural = "Parcelas"
        ordering = ["lancamento", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["lancamento", "numero"], name="parcela_numero_unico_por_lancamento"),
            models.CheckConstraint(check=Q(valor__gt=0), name="parcela_valor_positivo"),
        ]
        indexes = [
            models.Index(fields=["data_vencimento", "estado_estrutural"]),
        ]

    def __str__(self) -> str:
        return f"{self.lancamento.descricao} — parcela {self.numero}"

    @property
    def conta_prevista_efetiva(self):
        """Conta prevista desta parcela, ou a do lançamento se a parcela
        não tiver uma própria definida (compatibilidade com lançamentos
        criados antes deste campo existir)."""
        return self.conta_prevista or self.lancamento.conta_prevista

    @property
    def valor_baixado_principal(self) -> Decimal:
        total = self.baixas.filter(estornada=False).aggregate(
            total=models.Sum("valor_principal"),
        )["total"]
        return total or Decimal("0.00")

    @property
    def saldo_restante(self) -> Decimal:
        if self.estado_estrutural == ESTADO_CANCELADO:
            return Decimal("0.00")
        return self.valor - self.valor_baixado_principal

    def situacao_temporal(self, hoje=None) -> str:
        return situacao_temporal(self.estado_estrutural, self.data_vencimento, self.saldo_restante, hoje)

    def recalcular_estado(self, salvar: bool = True) -> str:
        saldo = self.saldo_restante
        if self.estado_estrutural == ESTADO_CANCELADO:
            novo_estado = ESTADO_CANCELADO
        elif saldo <= 0:
            novo_estado = ESTADO_QUITADO
        elif self.valor_baixado_principal > 0:
            novo_estado = ESTADO_PARCIAL
        else:
            novo_estado = ESTADO_ABERTO
        if novo_estado != self.estado_estrutural:
            self.estado_estrutural = novo_estado
            if salvar:
                self.save(update_fields=["estado_estrutural"])
        return novo_estado


class Baixa(models.Model):
    """Imutável após criada — uma correção é feita estornando e lançando de
    novo (nunca em UPDATE), o que mantém o razão (`MovimentoConta`) sempre
    coerente com o que de fato aconteceu."""

    parcela = models.ForeignKey(Parcela, on_delete=models.PROTECT, related_name="baixas")
    valor_principal = models.DecimalField(max_digits=12, decimal_places=2)
    juros = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    multa = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    valor_movimentado = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="= valor_principal + juros + multa - desconto, calculado no service",
    )
    data = models.DateField()
    conta = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, related_name="baixas")
    forma_pagamento = models.ForeignKey(
        FormaPagamento, on_delete=models.PROTECT, null=True, blank=True, related_name="baixas",
    )
    observacao = models.TextField(blank=True)
    estornada = models.BooleanField(default=False)
    estornada_em = models.DateTimeField(null=True, blank=True)
    estornada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="baixas_estornadas",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="baixas_feitas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Baixa"
        verbose_name_plural = "Baixas"
        ordering = ["-data", "-id"]
        constraints = [
            models.CheckConstraint(check=Q(valor_principal__gt=0), name="baixa_valor_principal_positivo"),
            models.CheckConstraint(check=Q(juros__gte=0), name="baixa_juros_nao_negativo"),
            models.CheckConstraint(check=Q(multa__gte=0), name="baixa_multa_nao_negativa"),
            models.CheckConstraint(check=Q(desconto__gte=0), name="baixa_desconto_nao_negativo"),
            models.CheckConstraint(check=Q(valor_movimentado__gte=0), name="baixa_valor_movimentado_nao_negativo"),
        ]

    def __str__(self) -> str:
        return f"Baixa {self.id} — parcela {self.parcela_id} — R$ {self.valor_movimentado}"


class Transferencia(models.Model):
    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="transferencias")
    conta_origem = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, related_name="transferencias_saida")
    conta_destino = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, related_name="transferencias_entrada")
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    data = models.DateField()
    observacao = models.TextField(blank=True)
    estornada = models.BooleanField(default=False)
    estornada_em = models.DateTimeField(null=True, blank=True)
    estornada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transferencias_estornadas",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transferencias_criadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transferência"
        verbose_name_plural = "Transferências"
        ordering = ["-data", "-id"]
        constraints = [
            models.CheckConstraint(check=Q(valor__gt=0), name="transferencia_valor_positivo"),
            models.CheckConstraint(
                check=~Q(conta_origem=models.F("conta_destino")),
                name="transferencia_contas_diferentes",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.conta_origem} → {self.conta_destino} — R$ {self.valor}"


# ─────────────────────────────────────────────────────────────────────────
# Recorrências
# ─────────────────────────────────────────────────────────────────────────

class RegraRecorrencia(models.Model):
    """Estratégia sem depender de cron (ver plano, seção 12): regra com fim
    definido gera tudo de uma vez; sem fim mantém uma janela futura
    (`janela_meses`) estendida por comando idempotente + checagem lazy."""

    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="regras_recorrencia")
    descricao = models.CharField(max_length=200)
    tipo_lancamento = models.CharField(max_length=20, choices=TIPO_LANCAMENTO_CHOICES)
    categoria = models.ForeignKey(CategoriaFinanceira, on_delete=models.PROTECT, related_name="regras_recorrencia")
    centro_custo = models.ForeignKey(
        CentroCusto, on_delete=models.PROTECT, null=True, blank=True, related_name="regras_recorrencia",
    )
    conta_prevista = models.ForeignKey(
        ContaBancaria, on_delete=models.PROTECT, null=True, blank=True, related_name="regras_recorrencia",
    )
    contato = models.ForeignKey(
        ContatoFinanceiro, on_delete=models.PROTECT, null=True, blank=True, related_name="regras_recorrencia",
    )
    forma_pagamento = models.ForeignKey(
        FormaPagamento, on_delete=models.PROTECT, null=True, blank=True, related_name="regras_recorrencia",
    )
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    frequencia = models.CharField(max_length=12, choices=FREQUENCIA_CHOICES)
    data_inicial = models.DateField()
    data_final = models.DateField(null=True, blank=True)
    quantidade_ocorrencias = models.PositiveIntegerField(null=True, blank=True)
    janela_meses = models.PositiveIntegerField(default=12)
    janela_gerada_ate = models.DateField(null=True, blank=True)
    ultima_verificacao_em = models.DateTimeField(null=True, blank=True)
    ativa = models.BooleanField(default=True)
    pausada = models.BooleanField(default=False)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="regras_recorrencia_criadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Regra de Recorrência"
        verbose_name_plural = "Regras de Recorrência"
        ordering = ["descricao"]
        constraints = [
            models.CheckConstraint(check=Q(valor__gt=0), name="regra_recorrencia_valor_positivo"),
        ]

    def __str__(self) -> str:
        return self.descricao

    @property
    def tem_fim_definido(self) -> bool:
        return bool(self.data_final or self.quantidade_ocorrencias)


class OcorrenciaRecorrencia(models.Model):
    """Liga cada ocorrência gerada à sua regra+data. A unicidade é por
    `(regra, data_ocorrencia)` — não por ano/mês: frequência semanal gera
    várias ocorrências no mesmo mês, então "competência" teria que permitir
    repetição; a data exata nunca se repete para uma mesma regra, então é a
    chave certa para a UniqueConstraint (garantia final contra duplicidade,
    mesmo se o comando rodar 2x ou junto com a checagem lazy)."""

    regra = models.ForeignKey(RegraRecorrencia, on_delete=models.CASCADE, related_name="ocorrencias")
    data_ocorrencia = models.DateField()
    lancamento = models.OneToOneField(
        LancamentoFinanceiro, on_delete=models.CASCADE, related_name="ocorrencia_recorrencia",
    )

    class Meta:
        verbose_name = "Ocorrência de Recorrência"
        verbose_name_plural = "Ocorrências de Recorrência"
        ordering = ["-data_ocorrencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["regra", "data_ocorrencia"],
                name="ocorrencia_recorrencia_unica_por_data",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.regra.descricao} — {self.data_ocorrencia:%d/%m/%Y}"


# ─────────────────────────────────────────────────────────────────────────
# Ajuste de saldo, razão (ledger) e auditoria
# ─────────────────────────────────────────────────────────────────────────

class AjusteSaldo(models.Model):
    """Ação sensível — só usuário com `private_label.ajustar_saldo`. Sempre
    gera 1 `MovimentoConta` e 1 `LogAuditoriaFinanceiro`."""

    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="ajustes_saldo")
    conta = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, related_name="ajustes_saldo")
    valor = models.DecimalField(max_digits=12, decimal_places=2, help_text="Com sinal: positivo ou negativo")
    motivo = models.TextField()
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ajustes_saldo",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ajuste de Saldo"
        verbose_name_plural = "Ajustes de Saldo"
        ordering = ["-criado_em"]
        constraints = [
            models.CheckConstraint(check=~Q(valor=0), name="ajuste_saldo_valor_diferente_de_zero"),
        ]

    def __str__(self) -> str:
        return f"Ajuste {self.conta} — R$ {self.valor}"


class MovimentoConta(models.Model):
    """Razão único (ledger append-only) — única fonte do saldo realizado de
    cada conta. Nunca editado/deletado após criado; um estorno lança um novo
    movimento inverso. Exatamente 1 dos FKs de origem é não-nulo (ver
    CheckConstraint) — dá integridade referencial de verdade, ao contrário
    de um `origem_tipo`/`origem_id` genérico. `fatura_pagamento` e
    `investimento_transacao` serão adicionados nas migrations das Fases 1B
    e 2 (junto com a atualização desta constraint)."""

    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="movimentos")
    conta = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, related_name="movimentos")
    data = models.DateField()
    valor = models.DecimalField(max_digits=12, decimal_places=2, help_text="Com sinal: + entrada, - saída")
    evento_chave = models.CharField(max_length=80, unique=True)
    # FK simples (não OneToOne) em todas as origens: uma baixa/ajuste pode
    # gerar mais de 1 movimento ao longo do tempo (o original + um de
    # estorno, que nunca edita/apaga o primeiro — ledger append-only).
    baixa = models.ForeignKey(
        Baixa, on_delete=models.PROTECT, null=True, blank=True, related_name="movimentos",
    )
    transferencia = models.ForeignKey(
        Transferencia, on_delete=models.PROTECT, null=True, blank=True, related_name="movimentos",
    )
    ajuste = models.ForeignKey(
        AjusteSaldo, on_delete=models.PROTECT, null=True, blank=True, related_name="movimentos",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Movimento de Conta"
        verbose_name_plural = "Movimentos de Conta"
        ordering = ["-data", "-id"]
        indexes = [
            models.Index(fields=["conta", "data"]),
        ]
        constraints = [
            models.CheckConstraint(check=~Q(valor=0), name="movimento_conta_valor_diferente_de_zero"),
            models.CheckConstraint(
                check=(
                    (Q(baixa__isnull=False) & Q(transferencia__isnull=True) & Q(ajuste__isnull=True))
                    | (Q(baixa__isnull=True) & Q(transferencia__isnull=False) & Q(ajuste__isnull=True))
                    | (Q(baixa__isnull=True) & Q(transferencia__isnull=True) & Q(ajuste__isnull=False))
                ),
                name="movimento_conta_exatamente_uma_origem",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.conta} — {self.data} — R$ {self.valor}"


class LogAuditoriaFinanceiro(models.Model):
    """Log genérico reaproveitado por todas as entidades do módulo (evita
    duplicar uma tabela de log por model, seguindo o espírito do padrão do
    projeto — ex. `ComissaoLog`, `HistoricoDataPedido` — mas parametrizado)."""

    ACAO_CHOICES = [
        ("criacao", "Criação"),
        ("edicao", "Edição"),
        ("cancelamento", "Cancelamento"),
        ("baixa", "Baixa"),
        ("estorno", "Estorno"),
        ("ajuste", "Ajuste"),
        ("conciliacao", "Conciliação"),
        ("exclusao", "Exclusão definitiva"),
    ]

    operacao = models.ForeignKey(OperacaoFinanceira, on_delete=models.PROTECT, related_name="logs_auditoria")
    entidade = models.CharField(max_length=40)
    objeto_id = models.PositiveIntegerField()
    acao = models.CharField(max_length=15, choices=ACAO_CHOICES)
    campo = models.CharField(max_length=60, blank=True)
    valor_de = models.CharField(max_length=255, blank=True)
    valor_para = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs_financeiros",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de Auditoria Financeira"
        verbose_name_plural = "Logs de Auditoria Financeira"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["entidade", "objeto_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.entidade}#{self.objeto_id} — {self.acao}"


class AnexoFinanceiro(models.Model):
    """Nunca servido como mídia pública — download só pela view autenticada
    `financeiro:pl_anexo_download` (ver plano, seção 15). `MEDIA_ROOT` deste
    projeto não é exposto por Nginx/WhiteNoise hoje, então o arquivo já
    nasce fora de qualquer rota pública; a view é a única forma de acesso."""

    EXTENSOES_PERMITIDAS = ["pdf", "jpg", "jpeg", "png", "webp", "xlsx", "csv", "ofx"]
    TAMANHO_MAXIMO_MB = 10

    lancamento = models.ForeignKey(LancamentoFinanceiro, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to=caminho_anexo_financeiro)
    nome_original = models.CharField(max_length=255)
    tamanho = models.PositiveIntegerField(help_text="Bytes")
    tipo_mime = models.CharField(max_length=100, blank=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="anexos_financeiros",
    )
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Anexo Financeiro"
        verbose_name_plural = "Anexos Financeiros"
        ordering = ["-enviado_em"]

    def __str__(self) -> str:
        return self.nome_original
