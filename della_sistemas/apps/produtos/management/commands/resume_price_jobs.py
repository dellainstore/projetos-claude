"""
Management command: resume_price_jobs

Detecta jobs de atualização de preços "travados" (status pending/running sem
progresso há mais de N segundos — sinal de que o worker que os processava
morreu no meio, ex.: `della restart admin` durante uma atualização em lote) e
refaz cada um do zero com os parâmetros originais salvos no job.

Reaplicar é seguro: preços já enviados ao Bling são apenas confirmados
(skip), nunca duplicados.

Uso manual:
  python manage.py resume_price_jobs

Uso automático: cron a cada poucos minutos.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Retoma jobs de atualização de preços travados por um restart do servidor"

    def add_arguments(self, parser):
        parser.add_argument("--stale-seconds", type=int, default=120)

    def handle(self, *args, **options):
        from apps.produtos.services.precos import retomar_jobs_travados

        retomados = retomar_jobs_travados(stale_seconds=options["stale_seconds"])
        if retomados:
            self.stdout.write(self.style.SUCCESS(f"{len(retomados)} job(s) retomado(s): {', '.join(retomados)}"))
        else:
            self.stdout.write("Nenhum job travado encontrado.")
