"""Modelos do módulo Recursos Humanos (D'ELLA Sistemas).

Cobre cadastro de colaboradores, salários/folha, comissão (sobre pedidos do
Bling), férias, benefícios (VT) e controle de ponto (banco de horas com geofence).
"""

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models


class Colaborador(models.Model):
    """Funcionário CLT ou sócio (pró-labore). ~6 registros no total."""

    TIPO_CHOICES = [
        ("clt", "CLT"),
        ("pro_labore", "PRÓ-LABORE"),
        ("sem_registro", "SEM REGISTRO"),
    ]

    nome              = models.CharField(max_length=120)
    cargo             = models.CharField(max_length=80, blank=True)
    tipo_contrato     = models.CharField(max_length=20, choices=TIPO_CHOICES, default="clt")
    usuario           = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="colaborador",
        help_text="Login usado para bater o próprio ponto.",
    )
    bling_vendedor_id = models.BigIntegerField(
        null=True, blank=True, db_index=True,
        help_text="ID do vendedor no Bling — usado para casar a comissão.",
    )
    data_admissao     = models.DateField(null=True, blank=True)
    salario_base      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    recebe_comissao   = models.BooleanField(
        default=True, help_text="Desmarque para quem não recebe comissão.",
    )
    comissao_percentual_padrao = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("4.5"),
        help_text="Percentual padrão de comissão (ex.: 4,50).",
    )
    recebe_vt         = models.BooleanField(
        default=True, help_text="Desmarque para quem não recebe vale-transporte.",
    )
    vt_valor_dia      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    carga_horaria_diaria = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text="Horas/dia esperadas — base do banco de horas quando não há escala. "
                  "Deixe em branco para quem não tem jornada fixa (ex.: sócios).",
    )
    escala            = models.ForeignKey(
        "Escala", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="colaboradores",
        help_text="Escala de trabalho — base dos dias de VT e do banco de horas.",
    )
    escala_ancora_b   = models.DateField(
        null=True, blank=True,
        help_text="Segunda-feira de uma semana em que ela TRABALHA sábado (variante B). "
                  "Define a paridade da alternância de sábados.",
    )
    vt_meses_adiantado = models.IntegerField(
        default=1,
        help_text="Quantos meses à frente o VT é pago junto ao salário. "
                  "1 = salário do mês paga o VT do mês seguinte; 0 = mês corrente.",
    )
    na_folha          = models.BooleanField(
        default=True,
        help_text="Desmarque para quem fica só no cadastro e não entra na folha "
                  "(resumida nem detalhada) — ex.: CEO.",
    )
    registra_ponto    = models.BooleanField(
        default=True,
        help_text="Desmarque para quem não bate ponto (ex.: sócios, CEO).",
    )
    canal_meta_individual = models.CharField(
        max_length=20, blank=True, default="",
        choices=[("show_room_sp", "Show Room SP"), ("anaca", "Anacã SP")],
        help_text="Canal cujas metas individuais alimentam. "
                  "Deixe em branco se não tem meta individual (ex.: Cris).",
    )
    lojas_ponto       = models.ManyToManyField(
        "LocalEmpresa", blank=True, related_name="colaboradores",
        help_text="Lojas onde este colaborador pode registrar o ponto. "
                  "Pode ser uma ou as duas.",
    )
    ativo             = models.BooleanField(default=True)
    criado_em         = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Colaborador"
        verbose_name_plural = "Colaboradores"
        ordering = ["-ativo", "nome"]

    def __str__(self) -> str:
        return self.nome


# ── Escalas de trabalho ──────────────────────────────────────────────────────

class Escala(models.Model):
    """Jornada de trabalho. Pode ter duas variantes de semana (A/B) quando alterna
    sábado — ex.: semana sem sábado (Seg–Qui 09–19, Sex 09–18) × semana com sábado
    (Seg–Sex 10–19, Sáb 10–14), ambas fechando 44h. Escala fixa usa só a variante A."""

    nome           = models.CharField(max_length=120)
    alterna_sabado = models.BooleanField(
        default=False,
        help_text="Se marcado, alterna entre a semana SEM sábado (A) e COM sábado (B).",
    )
    ativo          = models.BooleanField(default=True)
    criado_em      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Escala"
        verbose_name_plural = "Escalas"
        ordering = ["-ativo", "nome"]

    def __str__(self) -> str:
        return self.nome


