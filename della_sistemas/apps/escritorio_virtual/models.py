"""Modelos do Escritório Virtual (D'ELLA Sistemas).

Este módulo guarda **apenas configuração de cenário**: quais salas existem,
qual personagem representa cada colaborador e quais parâmetros visuais regem
a cena. O estado de cada personagem (trabalhando, no almoço, fora) **nunca**
é persistido aqui: ele é recalculado a cada leitura a partir do módulo de
ponto (`apps.rh`), que segue sendo a fonte oficial.

Ver `services/projecao.py` para a derivação e `services/salas.py` para a
resolução de sala.
"""

from datetime import time

from django.core.validators import MinValueValidator
from django.db import models


class SalaEscritorio(models.Model):
    """Ambiente do mapa 2D (entrada, showrooms, refeitório).

    O vínculo com a loja física (`LocalEmpresa`) mora aqui, não na personagem:
    a batida de ponto diz em QUAL LOJA a pessoa está, e é a sala que sabe qual
    loja ela representa. Como a resolução precisa ser determinística
    (uma loja resolve para exatamente uma sala), o campo é `OneToOne`.
    """

    slug        = models.SlugField(
        max_length=40, unique=True,
        help_text="Identificador técnico usado pelo frontend. Ex.: showroom-1.",
    )
    nome        = models.CharField(max_length=80)
    ordem       = models.IntegerField(default=0, help_text="Ordem de exibição.")
    ativo       = models.BooleanField(default=True)

    loja        = models.OneToOneField(
        "rh.LocalEmpresa", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sala_virtual",
        help_text="Loja física que esta sala representa. Uma loja mapeia para "
                  "no máximo uma sala (evita ambiguidade na resolução).",
    )

    # Layout no mapa (unidades do cenário, não pixels de tela).
    pos_x       = models.IntegerField(default=0)
    pos_y       = models.IntegerField(default=0)
    largura     = models.IntegerField(default=200, validators=[MinValueValidator(1)])
    altura      = models.IntegerField(default=150, validators=[MinValueValidator(1)])

    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sala do Escritório"
        verbose_name_plural = "Salas do Escritório"
        ordering = ["ordem", "slug"]

    def __str__(self) -> str:
        return self.nome


class PersonagemEscritorio(models.Model):
    """Ator do cenário. Na v1 só `HUMAN_EMPLOYEE` tem estado (vindo do ponto).

    `AI_AGENT` e `SYSTEM_ACTOR` existem apenas para o domínio já nascer
    preparado (ver seção 12 do plano); nenhum deles é animado na v1 e nenhuma
    integração de IA é feita aqui.
    """

    HUMAN_EMPLOYEE = "HUMAN_EMPLOYEE"
    AI_AGENT       = "AI_AGENT"
    SYSTEM_ACTOR   = "SYSTEM_ACTOR"
    TIPO_ATOR_CHOICES = [
        (HUMAN_EMPLOYEE, "Funcionário humano (estado vem do ponto)"),
        (AI_AGENT, "Agente de IA (estado virá de tarefas, futuro)"),
        (SYSTEM_ACTOR, "Ator do sistema (estado virá de eventos técnicos, futuro)"),
    ]

    colaborador  = models.OneToOneField(
        "rh.Colaborador", on_delete=models.CASCADE, null=True, blank=True,
        related_name="personagem_escritorio",
        help_text="Obrigatório para HUMAN_EMPLOYEE. Vazio para atores não humanos.",
    )
    tipo_ator    = models.CharField(
        max_length=20, choices=TIPO_ATOR_CHOICES, default=HUMAN_EMPLOYEE,
    )
    personagem   = models.SlugField(
        max_length=40,
        help_text="Slug do sprite/skin. Ex.: tina. Não é chave de negócio.",
    )
    sala_padrao  = models.ForeignKey(
        SalaEscritorio, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="personagens_padrao",
        help_text="Fallback: usada quando a batida não informa loja ou a loja "
                  "não tem sala mapeada.",
    )
    pos_x        = models.IntegerField(default=0)
    pos_y        = models.IntegerField(default=0)
    ativo        = models.BooleanField(default=True)
    criado_em    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Personagem do Escritório"
        verbose_name_plural = "Personagens do Escritório"
        ordering = ["personagem"]
        constraints = [
            models.CheckConstraint(
                # Ator humano sem colaborador não teria fonte de estado; ator
                # não humano com colaborador confundiria a projeção.
                check=(
                    models.Q(tipo_ator="HUMAN_EMPLOYEE", colaborador__isnull=False)
                    | (~models.Q(tipo_ator="HUMAN_EMPLOYEE") & models.Q(colaborador__isnull=True))
                ),
                name="escritorio_humano_exige_colaborador",
            ),
        ]

    def __str__(self) -> str:
        if self.colaborador_id:
            return f"{self.personagem} ({self.colaborador})"
        return f"{self.personagem} ({self.get_tipo_ator_display()})"


class ParametrosEscritorio(models.Model):
    """Parâmetros visuais do escritório. Registro único (singleton, pk=1).

    Nada aqui altera regra trabalhista: são só limites de RENDERIZAÇÃO. A
    margem de fechamento decide quando a loja apaga as luzes, não quando o
    ponto cobra uma batida (isso continua em `ParametrosPonto` e no job
    `verificar_ponto`).
    """

    poll_segundos = models.IntegerField(
        default=10,
        help_text="Intervalo de consulta do frontend, em segundos.",
    )
    margem_fechamento_minutos = models.IntegerField(
        default=90,
        help_text="Quanto tempo depois da saída prevista pela escala a loja "
                  "apaga as luzes e a personagem vira MISSING_PUNCH.",
    )
    hora_limite_absoluta = models.TimeField(
        default=time(23, 0),
        help_text="Limite usado quando NÃO há escala com horário de saída "
                  "para o dia (não é teto da margem acima).",
    )
    evento_recente_segundos = models.IntegerField(
        default=120,
        help_text="Janela em que uma batida ainda dispara animação de "
                  "transição (ARRIVING, RETURNING_FROM_LUNCH, LEAVING). "
                  "Quem abre a página depois disso vê a cena parada.",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parâmetros do Escritório"
        verbose_name_plural = "Parâmetros do Escritório"

    def __str__(self) -> str:
        return f"Parâmetros do Escritório (poll {self.poll_segundos}s)"

    @classmethod
    def atual(cls) -> "ParametrosEscritorio":
        """Instância de leitura. **Não grava nada**: se a linha não existe,
        devolve um objeto não salvo com os defaults.

        A projeção é somente leitura por contrato, então não pode usar
        `get_or_create` (que escreveria na primeira execução, inclusive a
        partir de um GET de API)."""
        return cls.objects.filter(pk=1).first() or cls(pk=1)

    @classmethod
    def editavel(cls) -> "ParametrosEscritorio":
        """Instância persistida, para telas de configuração (escreve se
        necessário). Não deve ser usada pela projeção."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
