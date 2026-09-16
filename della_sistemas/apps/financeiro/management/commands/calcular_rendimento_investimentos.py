"""Atualiza o CDI diário (Bacen) e lança o rendimento automático das contas
de investimento indexadas a ele (Private Label). Idempotente — pode rodar
mais de 1x sem duplicar nada (ver `services/private_label/cdi.py`).
Mecanismo primário: cron 1x/dia.
"""
from django.core.management.base import BaseCommand

from apps.financeiro.services.private_label.cdi import (
    atualizar_taxas_cdi,
    lancar_rendimentos_automaticos_todas_contas,
)


class Command(BaseCommand):
    help = "Sincroniza o CDI do Bacen e lança o rendimento automático das contas de investimento (% CDI)."

    def handle(self, *args, **options):
        qtd_taxas = atualizar_taxas_cdi()
        self.stdout.write(f"{qtd_taxas} taxa(s) de CDI sincronizada(s) do Bacen.")

        resultado = lancar_rendimentos_automaticos_todas_contas()
        if not resultado:
            self.stdout.write(self.style.SUCCESS("Nenhum rendimento pendente a lançar."))
            return
        total = sum(resultado.values())
        self.stdout.write(self.style.SUCCESS(
            f"{total} dia(s) de rendimento lançado(s) em {len(resultado)} conta(s): {resultado}"
        ))
