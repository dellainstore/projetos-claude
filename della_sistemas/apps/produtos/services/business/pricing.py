from typing import Any
import time

from apps.produtos.services.bling.api import bling_get
from apps.produtos.services.bling.products import get_produto
from apps.produtos.services.db import get_conn

_PRICE_LIST_CACHE_TTL_SEC = 300
_price_list_name_cache: dict[str, Any] = {"ts": 0, "map": {}}
_product_atacado_cache: dict[int, tuple[float | None, float]] = {}


def _to_float(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _first_float(*values) -> float | None:
    for v in values:
        n = _to_float(v)
        if n is not None:
            return n
    return None


def _deep_find_first_float(obj: Any, keys: set[str]) -> float | None:
    if isinstance(obj, dict):
        # 1) tenta chaves diretas primeiro
        for k, v in obj.items():
            if str(k).strip().lower() in keys:
                n = _to_float(v)
                if n is not None:
                    return n
        # 2) depois desce recursivamente
        for v in obj.values():
            n = _deep_find_first_float(v, keys)
            if n is not None:
                return n
    elif isinstance(obj, list):
        for item in obj:
            n = _deep_find_first_float(item, keys)
            if n is not None:
                return n
    return None


def _iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def _deep_get(obj: Any, keys: set[str]) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).strip().lower() in keys:
                return v
        for v in obj.values():
            out = _deep_get(v, keys)
            if out is not None:
                return out
    elif isinstance(obj, list):
        for item in obj:
            out = _deep_get(item, keys)
            if out is not None:
                return out
    return None


def _extract_positive_atacado_from_payload(payload: Any) -> float | None:
    """
    Tenta localizar preço de lista ATACADO em estruturas variadas do Bling.
    """
    for row in _iter_dicts(payload):
        label = str(
            row.get("nome")
            or row.get("descricao")
            or (row.get("listaPreco") or {}).get("nome")
            or (row.get("lista") or {}).get("nome")
            or ""
        ).upper()
        if "ATAC" not in label:
            continue
        cand = _first_float(
            row.get("preco"),
            row.get("valor"),
            row.get("precoLista"),
            row.get("precoVenda"),
        )
        if cand is None:
            cand = _deep_find_first_float(row, {"preco", "valor", "precolista", "precovenda"})
        if cand is not None and cand > 0:
            return cand
    return None


def _get_price_list_name_map() -> dict[int, str]:
    now = time.time()
    ts = float(_price_list_name_cache.get("ts") or 0)
    cached = _price_list_name_cache.get("map")
    if isinstance(cached, dict) and (now - ts) < _PRICE_LIST_CACHE_TTL_SEC:
        return cached

    out: dict[int, str] = {}
    for endpoint in ("/listas-precos", "/listasPrecos"):
        page = 1
        for _ in range(2):
            try:
                resp = bling_get(endpoint, params={"pagina": page, "limite": 100}, timeout=8, retries=0)
            except Exception:
                break
            data = resp.get("data") if isinstance(resp, dict) else None
            if not isinstance(data, list) or not data:
                break
            for row in data:
                if not isinstance(row, dict):
                    continue
                lid = _first_float(
                    row.get("id"),
                    row.get("idListaPreco"),
                    _deep_get(row, {"id", "idlistapreco", "listaprecoid"}),
                )
                name = str(row.get("nome") or row.get("descricao") or "").strip().upper()
                if lid is not None and name:
                    out[int(lid)] = name
            page += 1
        if out:
            break

    _price_list_name_cache["ts"] = now
    _price_list_name_cache["map"] = out
    return out


def _extract_atacado_by_list_id(payload: Any) -> float | None:
    name_map = _get_price_list_name_map()
    if not name_map:
        return None

    for row in _iter_dicts(payload):
        lid = _first_float(
            row.get("idListaPreco"),
            row.get("listaPrecoId"),
            row.get("id"),
            _deep_get(row.get("listaPreco"), {"id", "idlistapreco"}),
        )
        if lid is None:
            continue
        list_name = name_map.get(int(lid), "")
        if "ATAC" not in list_name:
            continue
        cand = _first_float(
            row.get("preco"),
            row.get("valor"),
            row.get("precoLista"),
            row.get("precoVenda"),
        )
        if cand is None:
            cand = _deep_find_first_float(row, {"preco", "valor", "precolista", "precovenda"})
        if cand is not None and cand > 0:
            return cand
    return None


