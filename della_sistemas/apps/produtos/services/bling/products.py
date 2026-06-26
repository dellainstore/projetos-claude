from apps.produtos.services.bling.api import bling_get, bling_post, bling_patch


def get_produto(product_id: int) -> dict:
    return bling_get(f"/produtos/{int(product_id)}")


def criar_produto(payload: dict) -> dict:
    # Bling espera {"data": {...}} em alguns endpoints, mas no seu caso já funcionou como payload direto.
    # Se começar a dar 400 "data obrigatória", a gente muda pra {"data": payload}.
    return bling_post("/produtos", json=payload)


def atualizar_produto_patch(product_id: int, payload: dict) -> dict:
    return bling_patch(f"/produtos/{int(product_id)}", json=payload)
