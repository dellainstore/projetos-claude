"""
Management command: sync_catalog

Sincroniza o catálogo de produtos do Bling para o inclusoes.db e reconstrói
as variações a partir dos produtos. Substitui o antigo
`app/produtos/src/admin/run_catalog_sync.py` (Streamlit), reaproveitando o
código já portado em apps/produtos/services.

Uso manual:
  python manage.py sync_catalog

Uso automático: cron diário (ver crontab — vendas_custo_cmv / catalog sync).
"""
import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sincroniza catálogo do Bling (sync_products + rebuild_variants_from_products)"

    def add_arguments(self, parser):
        parser.add_argument("--limit-per-page", type=int, default=50)

    def handle(self, *args, **options):
        from apps.produtos.services.bling.sync import sync_products
        from apps.produtos.services.business.catalog import rebuild_variants_from_products

        started_at = int(time.time())
        out = {
            "started_at": started_at,
            "sync": {},
            "rebuild": {},
            "ok": False,
            "error": None,
        }

        try:
            out["sync"] = sync_products(limit_per_page=options["limit_per_page"])
            out["rebuild"] = rebuild_variants_from_products()
            out["ok"] = True
        except Exception as e:  # noqa: BLE001 — registramos e retornamos status
            out["error"] = str(e)

        out["finished_at"] = int(time.time())
        out["duration_sec"] = int(out["finished_at"] - started_at)

        db_path = Path(getattr(settings, "PRODUTOS_DB_PATH", ""))
        if db_path:
            log_file = db_path.parent / "sync_catalog_cron.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(out, ensure_ascii=False) + "\n")

        self.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
        if not out["ok"]:
            raise SystemExit(1)