class EscalaDia(models.Model):
    """Jornada de um dia da semana dentro de uma variante da escala."""

    VARIANTE_CHOICES = [
        ("A", "Semana sem sábado / padrão"),
        ("B", "Semana com sábado"),
    ]
    DIA_CHOICES = [
        (0, "Segunda"), (1, "Terça"), (2, "Quarta"), (3, "Quinta"),
        (4, "Sexta"), (5, "Sábado"), (6, "Domingo"),
    ]

    escala             = models.ForeignKey(Escala, on_delete=models.CASCADE, related_name="dias")
    variante           = models.CharField(max_length=1, choices=VARIANTE_CHOICES, default="A")
    dia_semana         = models.IntegerField(choices=DIA_CHOICES)
    trabalha           = models.BooleanField(default=True)
    hora_entrada       = models.TimeField(null=True, blank=True)
    hora_saida_almoco  = models.TimeField(null=True, blank=True)
    hora_volta_almoco  = models.TimeField(null=True, blank=True)
    hora_saida         = models.TimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Dia de Escala"
        verbose_name_plural = "Dias de Escala"
        ordering = ["escala", "variante", "dia_semana"]
        unique_together = [("escala", "variante", "dia_semana")]

    def __str__(self) -> str:
        return f"{self.escala} {self.variante} — {self.get_dia_semana_display()}"

    def horas(self) -> Decimal:
        """Horas esperadas no dia: (saída − entrada) − almoço. 0 se não trabalha
        ou sem horário."""
        if not self.trabalha or not self.hora_entrada or not self.hora_saida:
            return Decimal("0")
        _h = lambda t: t.hour + t.minute / 60  # noqa: E731
        bruto = _h(self.hora_saida) - _h(self.hora_entrada)
        almoco = 0.0
        if self.hora_saida_almoco and self.hora_volta_almoco:
            almoco = max(_h(self.hora_volta_almoco) - _h(self.hora_saida_almoco), 0)
        return Decimal(str(round(max(bruto - almoco, 0), 2)))


class EscalaExcecao(models.Model):
    """Override manual da variante de UMA semana para UMA colaboradora — cobre trocas
    de sábado (ex.: uma faz dois sábados seguidos enquanto a outra folga)."""

    colaborador    = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="excecoes_escala")
    semana_segunda = models.DateField(help_text="Segunda-feira da semana afetada.")
    variante       = models.CharField(max_length=1, choices=EscalaDia.VARIANTE_CHOICES)
    observacao     = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Exceção de Escala"
        verbose_name_plural = "Exceções de Escala"
        ordering = ["-semana_segunda", "colaborador"]
        unique_together = [("colaborador", "semana_segunda")]

    def __str__(self) -> str:
        return f"{self.colaborador} — semana de {self.semana_segunda:%d/%m/%Y} → {self.variante}"


# ── Salários / folha ─────────────────────────────────────────────────────────

NATUREZA_CHOICES = [
    ("provento", "Provento"),
    ("desconto", "Desconto"),
]


class EventoFolha(models.Model):
    """Lançamento mensal avulso (13º, adiantamento, extra). O salário fixo vem
    de Colaborador.salario_base; aqui ficam os complementos do mês.

    `natureza` define se soma (provento) ou abate (desconto) no total da folha.
    """

    TIPO_CHOICES = [
        ("salario", "Salário"),
        ("decimo_terceiro", "13º salário"),
        ("adiantamento", "Adiantamento"),
        ("outro", "Outro"),
    ]

    colaborador    = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="eventos_folha")
    ano            = models.IntegerField()
    mes            = models.IntegerField()
    natureza       = models.CharField(max_length=10, choices=NATUREZA_CHOICES, default="provento")
    tipo           = models.CharField(max_length=20, choices=TIPO_CHOICES, default="outro")
    valor          = models.DecimalField(max_digits=12, decimal_places=2)
    descricao      = models.CharField(max_length=200, blank=True)
    data_pagamento = models.DateField(
        null=True, blank=True, help_text="Data em que este lançamento foi efetivamente pago.",
    )
    recorrencia    = models.ForeignKey(
        "LancamentoRecorrente", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="gerados",
        help_text="Preenchido quando o lançamento veio de uma recorrência.",
    )
    criado_em      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento de Folha"
        verbose_name_plural = "Eventos de Folha"
        ordering = ["-ano", "-mes", "colaborador"]

    def __str__(self) -> str:
        return f"{self.colaborador} — {self.get_tipo_display()} {self.mes:02d}/{self.ano}"


