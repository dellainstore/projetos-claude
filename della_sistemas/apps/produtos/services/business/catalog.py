import re
import time
from typing import Dict, Any

from apps.produtos.services.db import get_conn

PATTERN = re.compile(r"^(?P<base>.+?)\s*\((?P<color>[^()]*)\)\s*\((?P<size>[^()]*)\)\s*$")


def _now() -> int:
    return int(time.time())


def _norm(s: str) -> str:
    return (s or "").strip().upper()


def parse_name(name: str) -> Dict[str, Any]:
    name = (name or "").strip()
    m = PATTERN.match(name)
    if not m:
        return {"base_name": name, "color": None, "size": None, "ok": False}

    base = _norm(m.group("base"))
    color = _norm(m.group("color"))
    size = _norm(m.group("size"))

    if not base or not color or not size:
        return {"base_name": base or name, "color": color or None, "size": size or None, "ok": False}

    return {"base_name": base, "color": color, "size": size, "ok": True}


def rebuild_variants_from_products() -> Dict[str, Any]:
    """
    Reconstrói variants_cache a partir do products_cache.name e products_cache.situation.

    Regras:
    - active=1 apenas se situation=='A'
    - SKU duplicado: escolhe o "melhor" registro:
        1) ativo vence inativo
        2) se empate, maior updated_at vence
        3) se ainda empate, maior bling_product_id vence
    """
    conn = get_conn()
    cur = conn.cursor()

    # Detecta se products_cache tem updated_at
    cols = [r[1] for r in cur.execute("PRAGMA table_info(products_cache)").fetchall()]
    has_updated_at = "updated_at" in cols

    if has_updated_at:
        rows = cur.execute("""
            SELECT bling_product_id, name, code, situation, updated_at
            FROM products_cache
        """).fetchall()
    else:
        rows = cur.execute("""
            SELECT bling_product_id, name, code, situation
            FROM products_cache
        """).fetchall()

    inserted = 0
    parsed_ok = 0
    parsed_fail = 0
    no_sku = 0
    dedup_wins = 0

    # Reconstrói do zero
    cur.execute("DELETE FROM variants_cache")
    conn.commit()

    now = _now()

    # Mantém "melhor por SKU" em memória pra decidir antes de gravar
    best_by_sku: dict[str, dict[str, Any]] = {}

    for row in rows:
        if has_updated_at:
            bling_product_id, name, sku, situation, updated_at = row
            updated_at = int(updated_at or 0)
        else:
            bling_product_id, name, sku, situation = row
            updated_at = 0

        sku = (str(sku).strip() if sku is not None else "")
        if not sku:
            no_sku += 1
            continue

        p = parse_name(name or "")
        ok = bool(p["ok"])

        base = _norm(p["base_name"]) if ok else _norm(name or "")
        color = p["color"] if ok else None
        size = p["size"] if ok else None

        sit = (str(situation).strip().upper() if situation is not None else "")
        active = 1 if sit == "A" else 0

        if ok:
            parsed_ok += 1
        else:
            parsed_fail += 1

        cand = {
            "sku": sku,
            "bling_product_id": int(bling_product_id),
            "product_name": str(name or ""),
            "base_name": base,
            "color_key": color,
            "size_key": size,
            "active": int(active),
            "updated_at_src": updated_at,
        }

        prev = best_by_sku.get(sku)
        if prev is None:
            best_by_sku[sku] = cand
        else:
            # Regra de vitória:
            # 1) ativo vence
            if cand["active"] > prev["active"]:
                best_by_sku[sku] = cand
                dedup_wins += 1
            elif cand["active"] < prev["active"]:
                continue
            else:
                # 2) updated_at maior vence
                if cand["updated_at_src"] > prev["updated_at_src"]:
                    best_by_sku[sku] = cand
                    dedup_wins += 1
                elif cand["updated_at_src"] < prev["updated_at_src"]:
                    continue
                else:
                    # 3) id maior vence
                    if cand["bling_product_id"] > prev["bling_product_id"]:
                        best_by_sku[sku] = cand
                        dedup_wins += 1

    # Agora grava só 1 por SKU
    for sku, v in best_by_sku.items():
        cur.execute("""
            INSERT INTO variants_cache
            (sku, bling_product_id, product_name, base_name, color_key, size_key, active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            v["sku"],
            v["bling_product_id"],
            v["product_name"],
            v["base_name"],
            v["color_key"],
            v["size_key"],
            v["active"],
            now
        ))
        inserted += 1

    conn.commit()
    conn.close()

    return {
        "inserted": inserted,
        "parsed_ok": parsed_ok,
        "parsed_fail": parsed_fail,
        "no_sku": no_sku,
        "dedup_wins": dedup_wins,
    }
