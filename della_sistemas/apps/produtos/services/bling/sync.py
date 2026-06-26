import json
import time
from pathlib import Path

from apps.produtos.services.bling.api import bling_get
from apps.produtos.services.db import get_conn

STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "sync_state.json"

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def sync_products(limit_per_page: int = 50, start_page: int | None = None) -> dict:
    """
    Sincroniza produtos do Bling para products_cache.
    - retry/backoff é feito no bling_get
    - checkpoint: salva última página concluída
    """
    conn = get_conn()
    cur = conn.cursor()

    inserted = 0
    updated = 0
    deleted = 0
    deleted_variants = 0
    now = int(time.time())

    state = _load_state()
    page = start_page if start_page is not None else int(state.get("products_last_page", 1))
    started_page = int(page)
    seen_ids: set[int] = set()

    pages_ok = 0

    while True:
        data = bling_get("/produtos", params={"pagina": page, "limite": limit_per_page}, timeout=30)
        items = data.get("data") or []
        if not items:
            # acabou
            _save_state({"products_last_page": 1})
            break

        for p in items:
            pid = p.get("id")
            if pid is None:
                continue
            pid = int(pid)
            seen_ids.add(pid)
            name = p.get("nome") or ""
            code = p.get("codigo")
            situation = p.get("situacao")
            ptype = p.get("tipo")
            pformat = p.get("formato")

            exists = cur.execute(
                "SELECT 1 FROM products_cache WHERE bling_product_id = ?",
                (pid,)
            ).fetchone()

            if exists:
                cur.execute("""
                    UPDATE products_cache
                    SET name=?, code=?, situation=?, type=?, format=?, updated_at=?
                    WHERE bling_product_id=?
                """, (name, code, situation, ptype, pformat, now, pid))
                updated += 1
            else:
                cur.execute("""
                    INSERT INTO products_cache
                    (bling_product_id, name, code, situation, type, format, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (pid, name, code, situation, ptype, pformat, now))
                inserted += 1

        conn.commit()
        pages_ok += 1

        # salva checkpoint: próxima página
        _save_state({"products_last_page": page + 1})

        page += 1

    # Se começou da página 1 e processou ao menos uma página,
    # remove do cache itens que não vieram mais no catálogo do Bling.
    if started_page == 1 and pages_ok > 0 and seen_ids:
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS _sync_seen_ids (id INTEGER PRIMARY KEY)")
        cur.execute("DELETE FROM _sync_seen_ids")
        cur.executemany(
            "INSERT OR IGNORE INTO _sync_seen_ids (id) VALUES (?)",
            [(pid,) for pid in seen_ids],
        )
        deleted_variants = cur.execute(
            """
            DELETE FROM variants_cache
            WHERE bling_product_id NOT IN (SELECT id FROM _sync_seen_ids)
            """
        ).rowcount
        deleted = cur.execute(
            """
            DELETE FROM products_cache
            WHERE bling_product_id NOT IN (SELECT id FROM _sync_seen_ids)
            """
        ).rowcount
        conn.commit()

    conn.close()
    return {
        "pages_ok": pages_ok,
        "last_page_saved": page,
        "inserted": inserted,
        "updated": updated,
        "deleted_variants": int(deleted_variants or 0),
        "deleted": int(deleted or 0),
        "pruned": bool(started_page == 1 and pages_ok > 0 and seen_ids),
        "limit": limit_per_page
    }
