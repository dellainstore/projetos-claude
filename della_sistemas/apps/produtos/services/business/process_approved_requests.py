import json
import time
from typing import Any

from apps.produtos.services.bling.products import atualizar_produto_patch, criar_produto, get_produto
from apps.produtos.services.bling.api import bling_request_raw
from apps.produtos.services.db import get_conn
from apps.produtos.services.business.pricing import extract_prices
from apps.produtos.services.business.suppliers import normalize_supplier_name, get_or_create_bling_supplier
from apps.produtos.services.precos import atualizar_custo_bling


def _vincular_custo_bling(bling_id: int, price_custo: float, supplier_name: str, sku: str = "") -> bool:
    """
    Vincula fornecedor e define precoCusto no Bling.
    Busca/cria o contato do fornecedor e usa POST /produtos/fornecedores.
    Fallback para atualizar_custo_bling se o GET já retornar um registro existente.
    """
    # Tenta PUT no registro existente primeiro
    if atualizar_custo_bling(bling_id, price_custo):
        return True

    # Não há registro de fornecedor — cria com o contato correto
    contato_id = get_or_create_bling_supplier(supplier_name) if supplier_name else None
    if not contato_id:
        return False

    payload: dict = {
        "produto":    {"id": bling_id},
        "fornecedor": {"id": contato_id},
        "codigo":     sku or "",
        "descricao":  "",
        "precoCusto": float(price_custo),
        "precoCompra": 0.0,
        "padrao":     True,
    }
    try:
        r = bling_request_raw("POST", "/produtos/fornecedores", json=payload, timeout=10)
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def _extract_sku_from_product(product_data: dict[str, Any]) -> str | None:
    for key in ("codigo", "code", "sku"):
        value = product_data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().upper()
    return None


def _build_patch_from_template(template_data: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "preco",
        "precoCusto",
        "precoCompra",
        "formato",
        "unidade",
        "tipo",
        "condicao",
        "fornecedor",
        "fornecedores",
        "tributacao",
        "camposCustomizados",
        "categoria",
        "marca",
        "descricaoComplementar",
    ]
    return {k: template_data.get(k) for k in fields if template_data.get(k) is not None}

def _build_price_enforcement_patch(
    template_data: dict[str, Any],
    *,
    price_varejo: float | None,
    price_custo: float | None,
) -> dict[str, Any]:
    """
    Alguns layouts do Bling aceitam custo em chaves diferentes.
    Envia custo em formatos alternativos para aumentar compatibilidade.
    """
    p: dict[str, Any] = {}
    if price_varejo is not None:
        p["preco"] = float(price_varejo)
    if price_custo is not None:
        p["precoCusto"] = float(price_custo)
        p["precoCompra"] = float(price_custo)
        supplier_patch = _build_suppliers_patch(template_data, price_custo=float(price_custo))
        p.update(supplier_patch)
    return p


def _build_suppliers_patch(
    template_data: dict[str, Any],
    *,
    price_custo: float | None = None,
) -> dict[str, Any]:
    """
    Bling pode trabalhar com `fornecedor` (objeto) ou `fornecedores` (lista).
    Replica estrutura do template para não perder vínculo na aba Fornecedores.
    """
    suppliers: list[dict[str, Any]] = []

    fornecedores_src = template_data.get("fornecedores")
    if isinstance(fornecedores_src, list):
        for row in fornecedores_src:
            if isinstance(row, dict):
                suppliers.append(dict(row))

    fornecedor_src = template_data.get("fornecedor")
    if isinstance(fornecedor_src, dict):
        suppliers.append(dict(fornecedor_src))
    elif isinstance(fornecedor_src, list):
        for row in fornecedor_src:
            if isinstance(row, dict):
                suppliers.append(dict(row))

    # Remove duplicatas óbvias por `id`/`codigo` para evitar payloads redundantes.
    dedup: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, str]] = set()
    for row in suppliers:
        contato = row.get("contato") if isinstance(row.get("contato"), dict) else {}
        key = (row.get("id"), contato.get("id"), str(row.get("codigo") or "").strip().upper())
        if key in seen:
            continue
        seen.add(key)
        if price_custo is not None:
            row["precoCusto"] = float(price_custo)
            row["precoCompra"] = float(price_custo)
        dedup.append(row)

    if not dedup:
        return {}

    patch: dict[str, Any] = {"fornecedores": dedup}
    if len(dedup) == 1:
        patch["fornecedor"] = dedup[0]
    return patch


