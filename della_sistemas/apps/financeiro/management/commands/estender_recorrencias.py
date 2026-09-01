"""Estende a janela de geração das recorrências sem fim definido (Private
Label). Idempotente — pode rodar mais de 1x sem duplicar nada (ver
`services/private_label/recorrencias.py`). Mecanismo primário: cron 1x/dia.
"""
from django.core.management.base import BaseCommand

from apps.financeiro.services.private_label.recorrencias import estender_janela_recorrencias


class Command(BaseCommand):
    help = "Gera as próximas ocorrências das regras de recorrência do Private Label (idempotente)."

    def handle(self, *args, **options):
        resultado = estender_janela_recorrencias()
        if not resultado:
            self.stdout.write(self.style.SUCCESS("Nenhuma ocorrência nova a gerar."))
            return
        total = sum(resultado.values())
        self.stdout.write(self.style.SUCCESS(
            f"{total} ocorrência(s) gerada(s) em {len(resultado)} regra(s): {resultado}"
        ))
