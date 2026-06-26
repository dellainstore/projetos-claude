import json
import time
import unicodedata

from apps.produtos.services.db import get_conn
from apps.produtos.services.business.suppliers import normalize_supplier_name

_SIZE_LETTER_ORDER = {"PP": 0, "P": 1, "M": 2, "G": 3, "GG": 4, "XGG": 5, "EXG": 5, "G1": 6, "G2": 7, "G3": 8, "G4": 9}


def _sort_size_key(s: str):
    upper = (s or "").strip().upper()
    if upper in _SIZE_LETTER_ORDER:
        return (0, _SIZE_LETTER_ORDER[upper], "")
    try:
        return (1, int(upper), "")
    except ValueError:
        return (2, 0, upper)


def normalize_search_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.strip().upper().split())


def search_base_names(query: str, limit: int = 30) -> list[str]:
    q_norm = normalize_search_text(query)
    if not q_norm:
        return []
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT DISTINCT base_name
        FROM variants_cache
        WHERE base_name IS NOT NULL
          AND active = 1
        ORDER BY base_name
        """,
    ).fetchall()
    conn.close()
    matches: list[str] = []
    seen: set[str] = set()
    for (base_name,) in rows:
        if not base_name:
            continue
        key = normalize_search_text(base_name)
        if q_norm not in key or base_name in seen:
            continue
        seen.add(base_name)
        matches.append(base_name)
        if len(matches) >= int(limit):
            break
    return matches


def _pending_items_for_base(cur, base_name: str) -> list[dict]:
    rows = cur.execute(
        """
        SELECT payload_json
        FROM requests
        WHERE status IN ('PENDING', 'APPROVED')
          AND type IN ('NEW_VARIANT', 'UPSERT_VARIANT')
        ORDER BY request_id DESC
        """,
    ).fetchall()
    out = []
    base_upper = (base_name or "").strip().upper()
    for (payload_json,) in rows:
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            continue
        pbase = (payload.get("base") or "").strip().upper()
        if pbase != base_upper:
            continue
        for it in payload.get("items", []):
            color = str(it.get("color") or "").strip().upper()
            size = str(it.get("size") or "").strip().upper()
            if color and size:
                out.append(it)
    return out


def get_colors(base_name: str) -> list[str]:
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT DISTINCT color_key
        FROM variants_cache
        WHERE base_name = ?
          AND active = 1
          AND color_key IS NOT NULL
        ORDER BY color_key
        """,
        (base_name,),
    ).fetchall()
    colors = {r[0] for r in rows if r[0]}
    for it in _pending_items_for_base(cur, base_name):
        c = str(it.get("color") or "").strip().upper()
        if c:
            colors.add(c)
    conn.close()
    return sorted(colors)


def get_sizes(base_name: str, color: str) -> list[str]:
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT DISTINCT size_key
        FROM variants_cache
        WHERE base_name = ?
          AND color_key = ?
          AND active = 1
          AND size_key IS NOT NULL
        ORDER BY size_key
        """,
        (base_name, color),
    ).fetchall()
    sizes = {r[0] for r in rows if r[0]}
    color_upper = (color or "").strip().upper()
    for it in _pending_items_for_base(cur, base_name):
        c = str(it.get("color") or "").strip().upper()
        s = str(it.get("size") or "").strip().upper()
        if c == color_upper and s:
            sizes.add(s)
    conn.close()
    return sorted(sizes, key=_sort_size_key)


def get_sku(base_name: str, color: str, size: str) -> str | None:
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT sku
        FROM variants_cache
        WHERE base_name = ?
          AND color_key = ?
          AND size_key = ?
          AND active = 1
        LIMIT 1
        """,
        (base_name, color, size),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def upsert_pending_variant_request(
    *,
    base: str,
    color: str,
    size: str,
    qty: int,
    supplier_name: str,
    request_type: str = "NEW_VARIANT",
    template_product_id: int | None = None,
    created_by: str = "OP",
    conn=None,
) -> dict:
    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()
    cur = conn.cursor()
    base = (base or "").strip().upper()
    color = (color or "").strip().upper()
    size = (size or "").strip().upper()
    supplier_name = normalize_supplier_name(supplier_name) or "NAO INFORMADA"
    qty = int(qty)

    rows = cur.execute(
        """
        SELECT request_id, payload_json, status, template_product_id, type
        FROM requests
        WHERE type=?
          AND status IN ('PENDING', 'APPROVED')
        ORDER BY request_id ASC
        """,
        (request_type,),
    ).fetchall()

    for request_id, payload_json, status, req_template_id, req_type in rows:
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            continue
        if (payload.get("base") or "").strip().upper() != base:
            continue

        items = payload.get("items", [])
        for item in items:
            if (
                str(item.get("color") or "").strip().upper() == color
                and str(item.get("size") or "").strip().upper() == size
                and normalize_supplier_name(item.get("supplier_name") or "") == supplier_name
            ):
                item["qty"] = int(item.get("qty") or 0) + qty
                now = int(time.time())
                if template_product_id and not req_template_id:
                    cur.execute(
                        """
                        UPDATE requests
                        SET payload_json=?, updated_at=?, template_product_id=?
                        WHERE request_id=?
                        """,
                        (json.dumps(payload, ensure_ascii=False), now, int(template_product_id), int(request_id)),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE requests
                        SET payload_json=?, updated_at=?
                        WHERE request_id=?
                        """,
                        (json.dumps(payload, ensure_ascii=False), now, int(request_id)),
                    )
                if owns_conn:
                    conn.commit()
                    conn.close()
                return {"action": "merged", "request_id": int(request_id), "status": status}

        items.append(
            {
                "base": base,
                "color": color,
                "size": size,
                "qty": qty,
                "supplier_name": supplier_name,
            }
        )
        payload["base"] = base
        payload["items"] = items
        now = int(time.time())
        if template_product_id and not req_template_id:
            cur.execute(
                """
                UPDATE requests
                SET payload_json=?, updated_at=?, template_product_id=?
                WHERE request_id=?
                """,
                (json.dumps(payload, ensure_ascii=False), now, int(template_product_id), int(request_id)),
            )
        else:
            cur.execute(
                """
                UPDATE requests
                SET payload_json=?, updated_at=?
                WHERE request_id=?
                """,
                (json.dumps(payload, ensure_ascii=False), now, int(request_id)),
            )
        if owns_conn:
            conn.commit()
            conn.close()
        return {"action": "merged", "request_id": int(request_id), "status": status}

    payload = {
        "base": base,
        "items": [
            {
                "base": base,
                "color": color,
                "size": size,
                "qty": qty,
                "supplier_name": supplier_name,
            }
        ],
    }
    now = int(time.time())
    cur.execute(
        """
        INSERT INTO requests (type, status, payload_json, created_by, approved_by, created_at, updated_at, notes, template_product_id)
        VALUES (?, 'PENDING', ?, ?, NULL, ?, ?, NULL, ?)
        """,
        (request_type, json.dumps(payload, ensure_ascii=False), created_by, now, now, template_product_id),
    )
    new_id = cur.lastrowid
    if owns_conn:
        conn.commit()
        conn.close()
    return {"action": "created", "request_id": int(new_id), "status": "PENDING"}
