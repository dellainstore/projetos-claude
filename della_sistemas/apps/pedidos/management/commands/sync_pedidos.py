"""Sincroniza pedidos do Bling com o banco local."""

from django.core.management.base import BaseCommand

from apps.pedidos.services.sync import sync_pedidos


class Command(BaseCommand):
    help = "Sincroniza pedidos do Bling (cache local) por janela de dias"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias", type=int, default=90,
            help="Janela retroativa em dias (padrão: 90)"
        )
        parser.add_argument(
            "--completo", action="store_true",
            help="Sync completo: de 01/01/2026 até hoje (ignora --dias)"
        )
        parser.add_argument(
            "--situacoes", nargs="*", type=int, default=None,
            help="IDs de situação Bling específicos (padrão: todos mapeados)"
        )

    def handle(self, *args, **options):
        dias = options["dias"]
        situacoes = options["situacoes"]
        completo = options["completo"]
        if completo:
            self.stdout.write("Iniciando sync COMPLETO — de 01/01/2026 até hoje...\n")
        else:
            self.stdout.write(f"Iniciando sync — últimos {dias} dias...\n")
        stats = sync_pedidos(
            situacao_ids=situacoes,
            dias_retroativos=None if completo else dias,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Sync concluído: inseridos={stats['inserted']} "
                f"atualizados={stats['updated']} "
                f"sem_mudança={stats['unchanged']} "
                f"erros={stats['errors']}"
            )
        )
