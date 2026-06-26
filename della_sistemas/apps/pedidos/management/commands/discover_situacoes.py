"""Lista todas as situações Bling para descobrir IDs desconhecidos."""

from django.core.management.base import BaseCommand

from apps.pedidos.services.bling_client import coletar_situacoes_de_pedidos
from apps.pedidos.services.situacoes import ALL_IDS


class Command(BaseCommand):
    help = "Coleta situações únicas de pedidos Bling dos últimos 180 dias e exibe IDs"

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=180,
                            help="Janela de pedidos para varrer (padrão: 180 dias)")

    def handle(self, *args, **options):
        dias = options["dias"]
        self.stdout.write(f"Coletando situações de pedidos dos últimos {dias} dias...\n")
        situacoes = coletar_situacoes_de_pedidos(dias=dias)

        if not situacoes:
            self.stdout.write(self.style.WARNING("Nenhuma situação retornada."))
            self.stdout.write("Verifique autenticação Bling e o endpoint /situacoes.\n")
            return

        self.stdout.write(f"\n{'ID':>12}  {'Nome':<40}  {'Mapeado?'}")
        self.stdout.write("-" * 65)
        for s in sorted(situacoes, key=lambda x: x.get("id", 0)):
            sid = s.get("id", "?")
            nome = s.get("nome") or s.get("descricao") or "?"
            mapeado = "✓ " + ALL_IDS[sid] if sid in ALL_IDS else "  —  NÃO MAPEADO"
            self.stdout.write(f"{sid:>12}  {nome:<40}  {mapeado}")

        nao_mapeados = [s for s in situacoes if s.get("id") not in ALL_IDS]
        if nao_mapeados:
            self.stdout.write(self.style.WARNING(
                f"\n{len(nao_mapeados)} situação(ões) não mapeadas. "
                "Preencha EM_ABERTO_IDS e EM_ANDAMENTO_IDS em apps/pedidos/services/situacoes.py"
            ))
        else:
            self.stdout.write(self.style.SUCCESS("\nTodas as situações já estão mapeadas."))

        self.stdout.write(f"\nTotal: {len(situacoes)} situações.\n")
