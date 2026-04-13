def categorias_menu(request):
    """Injeta categorias ativas em todos os templates (para o menu de navegação)."""
    from apps.produtos.models import Categoria
    try:
        categorias = Categoria.objects.filter(ativa=True).order_by('ordem')
    except Exception:
        categorias = []
    return {'categorias_menu': categorias}