def _fetch_atacado_from_bling_product_prices(product_id: int) -> float | None:
    cached = _product_atacado_cache.get(int(product_id))
    now = time.time()
    if cached and (now - float(cached[1])) < _PRICE_LIST_CACHE_TTL_SEC:
        return cached[0]

    value: float | None = None
    for endpoint in (
        f"/produtos/{int(product_id)}/precos",
        f"/produtos/{int(product_id)}/preco",
    ):
        try:
            resp = bling_get(endpoint, timeout=8, retries=0)
        except Exception:
            continue
        value = _extract_positive_atacado_from_payload(resp)
        if value is None:
            value = _extract_atacado_by_list_id(resp)
        if value is not None and value > 0:
            break

    _product_atacado_cache[int(product_id)] = (value, now)
    return value


def extract_prices(product_data: dict[str, Any]) -> dict[str, float | None]:
    varejo = _to_float(product_data.get("preco"))

    # Custo pode vir em vários lugares dependendo da estrutura do produto/template no Bling.
    custo = _first_float(
        product_data.get("precoCusto"),
        product_data.get("precoCompra"),
        product_data.get("custo"),
    )
    if custo is None:
        fornecedor = product_data.get("fornecedor")
        if isinstance(fornecedor, dict):
            custo = _first_float(
                fornecedor.get("precoCusto"),
                fornecedor.get("precoCompra"),
                fornecedor.get("custo"),
            )
        elif isinstance(fornecedor, list):
            for row in fornecedor:
                if isinstance(row, dict):
                    custo = _first_float(
                        row.get("precoCusto"),
                        row.get("precoCompra"),
                        row.get("custo"),
                    )
                    if custo is not None:
                        break

    if custo is None:
        fornecedores = product_data.get("fornecedores")
        if isinstance(fornecedores, list):
            for row in fornecedores:
                if isinstance(row, dict):
                    custo = _first_float(
                        row.get("precoCusto"),
                        row.get("precoCompra"),
                        row.get("custo"),
                    )
                    if custo is not None:
                        break

    if custo is None:
        # fallback robusto: busca recursiva em estruturas de fornecedor
        custo = _deep_find_first_float(
            product_data.get("fornecedor"),
            {"precocusto", "precocompra", "custo"},
        )
    if custo is None:
        custo = _deep_find_first_float(
            product_data.get("fornecedores"),
            {"precocusto", "precocompra", "custo"},
        )

    # Atacado pode variar por estrutura de conta/lista de preço.
    atacado = _to_float(product_data.get("precoAtacado"))
    if atacado is not None and atacado <= 0:
        atacado = None
    if atacado is None:
        listas = product_data.get("listaPreco") or product_data.get("listasPreco") or product_data.get("precos")
        if isinstance(listas, list) and listas:
            for row in listas:
                if not isinstance(row, dict):
                    continue
                label = str(
                    row.get("nome")
                    or row.get("descricao")
                    or (row.get("listaPreco") or {}).get("nome")
                    or (row.get("lista") or {}).get("nome")
                    or ""
                ).upper()
                if "ATAC" in label:
                    cand = _first_float(
                        row.get("preco"),
                        row.get("valor"),
                        row.get("precoLista"),
                        row.get("precoVenda"),
                    )
                    if cand is None:
                        cand = _deep_find_first_float(
                            row,
                            {"preco", "valor", "precolista", "precovenda"},
                        )
                    if cand is not None and cand > 0:
                        atacado = cand
                        break

    return {"price_varejo": varejo, "price_custo": custo, "price_atacado": atacado}


def get_product_prices_by_id(product_id: int) -> dict[str, float | None]:
    try:
        data = get_produto(int(product_id)).get("data", {})
        prices = extract_prices(data or {})
        if prices.get("price_atacado") is None:
            prices["price_atacado"] = _fetch_atacado_from_bling_product_prices(int(product_id))
        return prices
    except Exception:
        # Falha temporária do Bling (ex.: 503): não derruba fluxo da UI.
        return {"price_varejo": None, "price_custo": None, "price_atacado": None}


