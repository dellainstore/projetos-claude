"""Chamadas Bling específicas do módulo Estoque (saldo, vendas, preço/custo).

Reaproveita o cliente HTTP do Django (retry, rate-limit, auth compartilhada)
já usado pelo apps.produtos — não reimplementa nada disso aqui.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any

from apps.produtos.services.bling.api import bling_get

PAGE_SIZE = 100
ATTENDED_STATUS_IDS = {47579, 150640, 9, 102406, 114939, 18723}
MAX_SAFE_DETAIL_WORKERS = 3  # Bling limita ~3 req/s no tenant atual


def _extract_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    return []


def _pick_first(obj: Any, keys: list[str]) -> Any:
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] not in (None, "", [], {}):
                return obj[key]
        for value in obj.values():
            found = _pick_first(value, keys)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _pick_first(item, keys)
            if found not in (None, "", [], {}):
                return found
    return None


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return 0
    try:
        return int(float(value))
    except Exception:
        return 0


def _normalize_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        pass
    return raw[:10]


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(str(value).strip()[:10])


def _iter_paginated(path: str, *, extra_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        params = {"pagina": page, "limite": PAGE_SIZE}
        if extra_params:
            params.update(extra_params)

        payload = bling_get(path, params=params)
        rows = _extract_list(payload)
        if not rows:
            break

        results.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        page += 1

    return results


def _extrair_estoque_do_produto(item: dict[str, Any]) -> float:
    estoque_obj = item.get("estoque")
    if not isinstance(estoque_obj, dict):
        return 0.0
    return _to_float(estoque_obj.get("saldoVirtualTotal"))


def get_produtos_precos() -> list[dict[str, Any]]:
    """Preço/custo/fornecedor por produto — únicos campos não cacheados em
    `products_cache` (identidade/SKU/modelo/cor/tamanho vêm do catálogo do
    produtos, via `catalog_bridge`)."""
    produtos = _iter_paginated("/produtos")
    out: list[dict[str, Any]] = []
    for item in produtos:
        produto_id = _to_int(_pick_first(item, ["id", "idProduto"]))
        if produto_id <= 0:
            continue
        out.append(
            {
                "id": produto_id,
                "preco": _to_float(_pick_first(item, ["preco", "precoVenda", "valor"])),
                "precoCusto": _to_float(_pick_first(item, ["precoCusto", "custo", "valorCusto"])),
                "fornecedor": str(_pick_first(item, ["fornecedor", "nomeFornecedor"]) or "").strip(),
                "estoque": _extrair_estoque_do_produto(item),
            }
        )
    return out


def get_estoque_atual() -> list[dict[str, Any]]:
    """Busca saldos de estoque fisico por produto via /estoques/saldos.

    - lista todos os produtos em /produtos (paginado)
    - consulta /estoques/saldos em lotes de 100 ids (idsProdutos[])
    - usa saldoFisicoTotal, com fallback soma de depositos[].saldoFisico
    """
    produtos = _iter_paginated("/produtos")
    produto_ids = sorted(
        {
            _to_int(_pick_first(p, ["id", "idProduto"]))
            for p in produtos
            if _to_int(_pick_first(p, ["id", "idProduto"])) > 0
        }
    )
    if not produto_ids:
        return []

    def _chunks(values: list[int], size: int) -> list[list[int]]:
        return [values[i : i + size] for i in range(0, len(values), size)]

    out: list[dict[str, Any]] = []
    for batch in _chunks(produto_ids, 100):
        payload = bling_get("/estoques/saldos", params={"idsProdutos[]": batch})
        rows = _extract_list(payload)
        for item in rows:
            produto_obj = item.get("produto")
            produto_id = _to_int(produto_obj.get("id")) if isinstance(produto_obj, dict) else 0
            if produto_id <= 0:
                produto_id = _to_int(_pick_first(item, ["idProduto", "id"]))
            if produto_id <= 0:
                continue

            saldo_fisico_total = item.get("saldoFisicoTotal")
            if saldo_fisico_total not in (None, ""):
                quantidade = _to_float(saldo_fisico_total)
            else:
                depositos = item.get("depositos")
                quantidade = 0.0
                if isinstance(depositos, list):
                    quantidade = float(sum(_to_float(dep.get("saldoFisico")) for dep in depositos if isinstance(dep, dict)))

            out.append({"produto_id": produto_id, "quantidade": quantidade})

    return out


def _iter_vendas_brutas(periodo_inicio: str, periodo_fim: str) -> list[dict[str, Any]]:
    """Lista pedidos de venda com quebra automatica de janelas longas.

    Bling limita o filtro de periodo para no maximo 366 dias.
    """
    ini = _parse_iso_date(periodo_inicio)
    fim = _parse_iso_date(periodo_fim)
    if ini > fim:
        ini, fim = fim, ini

    all_rows: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    cursor = ini
    max_days_per_window = 365
    while cursor <= fim:
        chunk_end = min(cursor + timedelta(days=max_days_per_window), fim)
        params = {"dataInicial": cursor.isoformat(), "dataFinal": chunk_end.isoformat()}
        rows = _iter_paginated("/pedidos/vendas", extra_params=params)
        for row in rows:
            pedido_id = _to_int(row.get("id"))
            if pedido_id <= 0 or pedido_id in seen_ids:
                continue
            seen_ids.add(pedido_id)
            all_rows.append(row)
        cursor = chunk_end + timedelta(days=1)

    return all_rows


def _extrair_situacao_id_lista(pedido: dict[str, Any]) -> int:
    situacao = pedido.get("situacao")
    if isinstance(situacao, dict):
        return _to_int(situacao.get("id"))
    return _to_int(pedido.get("idSituacao"))


def _extrair_situacao_id_detalhe(pedido: dict[str, Any]) -> int:
    situacao = pedido.get("situacao")
    if isinstance(situacao, dict):
        return _to_int(situacao.get("id"))
    return 0


def _extrair_produto_refs(item: dict[str, Any]) -> dict[str, Any]:
    produto_obj = item.get("produto")
    produto_dict = produto_obj if isinstance(produto_obj, dict) else {}
    produto_id = _to_int(produto_dict.get("id"))
    if produto_id <= 0:
        produto_id = _to_int(item.get("idProduto"))
    produto_codigo = str(produto_dict.get("codigo") or item.get("codigo") or item.get("codigoProduto") or "").strip()
    produto_nome = str(produto_dict.get("nome") or item.get("nome") or item.get("descricao") or "").strip()
    return {"id": produto_id, "codigo": produto_codigo, "nome": produto_nome}


def _get_pedido_detalhe(pedido_id: int) -> dict[str, Any]:
    payload = bling_get(f"/pedidos/vendas/{pedido_id}")
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def get_vendas(periodo_inicio: str, periodo_fim: str, *, detail_workers: int = 5) -> list[dict[str, Any]]:
    """Retorna itens vendidos no periodo para pedidos atendidos."""
    out: list[dict[str, Any]] = []
    workers = max(1, min(int(detail_workers or 5), MAX_SAFE_DETAIL_WORKERS))

    pedidos = _iter_vendas_brutas(periodo_inicio, periodo_fim)
    candidatas: list[tuple[int, str, int]] = []
    for pedido in pedidos:
        pedido_id = _to_int(pedido.get("id"))
        if pedido_id <= 0:
            continue
        situacao_id_lista = _extrair_situacao_id_lista(pedido)
        if situacao_id_lista not in ATTENDED_STATUS_IDS:
            continue
        data_lista = _normalize_date(pedido.get("data"))
        candidatas.append((pedido_id, data_lista, situacao_id_lista))

    def _fetch_detail(task: tuple[int, str, int]) -> tuple[int, str, int, dict[str, Any]]:
        pid, data_lista, situacao_lista = task
        detalhe = _get_pedido_detalhe(pid)
        return pid, data_lista, situacao_lista, detalhe

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for i in range(0, len(candidatas), workers):
            batch = candidatas[i : i + workers]
            future_to_task = {executor.submit(_fetch_detail, task): task for task in batch}
            for future in as_completed(future_to_task):
                pedido_id, data_lista, _situacao_id_lista, detalhe = future.result()

                situacao_id_detalhe = _extrair_situacao_id_detalhe(detalhe)
                if situacao_id_detalhe not in ATTENDED_STATUS_IDS:
                    continue

                data_pedido = _normalize_date(
                    detalhe.get("data") or detalhe.get("dataPedido") or detalhe.get("dataEmissao")
                )
                if not data_pedido:
                    data_pedido = data_lista

                itens = detalhe.get("itens")
                if not isinstance(itens, list):
                    continue

                for item in itens:
                    if not isinstance(item, dict):
                        continue
                    produto_refs = _extrair_produto_refs(item)
                    produto_id = int(produto_refs.get("id") or 0)
                    quantidade = _to_float(item.get("quantidade") or item.get("qtde"))
                    if produto_id <= 0 or quantidade <= 0:
                        continue
                    valor_unitario = _to_float(item.get("valor"))
                    desconto = _to_float(item.get("desconto"))
                    # Desconto as vezes é lançado maior que o próprio item (ex.: peça
                    # zerada + desconto residual do pedido jogado nessa linha no Bling).
                    # Isso não deve virar receita negativa — trava em 0.
                    valor_total_item = max(0.0, round(valor_unitario * quantidade - desconto, 2))
                    out.append(
                        {
                            "idProduto": produto_id,
                            "codigoProduto": str(produto_refs.get("codigo") or "").strip(),
                            "nomeProduto": str(produto_refs.get("nome") or "").strip(),
                            "quantidade": quantidade,
                            "valor": valor_total_item,
                            "dataPedido": data_pedido,
                            "idPedido": pedido_id,
                            "situacaoId": situacao_id_detalhe,
                        }
                    )

            if i + workers < len(candidatas):
                time.sleep(1.1)

    return out
