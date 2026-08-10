from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tarefas.models import Tarefa
from apps.tarefas.services.regras import registrar_historico


class Command(BaseCommand):
    help = (
        "Tira do quadro ativo as tarefas concluídas há mais de N dias (padrão 2) — "
        "elas continuam acessíveis em Tarefas > Histórico, só saem do board pra não "
        "acumular card 'Concluído' pra sempre."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=2)

    def handle(self, *args, **options):
        dias = options["dias"]
        limite = timezone.now() - timedelta(days=dias)

        qs = Tarefa.objects.filter(
            arquivada=False,
            concluida_em__isnull=False,
            concluida_em__lte=limite,
        )

        total = 0
        for tarefa in qs:
            tarefa.arquivada = True
            tarefa.arquivada_em = timezone.now()
            tarefa.motivo_arquivamento = "concluida"
            tarefa.save(update_fields=["arquivada", "arquivada_em", "motivo_arquivamento"])
            registrar_historico(
                tarefa, "arquivada", "concluída",
                f"arquivada automaticamente ({dias} dias em conclusão)",
                None,
            )
            total += 1

        self.stdout.write(self.style.SUCCESS(
            f"{total} tarefa(s) arquivada(s) (concluídas há mais de {dias} dia(s))."
        ))
