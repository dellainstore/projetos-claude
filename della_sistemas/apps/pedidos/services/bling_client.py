"""Thin wrapper sobre apps.produtos.services.bling.api para operações de pedidos."""

import logging

from apps.produtos.services.bling.api import bling_get

logger = logging.getLogger(__name__)

_LIMITE = 100


def listar_pedidos_por_situacao(
    situacao_ids: list[int],
    data_inicial: str | None = None,
    data_final: str | None = None,
) -> list[dict]:
    """Busca todos os pedidos do Bling para os IDs de situação fornecidos.

    Percorre todas as páginas de cada situação. Retorna lista de dicts brutos da API.
    """
    todos: list[dict] = []
    for situacao_id in situacao_ids:
        pagina = 1
        while True:
            params: dict = {"idSituacao": situacao_id, "pagina": pagina, "limite": _LIMITE}
            if data_inicial:
                params["dataInicial"] = data_inicial
            if data_final:
                params["dataFinal"] = data_final
            try:
                data = bling_get("/pedidos/vendas", params=params)
            except Exception as exc:
                logger.error("Erro ao buscar situacao=%s pagina=%s: %s", situacao_id, pagina, exc)
                break
            items: list[dict] = data.get("data") or []
            todos.extend(items)
            if len(items) < _LIMITE:
                break
            pagina += 1
    return todos


def obter_detalhe_pedido(bling_id: int) -> dict:
    """Busca detalhe completo de um pedido (itens, parcelas, pagamento)."""
    try:
        data = bling_get(f"/pedidos/vendas/{bling_id}")
        return data.get("data") or {}
    except Exception as exc:
        logger.error("Erro ao buscar detalhe do pedido %s: %s", bling_id, exc)
        return {}


def listar_todos_pedidos(
    data_inicial: str,
    data_final: str,
    on_page=None,
) -> list[dict]:
    """Busca todos os pedidos do período SEM filtro de situação.

    Captura qualquer situação, incluindo as não mapeadas em ALL_IDS.
    on_page(pagina) é chamado a cada página buscada.
    """
    todos: list[dict] = []
    pagina = 1
    while True:
        if on_page:
            on_page(pagina)
        try:
            data = bling_get(
                "/pedidos/vendas",
                params={"dataInicial": data_inicial, "dataFinal": data_final,
                        "pagina": pagina, "limite": _LIMITE},
            )
        except Exception as exc:
            logger.error("Erro ao buscar todos pedidos página %s: %s", pagina, exc)
            break
        items: list[dict] = data.get("data") or []
        todos.extend(items)
        if len(items) < _LIMITE:
            break
        pagina += 1
    return todos


def coletar_situacoes_de_pedidos(dias: int = 180) -> list[dict]:
    """Coleta situações únicas a partir de pedidos recentes (sem filtro de status).

    Usado pelo discover_situacoes para descobrir IDs desconhecidos.
    Percorre as primeiras páginas de pedidos dos últimos `dias` dias.
    """
    from datetime import date, timedelta
    data_ini = (date.today() - timedelta(days=dias)).isoformat()
    data_fim = date.today().isoformat()

    situacoes: dict[int, str] = {}
    pagina = 1
    max_paginas = 20  # até 2000 pedidos

    while pagina <= max_paginas:
        try:
            data = bling_get(
                "/pedidos/vendas",
                params={"dataInicial": data_ini, "dataFinal": data_fim,
                        "pagina": pagina, "limite": _LIMITE},
            )
        except Exception as exc:
            logger.error("Erro ao coletar situações (pág %s): %s", pagina, exc)
            break
        items: list[dict] = data.get("data") or []
        for item in items:
            sit: dict = item.get("situacao") or {}
            sid = sit.get("id")
            snome = sit.get("nome") or f"ID:{sid}"
            if sid and sid not in situacoes:
                situacoes[sid] = snome
        if len(items) < _LIMITE:
            break
        pagina += 1

    return [{"id": k, "nome": v} for k, v in sorted(situacoes.items())]
