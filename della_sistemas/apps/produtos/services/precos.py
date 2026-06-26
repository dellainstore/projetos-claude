"""
Serviço de gerenciamento de preços (varejo, custo, atacado).

Fluxo:
  listar_modelos()              → distinct base_names do catálogo
  listar_cores_com_precos(base) → uma linha por cor com os 3 preços atuais do Bling
  aplicar_precos(...)           → PATCH no Bling + grava price_history
  historico_precos(...)         → paginado com filtros
  tentar_atacado_bling(...)     → tenta PUT na lista ATACADO; retorna (ok, msg, csv_rows)
"""

from __future__ import annotations

import csv
import io
import json
import threading
import time
import uuid
from typing import Any

from apps.produtos.services.db import get_conn
from apps.produtos.services.bling.api import (
    bling_get,
    bling_patch,
    bling_post,
    bling_request_raw,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        f = float(v)
        return f if f > 0 else None
    except Exception:
        return None


def _prices_equal(a: float | None, b: float | None) -> bool:
    """True when two prices are effectively the same (within R$0.01 rounding)."""
    if a is None or b is None:
        return False
    return round(a, 2) == round(b, 2)


def _fetch_ultimos_atacados_local(skus: list[str]) -> dict[str, float]:
    """Returns {sku_upper: last_known_atacado} from price_history for the given SKUs."""
    if not skus:
        return {}
    upper_skus = [s.upper() for s in skus]
    placeholders = ",".join("?" * len(upper_skus))
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT ph.sku, ph.valor_novo
        FROM price_history ph
        INNER JOIN (
            SELECT UPPER(sku) as su, MAX(alterado_em) as max_ts
            FROM price_history
            WHERE UPPER(sku) IN ({placeholders})
              AND tipo IN ('atacado', 'atacado_local')
            GROUP BY UPPER(sku)
        ) latest ON UPPER(ph.sku) = latest.su AND ph.alterado_em = latest.max_ts
        WHERE ph.tipo IN ('atacado', 'atacado_local')
    """, upper_skus).fetchall()
    conn.close()
    return {row[0].upper(): float(row[1]) for row in rows if row[1]}


def _now() -> int:
    return int(time.time())


# ─────────────────────────────────────────────────────────────────────────────
# Custo via /produtos/fornecedores (endpoint correto confirmado com Bling)
# ─────────────────────────────────────────────────────────────────────────────

def atualizar_custo_bling(bling_id: int, novo_custo: float) -> bool:
    """
    Atualiza precoCusto via GET /produtos/fornecedores?idProduto={id}
    seguido de PUT /produtos/fornecedores/{idProdutoFornecedor}.
    Se não houver fornecedor vinculado, cria via POST.
    Retorna True se sucesso.
    """
    try:
        resp = bling_get("/produtos/fornecedores", params={"idProduto": bling_id}, timeout=10, retries=1)
        registros = resp.get("data") or []

        if registros:
            reg = registros[0]
            id_pf = reg["id"]
            payload = {
                "produto":    {"id": bling_id},
                "fornecedor": {"id": reg.get("fornecedor", {}).get("id", 0)},
                "descricao":  reg.get("descricao", ""),
                "codigo":     reg.get("codigo", ""),
                "precoCusto": float(novo_custo),
                "precoCompra": reg.get("precoCompra", 0),
                "padrao":     reg.get("padrao", True),
            }
            r = bling_request_raw("PUT", f"/produtos/fornecedores/{id_pf}", json=payload, timeout=10)
            return r.status_code in (200, 201, 204)
        else:
            # Produto sem fornecedor — cria registro mínimo
            payload = {
                "produto":    {"id": bling_id},
                "fornecedor": {"id": 0},
                "precoCusto": float(novo_custo),
                "precoCompra": 0.0,
                "padrao":     True,
            }
            r = bling_request_raw("POST", "/produtos/fornecedores", json=payload, timeout=10)
            return r.status_code in (200, 201, 204)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Inicialização da tabela de histórico
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_price_history_table() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            base_name    TEXT    NOT NULL,
            color_key    TEXT    NOT NULL,
            sku          TEXT,
            bling_id     INTEGER,
            tipo         TEXT    NOT NULL,   -- varejo | custo | atacado | atacado_local
            valor_antes  REAL,
            valor_novo   REAL    NOT NULL,
            usuario      TEXT    NOT NULL,
            alterado_em  INTEGER NOT NULL,   -- unix timestamp
            exportado_em INTEGER             -- unix timestamp, NULL = ainda não exportado
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_base    ON price_history(base_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_cor     ON price_history(color_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_quando  ON price_history(alterado_em DESC)")
    # Migração: adiciona exportado_em se não existir
    try:
        conn.execute("ALTER TABLE price_history ADD COLUMN exportado_em INTEGER")
    except Exception:
        pass
    conn.commit()
    conn.close()


_ensure_price_history_table()


# ─────────────────────────────────────────────────────────────────────────────
# Jobs de preço (processamento em background com progresso)
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_price_jobs_table() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_jobs (
            job_id       TEXT    PRIMARY KEY,
            status       TEXT    NOT NULL DEFAULT 'pending',
            total        INTEGER NOT NULL DEFAULT 0,
            feitos       INTEGER NOT NULL DEFAULT 0,
            ok           INTEGER NOT NULL DEFAULT 0,
            skip         INTEGER NOT NULL DEFAULT 0,
            erros        TEXT    NOT NULL DEFAULT '[]',
            avisos       TEXT    NOT NULL DEFAULT '[]',
            csv_atacado  TEXT,
            criado_em    INTEGER NOT NULL,
            concluido_em INTEGER
        )
    """)
    conn.commit()
    conn.close()