class LancamentoRecorrente(models.Model):
    """Modelo de lançamento que se repete todo mês (ex.: adiantamento todo dia 20),
    por um período definido ou por tempo indeterminado."""

    colaborador   = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="recorrencias")
    natureza      = models.CharField(max_length=10, choices=NATUREZA_CHOICES, default="provento")
    tipo          = models.CharField(max_length=20, choices=EventoFolha.TIPO_CHOICES, default="adiantamento")
    valor         = models.DecimalField(max_digits=12, decimal_places=2)
    descricao     = models.CharField(max_length=200, blank=True)
    dia_pagamento = models.IntegerField(
        default=20, help_text="Dia do mês em que costuma ser pago (1–31).",
    )
    ano_inicio    = models.IntegerField()
    mes_inicio    = models.IntegerField()
    indefinido    = models.BooleanField(
        default=True, help_text="Se marcado, repete em todos os meses a partir do início.",
    )
    ano_fim       = models.IntegerField(null=True, blank=True)
    mes_fim       = models.IntegerField(null=True, blank=True)
    ativo         = models.BooleanField(default=True)
    criado_em     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lançamento Recorrente"
        verbose_name_plural = "Lançamentos Recorrentes"
        ordering = ["colaborador", "tipo"]

    def __str__(self) -> str:
        return f"{self.colaborador} — {self.get_tipo_display()} (dia {self.dia_pagamento})"

    def ativa_no_mes(self, ano: int, mes: int) -> bool:
        if not self.ativo:
            return False
        if (ano, mes) < (self.ano_inicio, self.mes_inicio):
            return False
        if not self.indefinido and self.ano_fim and self.mes_fim:
            if (ano, mes) > (self.ano_fim, self.mes_fim):
                return False
        return True

    def data_no_mes(self, ano: int, mes: int):
        """Data de pagamento no mês: limita ao último dia e, se cair em fim de
        semana ou feriado, antecipa para o dia útil anterior."""
        import calendar
        from datetime import date

        from apps.rh.services.calendario import dia_util_anterior_ou_mesmo
        ultimo = calendar.monthrange(ano, mes)[1]
        d = date(ano, mes, min(self.dia_pagamento, ultimo))
        return dia_util_anterior_ou_mesmo(d)


class PagamentoFolha(models.Model):
    """Data em que um componente fixo da folha (salário, comissão, VT) foi pago,
    por colaboradora/mês — apenas informativo, para o detalhamento."""

    COMPONENTE_CHOICES = [
        ("salario", "Salário"),
        ("comissao", "Comissão"),
        ("vt", "Vale-transporte"),
    ]

    colaborador    = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="pagamentos_folha")
    ano            = models.IntegerField()
    mes            = models.IntegerField()
    componente     = models.CharField(max_length=20, choices=COMPONENTE_CHOICES)
    data_pagamento = models.DateField()
    atualizado_em  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pagamento de Folha"
        verbose_name_plural = "Pagamentos de Folha"
        ordering = ["-ano", "-mes", "colaborador", "componente"]
        unique_together = [("colaborador", "ano", "mes", "componente")]

    def __str__(self) -> str:
        return f"{self.colaborador} — {self.get_componente_display()} {self.mes:02d}/{self.ano}"


# ── Comissão ─────────────────────────────────────────────────────────────────

class ComissaoPedido(models.Model):
    """Override de comissão por pedido. Sem registro = usa o padrão do colaborador
    sobre o valor total do pedido. O valor da comissão é sempre calculado."""

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="comissoes")
    pedido      = models.ForeignKey("pedidos.PedidoBling", on_delete=models.CASCADE, related_name="comissoes")
    valor_base  = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Base de cálculo. Vazio = usa o valor total do pedido.",
    )
    percentual  = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Vazio = usa o percentual padrão do colaborador.",
    )
    valida      = models.BooleanField(default=True)
    manual      = models.BooleanField(
        default=False,
        help_text="Pedido incluído/alterado manualmente (ex.: vendedor não lançado no Bling).",
    )
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="comissoes_alteradas",
    )
    alterado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Comissão de Pedido"
        verbose_name_plural = "Comissões de Pedidos"
        ordering = ["-pedido__data_pedido"]
        unique_together = [("colaborador", "pedido")]

    def __str__(self) -> str:
        return f"Comissão {self.colaborador} — Pedido #{self.pedido.numero}"

    def base_efetiva(self) -> Decimal:
        if self.valor_base is not None:
            return self.valor_base
        return self.pedido.valor_total

    def percentual_efetivo(self) -> Decimal:
        if self.percentual is not None:
            return self.percentual
        return self.colaborador.comissao_percentual_padrao

    def valor_comissao(self) -> Decimal:
        return (self.base_efetiva() * self.percentual_efetivo() / Decimal("100")).quantize(Decimal("0.01"))


