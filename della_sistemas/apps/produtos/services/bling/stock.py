from apps.produtos.services.config import BLING_DEPOSITO_ID
from apps.produtos.services.bling.api import bling_post


def salvar_lancamento_estoque(id_produto: int, quantidade: int, tipo_operacao: str, observacoes: str = "") -> dict:
    if not BLING_DEPOSITO_ID:
        raise RuntimeError("BLING_DEPOSITO_ID não configurado no .env")

    payload = {
        "idProduto": int(id_produto),
        "idDeposito": int(BLING_DEPOSITO_ID),
        "quantidade": int(quantidade),
        "tipoOperacao": str(tipo_operacao),
        "observacoes": observacoes or "Inclusão automática via sistema",
    }

    return bling_post("/estoques", json=payload)