_ensure_price_jobs_table()


def get_job(job_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT job_id,status,total,feitos,ok,skip,erros,avisos,csv_atacado,criado_em,concluido_em FROM price_jobs WHERE job_id=?",
        (job_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "job_id": row[0], "status": row[1],
        "total": row[2], "feitos": row[3],
        "ok": row[4], "skip": row[5],
        "erros": json.loads(row[6] or "[]"),
        "avisos": json.loads(row[7] or "[]"),
        "csv_atacado": row[8],
        "criado_em": row[9], "concluido_em": row[10],
    }


def _atualizar_job(job_id: str, **kwargs) -> None:
    if not kwargs:
        return
    for k in ("erros", "avisos"):
        if k in kwargs and isinstance(kwargs[k], list):
            kwargs[k] = json.dumps(kwargs[k], ensure_ascii=False)
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    conn = get_conn()
    conn.execute(f"UPDATE price_jobs SET {sets} WHERE job_id = ?", vals)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo / modelos
# ─────────────────────────────────────────────────────────────────────────────

def listar_modelos() -> list[str]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT base_name
        FROM variants_cache
        WHERE active = 1 AND base_name IS NOT NULL AND color_key IS NOT NULL
        ORDER BY base_name COLLATE NOCASE
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def listar_cores_por_modelo(base_name: str) -> list[dict]:
    """
    Retorna uma linha por COR com um produto representativo.
    Os preços são lidos do Bling via API em paralelo; atacado usa fallback local.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    conn = get_conn()
    rows = conn.execute("""
        SELECT color_key, sku, bling_product_id
        FROM variants_cache
        WHERE UPPER(base_name) = UPPER(?)
          AND active = 1
          AND color_key IS NOT NULL
        GROUP BY color_key
        ORDER BY color_key COLLATE NOCASE
    """, (base_name,)).fetchall()

    # Busca preços de atacado locais (importados via Excel) para esses SKUs
    local_atacado: dict[str, float] = {}
    if rows:
        skus = [r[1] for r in rows if r[1]]
        placeholders = ",".join("?" * len(skus))
        ph_rows = conn.execute(f"""
            SELECT ph.sku, ph.valor_novo
            FROM price_history ph
            INNER JOIN (
                SELECT UPPER(sku) as sku_upper, MAX(alterado_em) as max_ts
                FROM price_history
                WHERE UPPER(sku) IN ({placeholders})
                  AND tipo IN ('atacado', 'atacado_local')
                GROUP BY UPPER(sku)
            ) latest ON UPPER(ph.sku) = latest.sku_upper AND ph.alterado_em = latest.max_ts
            WHERE ph.tipo IN ('atacado', 'atacado_local')
        """, [s.upper() for s in skus]).fetchall()
        for ph_sku, ph_valor in ph_rows:
            if ph_valor:
                local_atacado[ph_sku.upper()] = float(ph_valor)
    conn.close()

    def _fetch(row):
        color_key, sku, bling_id = row
        precos = _fetch_precos_bling(int(bling_id))
        atacado = precos.get("atacado") or local_atacado.get((sku or "").upper())
        return {
            "color_key": color_key,
            "sku": sku,
            "bling_id": bling_id,
            "varejo": precos.get("varejo"),
            "custo": precos.get("custo"),
            "atacado": atacado,
        }

    resultado = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_fetch, row) for row in rows]
        for fut in as_completed(futures):
            resultado.append(fut.result())

    resultado.sort(key=lambda x: (x["varejo"] is None, x["varejo"] or 0, x["color_key"]))
    return resultado


def _fetch_precos_bling(bling_id: int) -> dict[str, float | None]:
    try:
        data = bling_get(f"/produtos/{bling_id}").get("data") or {}
        varejo = _to_float(data.get("preco"))

        # Custo: tenta precoCusto direto, depois fornecedores
        custo = _to_float(data.get("precoCusto")) or _to_float(data.get("precoCompra"))
        if custo is None:
            for forn_key in ("fornecedor", "fornecedores"):
                forn = data.get(forn_key)
                if isinstance(forn, dict):
                    custo = _to_float(forn.get("precoCusto")) or _to_float(forn.get("precoCompra"))
                elif isinstance(forn, list):
                    for row in forn:
                        custo = _to_float(row.get("precoCusto")) or _to_float(row.get("precoCompra"))
                        if custo:
                            break
                if custo:
                    break

        # Atacado: tenta lista de preços inline
        atacado = _to_float(data.get("precoAtacado"))
        if not atacado:
            for lista_key in ("listaPreco", "listasPreco", "precos"):
                listas = data.get(lista_key)
                if isinstance(listas, list):
                    for row in listas:
                        label = str(
                            row.get("nome") or (row.get("listaPreco") or {}).get("nome") or ""
                        ).upper()
                        if "ATAC" in label:
                            atacado = _to_float(row.get("preco") or row.get("valor"))
                            if atacado:
                                break
                if atacado:
                    break

        # Atacado fallback: endpoint de preços do produto
        if not atacado:
            atacado = _fetch_atacado_endpoint(bling_id)

        return {"varejo": varejo, "custo": custo, "atacado": atacado}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Falha ao buscar preços Bling id=%s: %s", bling_id, exc)
        return {"varejo": None, "custo": None, "atacado": None}


def _fetch_atacado_endpoint(bling_id: int) -> float | None:
    try:
        resp = bling_get(f"/produtos/{bling_id}/precos", timeout=8, retries=0)
        data = resp if isinstance(resp, list) else (resp.get("data") or [])
        if not isinstance(data, list):
            data = [data]
        lista_map = _get_lista_precos_map()
        for row in data:
            if not isinstance(row, dict):
                continue
            # Tenta identificar pelo nome direto
            label = str(
                row.get("nome") or (row.get("listaPreco") or {}).get("nome") or ""
            ).upper()
            if "ATAC" not in label:
                # Tenta pelo id da lista
                lid = row.get("idListaPreco") or (row.get("listaPreco") or {}).get("id")
                if lid:
                    label = lista_map.get(int(lid), "")
            if "ATAC" in label:
                v = _to_float(row.get("preco") or row.get("valor"))
                if v:
                    return v
    except Exception:
        pass
    return None


_lista_precos_cache: dict = {"ts": 0, "map": {}}


def _get_lista_precos_map() -> dict[int, str]:
    now = time.time()
    if now - _lista_precos_cache["ts"] < 300 and _lista_precos_cache["map"]:
        return _lista_precos_cache["map"]
    out: dict[int, str] = {}
    try:
        resp = bling_get("/listas-precos", params={"pagina": 1, "limite": 100}, timeout=8, retries=0)
        data = resp.get("data") if isinstance(resp, dict) else []
        if isinstance(data, list):
            for row in data:
                lid = row.get("id")
                nome = str(row.get("nome") or "").strip().upper()
                if lid and nome:
                    out[int(lid)] = nome
    except Exception:
        pass
    _lista_precos_cache["ts"] = now
    _lista_precos_cache["map"] = out
    return out


def get_lista_atacado_id() -> int | None:
    for lid, nome in _get_lista_precos_map().items():
        if "ATAC" in nome:
            return lid
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SKUs por cor (para update em massa)
# ─────────────────────────────────────────────────────────────────────────────

def listar_skus_por_cor(base_name: str, color_keys: list[str]) -> list[dict]:
    if not color_keys:
        return []
    placeholders = ",".join("?" * len(color_keys))
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT sku, bling_product_id, color_key, size_key
        FROM variants_cache
        WHERE UPPER(base_name) = UPPER(?)
          AND UPPER(color_key) IN ({placeholders})
          AND active = 1
    """, (base_name, *[c.upper() for c in color_keys])).fetchall()
    conn.close()
    return [
        {"sku": r[0], "bling_id": r[1], "color_key": r[2], "size_key": r[3]}
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Aplicar preços
# ─────────────────────────────────────────────────────────────────────────────

def aplicar_precos(
    *,
    base_name: str,
    color_keys: list[str],
    varejo: float | None,
    custo: float | None,
    atacado: float | None,
    usuario: str,
    job_id: str | None = None,
) -> dict:
    """
    Atualiza preços no Bling para todos os SKUs das cores selecionadas.
    Pula chamadas à API quando o preço já é igual ao atual (evita timeout).
    Se job_id fornecido, atualiza progresso no DB a cada SKU processado.
    Retorna resumo: {ok, skip, erros, avisos, csv_atacado}
    """
    skus = listar_skus_por_cor(base_name, color_keys)
    if not skus:
        resultado = {"ok": 0, "skip": 0, "erros": ["Nenhum SKU encontrado para as cores selecionadas."], "avisos": [], "csv_atacado": None}
        if job_id:
            _atualizar_job(job_id, status="done", concluido_em=_now(), erros=resultado["erros"])
        return resultado

    num_tipos = sum([varejo is not None, custo is not None, atacado is not None])
    total_ops = len(skus) * num_tipos

    if job_id:
        _atualizar_job(job_id, status="running", total=total_ops)

    ok_count = 0
    skip_count = 0
    feitos = 0
    erros: list[str] = []
    avisos: list[str] = []
    csv_rows: list[dict] = []
    now = _now()

    precos_atuais: dict[str, dict] = {}
    lista_atacado_id = get_lista_atacado_id()
    todos_skus = [item["sku"] for item in skus if item["sku"]]
    ultimos_atacados = _fetch_ultimos_atacados_local(todos_skus) if atacado is not None else {}

    def _flush_progresso():
        if job_id:
            _atualizar_job(job_id, feitos=feitos, ok=ok_count, skip=skip_count, erros=erros)

    for item in skus:
        bling_id = item["bling_id"]
        color = item["color_key"]
        sku = item["sku"]

        if color not in precos_atuais:
            precos_atuais[color] = _fetch_precos_bling(bling_id)
        antes = precos_atuais[color]

        # Varejo: PATCH /produtos/{id} — pula se já é o mesmo preço
        if varejo is not None:
            if _prices_equal(varejo, antes.get("varejo")):
                skip_count += 1
            else:
                try:
                    bling_patch(f"/produtos/{bling_id}", json={"preco": varejo}, timeout=15, retries=2)
                    ok_count += 1
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO price_history (base_name,color_key,sku,bling_id,tipo,valor_antes,valor_novo,usuario,alterado_em) VALUES (?,?,?,?,?,?,?,?,?)",
                        (base_name.upper(), color, sku, bling_id, "varejo", antes.get("varejo"), varejo, usuario, now),
                    )
                    conn.commit()
                    conn.close()
                except Exception as e:
                    erros.append(f"SKU {sku} (varejo): {e}")
            feitos += 1
            _flush_progresso()

        # Custo: PUT /produtos/fornecedores — pula se já é o mesmo preço
        if custo is not None:
            if _prices_equal(custo, antes.get("custo")):
                skip_count += 1
            else:
                if atualizar_custo_bling(bling_id, custo):
                    ok_count += 1
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO price_history (base_name,color_key,sku,bling_id,tipo,valor_antes,valor_novo,usuario,alterado_em) VALUES (?,?,?,?,?,?,?,?,?)",
                        (base_name.upper(), color, sku, bling_id, "custo", antes.get("custo"), custo, usuario, now),
                    )
                    conn.commit()
                    conn.close()
                else:
                    erros.append(f"SKU {sku}: falha ao atualizar custo no Bling.")
            feitos += 1
            _flush_progresso()

        # Atacado — armazena localmente e gera CSV para importar no Bling (API não suportada)
        if atacado is not None:
            ultimo_local = ultimos_atacados.get((sku or "").upper())
            if _prices_equal(atacado, ultimo_local):
                skip_count += 1
            else:
                csv_rows.append({
                    "sku": sku,
                    "bling_id": bling_id,
                    "color_key": color,
                    "size_key": item["size_key"],
                    "atacado": atacado,
                })
                ok_count += 1
                conn = get_conn()
                conn.execute(
                    "INSERT INTO price_history (base_name,color_key,sku,bling_id,tipo,valor_antes,valor_novo,usuario,alterado_em) VALUES (?,?,?,?,?,?,?,?,?)",
                    (base_name.upper(), color, sku, bling_id, "atacado_local", antes.get("atacado"), atacado, usuario, now),
                )
                conn.commit()
                conn.close()
                ultimos_atacados[(sku or "").upper()] = atacado
            feitos += 1
            _flush_progresso()

    csv_atacado = _gerar_csv_atacado(csv_rows) if csv_rows else None

    if job_id:
        _atualizar_job(
            job_id,
            status="done",
            feitos=feitos,
            ok=ok_count,
            skip=skip_count,
            erros=erros,
            avisos=avisos,
            csv_atacado=csv_atacado,
            concluido_em=_now(),
        )

    return {"ok": ok_count, "skip": skip_count, "erros": erros, "avisos": avisos, "csv_atacado": csv_atacado}