class ComissaoLog(models.Model):
    """Histórico de alterações manuais de comissão (base ou percentual)."""

    comissao  = models.ForeignKey(ComissaoPedido, on_delete=models.CASCADE, related_name="logs")
    campo     = models.CharField(max_length=20)  # "base" | "percentual" | "inclusao"
    de        = models.CharField(max_length=40, blank=True)
    para      = models.CharField(max_length=40, blank=True)
    usuario   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="comissao_logs",
    )
    em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de Comissão"
        verbose_name_plural = "Logs de Comissão"
        ordering = ["-em"]

    def __str__(self) -> str:
        return f"{self.comissao} — {self.campo}: {self.de} → {self.para}"


# ── Férias ───────────────────────────────────────────────────────────────────

class PeriodoAquisitivo(models.Model):
    """Período aquisitivo de férias. Dias de direito padrão 30 (CLT)."""

    colaborador  = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="periodos_ferias")
    inicio       = models.DateField()
    fim          = models.DateField()
    dias_direito = models.IntegerField(default=30)
    abono_dias   = models.IntegerField(
        default=0,
        help_text="Abono pecuniário (venda de férias): dias comprados pela empresa. "
                  "Abatem do saldo. Só liberado após o período completar.",
    )
    observacao   = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Período Aquisitivo"
        verbose_name_plural = "Períodos Aquisitivos"
        ordering = ["colaborador", "-inicio"]

    def __str__(self) -> str:
        return f"{self.colaborador} — {self.inicio:%d/%m/%Y} a {self.fim:%d/%m/%Y}"


class GozoFerias(models.Model):
    """Período (ou dia avulso) de férias efetivamente gozado. Pode ser 1, 2, 3… dias."""

    periodo     = models.ForeignKey(PeriodoAquisitivo, on_delete=models.CASCADE, related_name="gozos")
    data_inicio = models.DateField()
    dias        = models.IntegerField(default=1)
    observacao  = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Gozo de Férias"
        verbose_name_plural = "Gozos de Férias"
        ordering = ["data_inicio"]

    def __str__(self) -> str:
        return f"{self.periodo.colaborador} — {self.dias} dia(s) a partir de {self.data_inicio:%d/%m/%Y}"


# ── Afastamentos (férias, folga, atestado…) ──────────────────────────────────

def _anexo_afastamento_path(instance, filename):
    return f"afastamentos/{instance.colaborador_id}/{filename}"


class Afastamento(models.Model):
    """Ausência justificada de um colaborador num intervalo de dias. Cobre férias
    (puxa do período aquisitivo), folga, atestado, falta e outros. Dias cobertos
    não geram pendência de ponto."""

    # "ferias" continua nos choices só para exibir lançamentos legados; o lançamento
    # de férias agora é feito exclusivamente no módulo Férias. Use FORM_TIPO_CHOICES
    # no formulário de afastamentos (faltas, atestados, folgas).
    TIPO_CHOICES = [
        ("ferias", "Férias"),
        ("folga", "Folga"),
        ("atestado", "Atestado"),
        ("falta", "Falta"),
        ("outro", "Outro"),
    ]
    FORM_TIPO_CHOICES = [
        ("falta", "Falta"),
        ("atestado", "Atestado"),
        ("folga", "Folga"),
        ("outro", "Outro"),
    ]

    colaborador   = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="afastamentos")
    tipo          = models.CharField(max_length=12, choices=TIPO_CHOICES)
    data_inicio   = models.DateField()
    data_fim      = models.DateField()
    periodo_ferias = models.ForeignKey(
        PeriodoAquisitivo, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="afastamentos",
        help_text="Período aquisitivo de onde abater os dias (apenas para férias).",
    )
    remunerado    = models.BooleanField(
        default=True, help_text="Folga/falta abonada (remunerada). Desmarque para falta não abonada.",
    )
    anexo         = models.FileField(
        upload_to=_anexo_afastamento_path, null=True, blank=True,
        help_text="Atestado/comprovante (PDF ou imagem). Imagens são convertidas para WebP.",
    )
    observacao    = models.CharField(max_length=300, blank=True)
    criado_por    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="afastamentos_lancados",
    )
    criado_em     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Afastamento"
        verbose_name_plural = "Afastamentos"
        ordering = ["-data_inicio", "colaborador"]

    def __str__(self) -> str:
        return f"{self.colaborador} — {self.get_tipo_display()} {self.data_inicio:%d/%m} a {self.data_fim:%d/%m/%Y}"

    @property
    def dias(self) -> int:
        return (self.data_fim - self.data_inicio).days + 1

    def cobre(self, dia) -> bool:
        return self.data_inicio <= dia <= self.data_fim


