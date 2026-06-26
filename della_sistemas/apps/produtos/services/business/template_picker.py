from apps.produtos.services.normalizer import parse_name
from apps.produtos.services.db import get_conn
from apps.produtos.services.business.lookup import normalize_search_text


def get_default_template_for_base(base: str) -> dict | None:
    """Retorna o template mais recente para um base_name: sku, id, nome e cor (sem tamanho)."""
    base = (base or "").strip().upper()
    if not base:
        return None
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT sku, bling_product_id, product_name, COALESCE(base_name, '') AS base_name, color_key
        FROM variants_cache
        WHERE base_name = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (base,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "sku": row[0],
        "id": int(row[1]),
        "name": row[2],
        "base_name": row[3],
        "color": row[4] or "",
    }


def format_template_label(tpl: dict) -> str:
    """Formato de exibição: SKU — NOME (COR)"""
    parts = [tpl.get("sku") or ""]
    base = (tpl.get("base_name") or tpl.get("name") or "").strip()
    color = (tpl.get("color") or "").strip()
    if base and color:
        parts.append(f"{base} ({color})")
    elif base:
        parts.append(base)
    return " — ".join(p for p in parts if p)


def search_templates(term: str, limit: int = 20, group_mode: str = "base") -> list[dict]:
    raw_term = (term or "").strip()
    term_norm = normalize_search_text(raw_term)
    if not term_norm:
        return []
    raw_upper = raw_term.upper()

    conn = get_conn()
    cur = conn.cursor()

    # Busca ampla e prioriza base_name para não "sumir" com modelos irmãos
    rows = cur.execute(
        """
        SELECT
            v.sku,
            v.bling_product_id,
            v.product_name,
            COALESCE(v.base_name, '') as base_name,
            CASE
                WHEN UPPER(COALESCE(v.base_name,'')) = ? THEN 0
                WHEN UPPER(COALESCE(v.base_name,'')) LIKE ? THEN 1
                WHEN UPPER(v.product_name) LIKE ? THEN 2
                WHEN UPPER(v.sku) LIKE ? THEN 3
                ELSE 9
            END AS rank_match,
            v.updated_at
        FROM variants_cache v
        WHERE UPPER(v.sku) LIKE ?
           OR UPPER(v.product_name) LIKE ?
           OR UPPER(COALESCE(v.base_name,'')) LIKE ?
           OR UPPER(v.sku) LIKE ?
           OR UPPER(v.product_name) LIKE ?
           OR UPPER(COALESCE(v.base_name,'')) LIKE ?
        ORDER BY rank_match ASC, v.updated_at DESC
        LIMIT 400
        """,
        (
            raw_upper,
            f"{raw_upper}%",
            f"%{raw_upper}%",
            f"%{raw_upper}%",
            f"%{raw_upper}%",
            f"%{raw_upper}%",
            f"%{raw_upper}%",
            f"%{term_norm}%",
            f"%{term_norm}%",
            f"%{term_norm}%",
        ),
    ).fetchall()
    conn.close()

    seen_groups = set()
    selected = []
    for sku, pid, name, base_name, rank_match, updated_at in rows:
        bn = (base_name or "").strip().upper()
        parsed = parse_name(name or "")
        color = (parsed.get("color") or "").strip().upper()
        size = (parsed.get("size") or "").strip().upper()
        norm_fields = [
            normalize_search_text(bn),
            normalize_search_text(name),
            normalize_search_text(sku),
            normalize_search_text(color),
            normalize_search_text(size),
        ]
        if term_norm not in " ".join(part for part in norm_fields if part):
            continue
        if group_mode == "base_color":
            key = (bn or parsed.get("base_name") or name.strip().upper(), color or "-")
        else:
            key = (bn or name.strip().upper(),)
        if key in seen_groups:
            continue
        seen_groups.add(key)
        selected.append(
            {
                "sku": sku,
                "id": int(pid),
                "name": name,
                "base_name": bn,
                "color": color or None,
                "size": size or None,
            }
        )
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        seen_ids = {x["id"] for x in selected}
        for sku, pid, name, base_name, rank_match, updated_at in rows:
            if int(pid) in seen_ids:
                continue
            bn = (base_name or "").strip().upper()
            parsed = parse_name(name or "")
            color = (parsed.get("color") or "").strip().upper()
            size = (parsed.get("size") or "").strip().upper()
            norm_fields = [
                normalize_search_text(bn),
                normalize_search_text(name),
                normalize_search_text(sku),
                normalize_search_text(color),
                normalize_search_text(size),
            ]
            if term_norm not in " ".join(part for part in norm_fields if part):
                continue
            selected.append(
                {
                    "sku": sku,
                    "id": int(pid),
                    "name": name,
                    "base_name": bn,
                    "color": color or None,
                    "size": size or None,
                }
            )
            if len(selected) >= limit:
                break

    return selected