def iniciar_job_precos(
    *,
    base_name: str,
    color_keys: list[str],
    varejo: float | None,
    custo: float | None,
    atacado: float | None,
    usuario: str,
) -> str:
    """Inicia aplicação de preços em background. Retorna job_id para polling."""
    job_id = uuid.uuid4().hex
    conn = get_conn()
    conn.execute(
        "INSERT INTO price_jobs (job_id,status,total,feitos,ok,skip,erros,avisos,criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
        (job_id, "pending", 0, 0, 0, 0, "[]", "[]", _now())
    )
    conn.commit()
    conn.close()

    def _worker():
        try:
            aplicar_precos(
                base_name=base_name,
                color_keys=color_keys,
                varejo=varejo,
                custo=custo,
                atacado=atacado,
                usuario=usuario,
                job_id=job_id,
            )
        except Exception as e:
            _atualizar_job(job_id, status="error", erros=[str(e)], concluido_em=_now())

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


def _tentar_atualizar_atacado(bling_id: int, preco: float, lista_id: int | None) -> dict:
    """Tenta atualizar o preço de atacado via API. Retorna {"ok": bool}."""
    if not lista_id:
        return {"ok": False}

    # Tenta PUT /listas-precos/{listaId}/produtos/{produtoId}
    for endpoint in [
        f"/listas-precos/{lista_id}/produtos/{bling_id}",
        f"/listas-precos/{lista_id}/itens/{bling_id}",
    ]:
        try:
            resp = bling_request_raw("PUT", endpoint, json={"preco": preco}, timeout=10)
            if resp.status_code in (200, 201, 204):
                return {"ok": True}
        except Exception:
            pass

    # Tenta PATCH
    try:
        resp = bling_request_raw("PATCH", f"/listas-precos/{lista_id}/produtos/{bling_id}",
                                  json={"preco": preco}, timeout=10)
        if resp.status_code in (200, 201, 204):
            return {"ok": True}
    except Exception:
        pass

    return {"ok": False}


