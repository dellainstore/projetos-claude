"""
Management command: processar_pipeline

Processa o pipeline completo:
  1. Requests APPROVED → cria produtos no Bling + PENDING stock_moves
  2. Stock moves PENDING → aplica estoque no Bling

Uso manual:
  python manage.py processar_pipeline

Uso automático via systemd timer (ver deploy/della-pipeline.timer).
"""
import time
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Processa requests aprovados e stock moves pendentes"

    def add_arguments(self, parser):
        parser.add_argument("--requests-limit", type=int, default=20)
        parser.add_argument("--moves-limit", type=int, default=50)

    def handle(self, *args, **options):
        from apps.produtos.services.business.process_approved_requests import processar_requests_aprovados
        from apps.produtos.services.business.process_stock_moves import processar_stock_moves

        t0 = time.time()

        r1 = processar_requests_aprovados(limit=options["requests_limit"])
        self.stdout.write(
            f"[requests] processados={r1['processed_requests']} "
            f"criados={r1['created_products']} "
            f"existentes={r1['skipped_existing']} "
            f"erros={len(r1['errors'])}"
        )
        for err in r1.get("errors", []):
            self.stderr.write(f"  ERRO request #{err['request_id']}: {err['error']}")

        r2 = processar_stock_moves(limit=options["moves_limit"])
        self.stdout.write(
            f"[moves]    processados={r2['processed']} "
            f"ok={r2['ok']} "
            f"erros={r2['error']}"
        )
        for m in r2.get("error_moves", []):
            self.stderr.write(f"  ERRO move #{m['move_id']}: {m.get('error','')}")

        elapsed = time.time() - t0
        self.stdout.write(f"Pipeline concluído em {elapsed:.1f}s")
