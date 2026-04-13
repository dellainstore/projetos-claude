def carrinho_info(request):
    """Injeta quantidade de itens do carrinho em todos os templates."""
    try:
        from apps.pedidos.carrinho import Carrinho
        carrinho = Carrinho(request)
        return {
            'carrinho_total_itens': len(carrinho),
            'carrinho_total': carrinho.get_total(),
        }
    except Exception:
        return {
            'carrinho_total_itens': 0,
            'carrinho_total': 0,
        }