def _gerar_csv_atacado(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["sku", "bling_id", "color_key", "size_key", "atacado"])
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r[k] for k in ["sku", "bling_id", "color_key", "size_key", "atacado"]})
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Histórico de preços
# ─────────────────────────────────────────────────────────────────────────────

def historico_precos(
    *,
    pagina: int = 1,
    por_pagina: int = 50,
    base_name: str = "",
    color_key: str = "",
    tipo: str = "",
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> dict:
    conditions = []
    params: list = []

    if start_ts is not None:
        conditions.append("alterado_em >= ?")
        params.append(start_ts)
    if end_ts is not None:
        conditions.append("alterado_em < ?")
        params.append(end_ts)
    if base_name:
        conditions.append("UPPER(base_name) LIKE UPPER(?)")
        params.append(f"%{base_name}%")
    if color_key:
        conditions.append("UPPER(color_key) LIKE UPPER(?)")
        params.append(f"%{color_key}%")
    if tipo:
        # "atacado" no filtro inclui registros locais também
        if tipo == "atacado":
            conditions.append("tipo IN ('atacado', 'atacado_local')")
        else:
            conditions.append("tipo = ?")
            params.append(tipo)
    else:
        # Sem filtro de tipo, mostra tudo exceto atacado_local duplicado — exibe como atacado
        pass

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (pagina - 1) * por_pagina

    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) FROM price_history {where}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT id, base_name, color_key, sku, tipo, valor_antes, valor_novo, usuario, alterado_em
        FROM price_history
        {where}
        ORDER BY alterado_em DESC
        LIMIT ? OFFSET ?
        """,
        [*params, por_pagina, offset],
    ).fetchall()
    conn.close()

    registros = [
        {
            "id": r[0],
            "base_name": r[1],
            "color_key": r[2],
            "sku": r[3],
            # normaliza atacado_local → atacado para exibição
            "tipo": "atacado" if r[4] == "atacado_local" else r[4],
            "valor_antes": r[5],
            "valor_novo": r[6],
            "usuario": r[7],
            "alterado_em": r[8],
        }
        for r in rows
    ]

    return {
        "registros": registros,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": max(1, -(-total // por_pagina)),
    }
