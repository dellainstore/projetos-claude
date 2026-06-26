from apps.produtos.services.bling.api import bling_post


def lancar_estoque(
    id_produto: int,
    id_deposito: int,
    tipo_operacao: str,
    quantidade: int,
    observacoes: str | None = None,
) -> dict:
    body = {
        "idProduto": int(id_produto),
        "idDeposito": int(id_deposito),
        "tipoOperacao": str(tipo_operacao),
        "quantidade": int(quantidade),
    }
    if observacoes:
        body["observacoes"] = observacoes

    return bling_post("/estoques", json=body)
