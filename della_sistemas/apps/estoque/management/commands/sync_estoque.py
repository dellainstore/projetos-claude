"""
Management command: sync_estoque

Sincroniza preço/custo/fornecedor, saldo de estoque e vendas do Bling para o
banco do módulo Estoque (Análise). Substitui o antigo
`app/estoque/jobs/sync_estoque.py` (Streamlit).

Uso manual:
  python manage.py sync_estoque
  python manage.py sync_estoque --only-vendas --dias 2 --workers 3

Uso automático: cron diário (ver crontab).
"""
import json
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.estoque.services.config import LOG_DIR
from apps.estoque.services.sync import (
    sync_estoque,
    sync_produtos,
    sync_vendas,
    sync_vendas_historico_mensal,
)


class Command(BaseCommand):
    help = "Sincroniza preço/custo, saldo de estoque e vendas do Bling (módulo Estoque - Análise)"

    def add_arguments(self, parser):
        parser.add_argument("--inicio", type=str, default=None, help="Data inicial das vendas (YYYY-MM-DD)")
        parser.add_argument("--fim", type=str, default=None, help="Data final das vendas (YYYY-MM-DD)")
        parser.add_argument("--dias", type=int, default=30, help="Janela de dias para vendas quando --inicio/--fim não informados")
        parser.add_argument("--only-vendas", action="store_true", help="Executa somente a sincronização de vendas")
        parser.add_argument("--historico-mensal", action="store_true", help="Executa vendas em blocos mensais")
        parser.add_argument("--workers", type=int, default=5, help="Workers para buscar detalhes de pedidos")

    def handle(self, *args, **options):
        started_at = int(time.time())
        fim = options["fim"] or date.today().isoformat()
        inicio = options["inicio"] or (date.today() - timedelta(days=max(1, options["dias"]))).isoformat()

        out: dict = {
            "started_at": started_at,
            "sync_produtos": {},
            "sync_estoque": {},
            "sync_vendas": {},
            "inicio": inicio,
            "fim": fim,
            "ok": False,
        }

        try:
            if not options["only_vendas"]:
                out["sync_produtos"] = sync_produtos()
                out["sync_estoque"] = sync_estoque()
            if options["historico_mensal"]:
                out["sync_vendas"] = sync_vendas_historico_mensal(
                    periodo_inicio=inicio, periodo_fim=fim, detail_workers=options["workers"]
                )
            else:
                out["sync_vendas"] = sync_vendas(
                    periodo_inicio=inicio, periodo_fim=fim, detail_workers=options["workers"]
                )
            out["ok"] = True
        except Exception as e:  # noqa: BLE001 — registramos e retornamos status
            out["error"] = str(e)

        out["finished_at"] = int(time.time())
        out["duration_sec"] = int(out["finished_at"] - started_at)

        log_file = LOG_DIR / "sync_estoque_cron.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")

        self.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
        if not out["ok"]:
            raise SystemExit(1)