# ── Benefícios ───────────────────────────────────────────────────────────────

class TipoBeneficio(models.Model):
    """Tipo de benefício oferecido (VT, VA, VR, Plano de Saúde…).

    O Vale-Transporte é especial: continua armazenado em `BeneficioVT` (dias × valor,
    integrado à folha). Os demais tipos usam `LancamentoBeneficio` (valor mensal por
    colaborador) e ficam apenas no módulo Benefícios — não entram na folha.
    """

    nome      = models.CharField(max_length=80, unique=True)
    sigla     = models.CharField(max_length=12, blank=True, help_text="Ex.: VA, VR, Plano.")
    eh_vt     = models.BooleanField(
        default=False,
        help_text="Marca o Vale-Transporte — usa a tela dias × valor e entra na folha.",
    )
    ativo     = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tipo de Benefício"
        verbose_name_plural = "Tipos de Benefício"
        ordering = ["-eh_vt", "nome"]

    def __str__(self) -> str:
        return self.nome


class LancamentoBeneficio(models.Model):
    """Benefício avulso (não-VT) de um colaborador num mês: um valor mensal.

    Usado para VA, VR, plano de saúde etc. Não entra no cálculo da folha — serve
    para registrar e vincular quem recebe cada benefício.
    """

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="beneficios")
    tipo        = models.ForeignKey(TipoBeneficio, on_delete=models.CASCADE, related_name="lancamentos")
    ano         = models.IntegerField()
    mes         = models.IntegerField()
    valor       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lançamento de Benefício"
        verbose_name_plural = "Lançamentos de Benefício"
        ordering = ["-ano", "-mes", "tipo", "colaborador"]
        unique_together = [("colaborador", "tipo", "ano", "mes")]

    def __str__(self) -> str:
        return f"{self.tipo} {self.colaborador} — {self.mes:02d}/{self.ano}"


class BeneficioVT(models.Model):
    """Vale-transporte por colaborador/mês: dias úteis × valor do dia."""

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="vts")
    ano         = models.IntegerField()
    mes         = models.IntegerField()
    dias        = models.IntegerField(default=0)
    valor_dia   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vale-Transporte"
        verbose_name_plural = "Vales-Transporte"
        ordering = ["-ano", "-mes", "colaborador"]
        unique_together = [("colaborador", "ano", "mes")]

    def __str__(self) -> str:
        return f"VT {self.colaborador} — {self.mes:02d}/{self.ano}"

    def total(self) -> Decimal:
        return (Decimal(self.dias) * self.valor_dia).quantize(Decimal("0.01"))


# ── Controle de Ponto ────────────────────────────────────────────────────────

class LocalEmpresa(models.Model):
    """Loja onde o ponto pode ser registrado (geofence). Pode haver várias —
    cada colaborador é vinculado a uma ou mais via Colaborador.lojas_ponto."""

    nome        = models.CharField(max_length=120, default="Loja")
    latitude    = models.DecimalField(max_digits=10, decimal_places=7)
    longitude   = models.DecimalField(max_digits=10, decimal_places=7)
    raio_metros = models.IntegerField(default=100)
    ativo       = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Loja"
        verbose_name_plural = "Lojas"
        ordering = ["-ativo", "nome"]

    def __str__(self) -> str:
        return f"{self.nome} (raio {self.raio_metros}m)"