def get_variant_product_id(base: str, color: str, size: str) -> int | None:
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT bling_product_id
        FROM variants_cache
        WHERE base_name = ?
          AND color_key = ?
          AND size_key = ?
        LIMIT 1
        """,
        (base, color, size),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else None


def get_last_known_atacado(base: str, color: str | None = None, size: str | None = None) -> float | None:
    """
    Fallback local quando a API do Bling não devolve lista de preço.
    Busca último preço atacado informado no histórico.
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1) tabela interna de atacado por variacao (prioridade máxima)
    if color and size:
        row = cur.execute(
            """
            SELECT price_atacado
            FROM atacado_prices
            WHERE UPPER(base_name)=?
              AND UPPER(color_key)=?
              AND UPPER(size_key)=?
            LIMIT 1
            """,
            (base.strip().upper(), color.strip().upper(), size.strip().upper()),
        ).fetchone()
        if row and row[0] is not None:
            out = _to_float(row[0])
            if out is not None and out > 0:
                conn.close()
                return out

    # 1.5) por modelo+cor (qualquer tamanho)
    if color and not size:
        row = cur.execute(
            """
            SELECT price_atacado
            FROM atacado_prices
            WHERE UPPER(base_name)=?
              AND UPPER(color_key)=?
              AND price_atacado IS NOT NULL
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (base.strip().upper(), color.strip().upper()),
        ).fetchone()
        if row and row[0] is not None:
            out = _to_float(row[0])
            if out is not None and out > 0:
                conn.close()
                return out

    if color and size:
        row = cur.execute(
            """
            SELECT price_atacado
            FROM stock_moves
            WHERE UPPER(COALESCE(base_name,'')) = ?
              AND UPPER(COALESCE(color_key,'')) = ?
              AND UPPER(COALESCE(size_key,'')) = ?
              AND price_atacado IS NOT NULL
            ORDER BY move_id DESC
            LIMIT 1
            """,
            (base.strip().upper(), color.strip().upper(), size.strip().upper()),
        ).fetchone()
        if row and row[0] is not None:
            out = _to_float(row[0])
            if out is not None and out > 0:
                conn.close()
                return out

    if color and not size:
        row = cur.execute(
            """
            SELECT price_atacado
            FROM stock_moves
            WHERE UPPER(COALESCE(base_name,'')) = ?
              AND UPPER(COALESCE(color_key,'')) = ?
              AND price_atacado IS NOT NULL
            ORDER BY move_id DESC
            LIMIT 1
            """,
            (base.strip().upper(), color.strip().upper()),
        ).fetchone()
        if row and row[0] is not None:
            out = _to_float(row[0])
            if out is not None and out > 0:
                conn.close()
                return out

    row = cur.execute(
        """
        SELECT price_atacado
        FROM stock_moves
        WHERE UPPER(COALESCE(base_name,'')) = ?
          AND price_atacado IS NOT NULL
        ORDER BY move_id DESC
        LIMIT 1
        """,
        (base.strip().upper(),),
    ).fetchone()
    conn.close()
    if row and row[0] is not None:
        out = _to_float(row[0])
        return out if out is not None and out > 0 else None
    return None


def upsert_atacado_price(
    *,
    base: str,
    color: str,
    size: str,
    price_atacado: float,
    sku: str | None = None,
    source: str = "MANUAL",
) -> None:
    conn = get_conn()
    cur = conn.cursor()
    now = int(time.time())
    cur.execute(
        """
        INSERT INTO atacado_prices
        (base_name, color_key, size_key, sku, price_atacado, source, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(base_name, color_key, size_key)
        DO UPDATE SET
            sku=excluded.sku,
            price_atacado=excluded.price_atacado,
            source=excluded.source,
            updated_at=excluded.updated_at
        """,
        (
            base.strip().upper(),
            color.strip().upper(),
            size.strip().upper(),
            (sku or "").strip() or None,
            float(price_atacado),
            source,
            now,
        ),
    )
    conn.commit()
    conn.close()
