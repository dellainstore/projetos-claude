from django.conf import settings
from django.db import models


class ColunaStatus(models.Model):
    """Coluna do quadro Kanban. Nomes/quantidade configuráveis pelo Super
    Admin — não fixos no código (tela em apps/tarefas/views/colunas.py)."""

    nome = models.CharField(max_length=40)
    ordem = models.PositiveIntegerField(default=0)
    cor = models.CharField(max_length=20, blank=True, help_text="Cor hex opcional, ex.: #c9a96e")
    eh_conclusao = models.BooleanField(
        default=False,
        verbose_name="É coluna de conclusão",
        help_text="Tarefas aqui não entram no contador de pendências do menu.",
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem"]
        verbose_name = "Coluna de status"
        verbose_name_plural = "Colunas de status"

    def __str__(self) -> str:
        return self.nome


class Tarefa(models.Model):
    PRIORIDADE_CHOICES = [
        ("baixa", "Baixa"),
        ("media", "Média"),
        ("alta", "Alta"),
    ]
    MOTIVO_ARQUIVAMENTO_CHOICES = [
        ("concluida", "Concluída"),
        ("excluida", "Excluída"),
    ]

    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES, default="media")
    prazo = models.DateField()
    status = models.ForeignKey(ColunaStatus, on_delete=models.PROTECT, related_name="tarefas")
    posicao = models.PositiveIntegerField(default=0)  # ordem dentro da coluna

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tarefas_criadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    editado_em = models.DateTimeField(
        null=True, blank=True,
        help_text="Só marcado quando o criador edita título/descrição/prazo/prioridade "
                   "— usado pra avisar responsáveis que ainda não viram a mudança. "
                   "Mover de coluna não conta como edição.",
    )
    arquivada = models.BooleanField(default=False)  # soft delete — exclusão real nunca apaga histórico
    arquivada_em = models.DateTimeField(null=True, blank=True)
    motivo_arquivamento = models.CharField(max_length=20, choices=MOTIVO_ARQUIVAMENTO_CHOICES, blank=True)

    concluida_em = models.DateTimeField(
        null=True, blank=True,
        help_text="Quando entrou numa coluna de conclusão — zera se voltar pra uma "
                   "coluna ativa. O comando arquivar_tarefas_concluidas usa isso pra "
                   "saber há quantos dias está concluída.",
    )

    responsaveis = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="TarefaResponsavel",
        related_name="tarefas_responsavel",
    )

    class Meta:
        ordering = ["posicao", "-criado_em"]
        verbose_name = "Tarefa"
        verbose_name_plural = "Tarefas"

    def __str__(self) -> str:
        return self.titulo


class TarefaResponsavel(models.Model):
    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    atribuida_em = models.DateTimeField(auto_now_add=True)
    visto_em = models.DateTimeField(
        null=True, blank=True,
        help_text="Última vez que este responsável abriu o card — comparado com "
                   "Tarefa.editado_em pra saber se ele já viu a versão mais recente.",
    )

    class Meta:
        unique_together = [("tarefa", "usuario")]

    def __str__(self) -> str:
        return f"{self.usuario} em {self.tarefa}"


class HistoricoTarefa(models.Model):
    CAMPO_CHOICES = [
        ("criacao", "Criação"),
        ("titulo", "Título"),
        ("descricao", "Descrição"),
        ("prioridade", "Prioridade"),
        ("prazo", "Prazo"),
        ("status", "Status"),
        ("responsaveis", "Responsáveis"),
        ("arquivada", "Exclusão"),
    ]

    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name="historico")
    campo = models.CharField(max_length=30, choices=CAMPO_CHOICES)
    valor_anterior = models.CharField(max_length=255, blank=True)
    valor_novo = models.CharField(max_length=255, blank=True)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    alterado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-alterado_em"]
        verbose_name = "Histórico de tarefa"
        verbose_name_plural = "Histórico de tarefas"