def _find_variant(cur, base: str, color: str, size: str) -> tuple[str | None, int | None]:
    row = cur.execute(
        """
        SELECT sku, bling_product_id
        FROM variants_cache
        WHERE base_name = ?
          AND color_key = ?
          AND size_key = ?
        LIMIT 1
        """,
        (base, color, size),
    ).fetchone()
    if not row:
        return None, None
    return row[0], int(row[1])


def _auto_pick_template_id(cur, base: str) -> int | None:
    """Retorna o bling_product_id mais recente do mesmo base_name no cache (para nova cor em produto existente)."""
    row = cur.execute(
        """
        SELECT bling_product_id
        FROM variants_cache
        WHERE base_name = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (base,),
    ).fetchone()
    return int(row[0]) if row else None


def _find_recent_created_variant(cur, base: str, color: str, size: str) -> tuple[str | None, int | None]:
    row = cur.execute(
        """
        SELECT NULLIF(sku, ''), bling_product_id
        FROM stock_moves
        WHERE base_name = ?
          AND color_key = ?
          AND size_key = ?
          AND bling_product_id IS NOT NULL
        ORDER BY move_id DESC
        LIMIT 1
        """,
        (base, color, size),
    ).fetchone()
    if not row:
        return None, None
    return row[0], int(row[1])


def _enqueue_stock_move(
    cur,
    *,
    sku: str | None,
    bling_product_id: int,
    qty: int,
    base: str,
    color: str,
    size: str,
    supplier_name: str,
    requested_at: int,
    price_varejo: float | None = None,
    price_custo: float | None = None,
    price_atacado: float | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO stock_moves
        (sku, qty_delta, status, created_by, created_at, result_json,
         base_name, color_key, size_key, supplier_name, requested_at, bling_product_id,
         price_varejo, price_custo, price_atacado)
        VALUES (?, ?, 'PENDING', 'SYSTEM', ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sku or "",
            int(qty),
            requested_at,
            base,
            color,
            size,
            supplier_name,
            requested_at,
            int(bling_product_id),
            float(price_varejo) if price_varejo is not None else None,
            float(price_custo) if price_custo is not None else None,
            float(price_atacado) if price_atacado is not None else None,
        ),
    )


def processar_aprovacao(
    request_id: int,
    approved_by: str,
    items_override=None,
    base_override: str | None = None,
    template_id_override: int | None = None,
) -> dict[str, Any]:
    """Aprova e processa imediatamente um único request pendente."""
    conn = get_conn()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT payload_json, template_product_id FROM requests WHERE request_id=? AND status='PENDING'",
        (request_id,),
    ).fetchone()

    if not row:
        conn.close()
        return {"ok": 0, "error": 1}

    payload = json.loads(row["payload_json"] or "{}")
    if items_override:
        payload["items"] = items_override
    if base_override:
        payload["base"] = base_override.strip().upper()

    template_product_id = template_id_override or row["template_product_id"]

    now = int(time.time())
    cur.execute(
        "UPDATE requests SET status='APPROVED', approved_by=?, updated_at=?, payload_json=?, template_product_id=? WHERE request_id=?",
        (approved_by, now, json.dumps(payload, ensure_ascii=False), template_product_id, request_id),
    )
    conn.commit()
    conn.close()

    result = processar_requests_aprovados(limit=20)
    ok = result.get("created_products", 0) + result.get("skipped_existing", 0)
    return {"ok": ok, "error": len(result.get("errors", []))}


def processar_requests_aprovados(limit: int = 10) -> dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    stats = {
        "processed_requests": 0,
        "created_products": 0,
        "created_stock_moves": 0,
        "skipped_existing": 0,
        "errors": [],
    }

    rows = cur.execute(
        """
        SELECT request_id, payload_json, template_product_id
        FROM requests
        WHERE status='APPROVED'
        ORDER BY request_id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    for request_id, payload_json, template_product_id in rows:
        try:
            payload = json.loads(payload_json)
            base = (payload.get("base") or "").strip().upper()
            items = payload.get("items", [])
            if not base or not items:
                raise ValueError("Payload invalido (base ou items vazio).")

            template = {}
            patch_copy = {}
            template_prices = {"price_varejo": None, "price_custo": None, "price_atacado": None}

            resolved_template_id = template_product_id or _auto_pick_template_id(cur, base)

            if resolved_template_id:
                template = get_produto(int(resolved_template_id)).get("data", {})
                if not template:
                    raise RuntimeError("Falha ao carregar template do Bling.")
                patch_copy = _build_patch_from_template(template)
                template_prices = extract_prices(template or {})

            created = []
            skipped = []
            move_count = 0

            for it in items:
                color = str(it.get("color") or "").strip().upper()
                size = str(it.get("size") or "").strip().upper()
                qty = int(it.get("qty", 0))
                supplier_name = normalize_supplier_name(it.get("supplier_name") or "") or "NAO INFORMADA"
                if not color or not size or qty <= 0:
                    continue

                sku, bling_product_id = _find_variant(cur, base, color, size)
                if not bling_product_id:
                    sku, bling_product_id = _find_recent_created_variant(cur, base, color, size)

                if bling_product_id:
                    skipped.append(
                        {
                            "base": base,
                            "color": color,
                            "size": size,
                            "qty": qty,
                            "supplier_name": supplier_name,
                        }
                    )
                    stats["skipped_existing"] += 1
                else:
                    if not template:
                        raise ValueError("Template obrigatorio para criar nova variacao/modelo.")
                    nome = f"{base} ({color}) ({size})"
                    create_payload = {
                        "nome": nome,
                        "tipo": template.get("tipo") or "P",
                        "situacao": template.get("situacao") or "A",
                        "formato": template.get("formato") or "S",
                    }
                    if template.get("unidade"):
                        create_payload["unidade"] = template.get("unidade")
                    create_payload.update(
                        _build_suppliers_patch(
                            template,
                            price_custo=template_prices.get("price_custo"),
                        )
                    )
                    created_resp = criar_produto(create_payload)
                    new_id = (created_resp.get("data") or {}).get("id")
                    if not new_id:
                        raise RuntimeError(f"Criacao retornou sem id: {created_resp}")
                    atualizar_produto_patch(int(new_id), patch_copy)
                    # Varejo via PATCH normal
                    price_varejo = template_prices.get("price_varejo")
                    if price_varejo:
                        atualizar_produto_patch(int(new_id), {"preco": float(price_varejo)})
                    # Custo: tenta registro existente, senão cria vínculo com fornecedor
                    price_custo = template_prices.get("price_custo")
                    if price_custo:
                        _vincular_custo_bling(int(new_id), float(price_custo), supplier_name, sku or "")
                    bling_product_id = int(new_id)
                    created_product_data = get_produto(int(new_id)).get("data", {}) or {}
                    sku = _extract_sku_from_product(created_product_data)
                    created.append(
                        {
                            "base": base,
                            "color": color,
                            "size": size,
                            "qty": qty,
                            "supplier_name": supplier_name,
                            "sku": sku,
                            "bling_product_id": bling_product_id,
                        }
                    )
                    stats["created_products"] += 1

                _enqueue_stock_move(
                    cur,
                    sku=sku,
                    bling_product_id=int(bling_product_id),
                    qty=qty,
                    base=base,
                    color=color,
                    size=size,
                    supplier_name=supplier_name,
                    requested_at=int(time.time()),
                    price_varejo=template_prices.get("price_varejo"),
                    price_custo=template_prices.get("price_custo"),
                    price_atacado=template_prices.get("price_atacado"),
                )
                move_count += 1
                stats["created_stock_moves"] += 1

            now = int(time.time())
            cur.execute(
                """
                UPDATE requests
                SET status='IMPLEMENTED',
                    result_json=?,
                    updated_at=?
                WHERE request_id=?
                """,
                (
                    json.dumps(
                        {
                            "template_id": int(template_product_id) if template_product_id else None,
                            "created": created,
                            "skipped": skipped,
                            "stock_moves_created": move_count,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                    request_id,
                ),
            )
            conn.commit()
            stats["processed_requests"] += 1

        except Exception as e:
            now = int(time.time())
            stats["errors"].append({"request_id": request_id, "error": str(e)})
            cur.execute(
                """
                UPDATE requests
                SET status='ERROR',
                    result_json=?,
                    updated_at=?
                WHERE request_id=?
                """,
                (json.dumps({"error": str(e)}, ensure_ascii=False), now, request_id),
            )
            conn.commit()

    conn.close()
    return stats