class ParametrosPonto(models.Model):
    """Parâmetros globais do controle de ponto. Registro único (singleton, pk=1)."""

    tolerancia_minutos = models.IntegerField(
        default=10,
        help_text="Atrasos/extras dentro deste limite (em minutos) não viram saldo "
                  "no banco de horas. Ex.: 10.",
    )
    intervalo_minimo_minutos = models.IntegerField(
        default=2,
        help_text="Tempo mínimo (em minutos) entre duas batidas. Evita registrar "
                  "duas vezes por engano em cliques seguidos. Ex.: 2.",
    )
    data_inicio = models.DateField(
        default=date(2026, 7, 1),
        help_text="Pendências de ponto só são apuradas a partir deste dia. "
                  "Dias anteriores não cobram batida nem geram correção.",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parâmetros do Ponto"
        verbose_name_plural = "Parâmetros do Ponto"

    def __str__(self) -> str:
        return f"Parâmetros do Ponto (tolerância {self.tolerancia_minutos} min)"

    @classmethod
    def get(cls) -> "ParametrosPonto":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BatidaPonto(models.Model):
    """Batida individual de ponto, com geolocalização validada no momento do registro.

    O `tipo` é definido pela ordem cronológica das batidas do dia (1ª=entrada,
    2ª=saída almoço, 3ª=volta, 4ª=saída) — reordenado automaticamente a cada
    inclusão/edição. Ver services.ponto.reordenar_tipos_do_dia."""

    TIPO_CHOICES = [
        ("entrada", "Entrada"),
        ("saida_almoco", "Saída p/ almoço"),
        ("volta_almoco", "Volta do almoço"),
        ("saida", "Saída"),
    ]
    ORIGEM_CHOICES = [
        ("app", "Aplicativo"),
        ("manual", "Manual (gestor)"),
    ]

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="batidas")
    momento     = models.DateTimeField()
    tipo        = models.CharField(max_length=20, choices=TIPO_CHOICES)
    loja        = models.ForeignKey(
        LocalEmpresa, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="batidas", help_text="Loja onde a batida foi registrada.",
    )
    latitude    = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude   = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    distancia_m = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    dentro_raio = models.BooleanField(default=False)
    origem      = models.CharField(max_length=10, choices=ORIGEM_CHOICES, default="app")
    observacao  = models.CharField(max_length=200, blank=True)
    ajustado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="batidas_ajustadas",
        help_text="Gestor que incluiu/alterou a batida manualmente.",
    )
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Batida de Ponto"
        verbose_name_plural = "Batidas de Ponto"
        ordering = ["-momento"]

    def __str__(self) -> str:
        return f"{self.colaborador} — {self.get_tipo_display()} {self.momento:%d/%m %H:%M}"


class NotificacaoPonto(models.Model):
    """Pendência de ponto de um colaborador em um dia (batida faltando). Gerada
    automaticamente pelo job diário; o colaborador vê no sino e o gestor analisa."""

    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("analise", "Em análise do gestor"),
        ("resolvido", "Resolvido"),
    ]

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="notificacoes_ponto")
    data        = models.DateField(help_text="Dia com batidas incompletas.")
    mensagem    = models.CharField(max_length=240)
    status      = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pendente")
    lida        = models.BooleanField(default=False)
    criado_em   = models.DateTimeField(auto_now_add=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Notificação de Ponto"
        verbose_name_plural = "Notificações de Ponto"
        ordering = ["-data", "colaborador"]
        unique_together = [("colaborador", "data")]

    def __str__(self) -> str:
        return f"{self.colaborador} — pendência {self.data:%d/%m/%Y} ({self.get_status_display()})"


class CorrecaoPonto(models.Model):
    """Proposta de correção feita pelo próprio funcionário para um dia com batidas
    faltando. O gestor aprova (aplica os horários) ou ajusta manualmente."""

    STATUS_CHOICES = [
        ("pendente", "Aguardando aprovação"),
        ("aprovada", "Aprovada"),
        ("rejeitada", "Rejeitada"),
    ]

    colaborador       = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name="correcoes_ponto")
    data              = models.DateField()
    prop_entrada      = models.TimeField(null=True, blank=True)
    prop_saida_almoco = models.TimeField(null=True, blank=True)
    prop_volta_almoco = models.TimeField(null=True, blank=True)
    prop_saida        = models.TimeField(null=True, blank=True)
    sem_almoco        = models.BooleanField(
        default=False, help_text="Funcionário declarou que não teve horário de almoço.",
    )
    observacao        = models.CharField(max_length=240, blank=True)
    status            = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pendente")
    campos_aplicados  = models.CharField(
        max_length=60, blank=True, default="",
        help_text="Tipos de batida realmente criados/alterados na aprovação "
                  "(auditoria — os que já vieram do app não entram aqui).",
    )
    criado_em         = models.DateTimeField(auto_now_add=True)
    avaliado_por      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="correcoes_avaliadas",
    )
    avaliado_em       = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Correção de Ponto"
        verbose_name_plural = "Correções de Ponto"
        ordering = ["-data", "colaborador"]
        unique_together = [("colaborador", "data")]

    def __str__(self) -> str:
        return f"{self.colaborador} — correção {self.data:%d/%m/%Y} ({self.get_status_display()})"
