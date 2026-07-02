"""Verifica batidas incompletas e gera/atualiza as pendências de ponto.

Roda no fim do dia (cron). Por padrão verifica o dia de ontem (o dia já fechou);
pode receber --data YYYY-MM-DD para reprocessar um dia específico.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.rh.services.notificacoes import gerar_pendencias_do_dia


class Command(BaseCommand):
    help = "Gera pendências de ponto (batidas faltando) para um dia."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data", help="Dia a verificar (YYYY-MM-DD). Padrão: ontem.",
        )
        parser.add_argument(
            "--hoje", action="store_true",
            help="Verifica o dia de hoje em vez de ontem.",
        )

    def handle(self, *args, **options):
        if options.get("data"):
            dia = date.fromisoformat(options["data"])
        elif options.get("hoje"):
            dia = timezone.localdate()
        else:
            dia = timezone.localdate() - timedelta(days=1)

        abertas = gerar_pendencias_do_dia(dia)
        self.stdout.write(self.style.SUCCESS(
            f"Ponto {dia:%d/%m/%Y}: {abertas} pendência(s) aberta(s)."
        ))
