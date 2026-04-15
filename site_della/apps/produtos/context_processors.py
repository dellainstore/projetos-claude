def categorias_menu(request):
    """
    Injeta categorias ativas em todos os templates (para o menu de navegação).
    Retorna apenas categorias-mãe (parent=None), com subcategorias pré-carregadas.
    """
    from apps.produtos.models import Categoria
    try:
        categorias = (
            Categoria.objects
            .filter(ativa=True, parent__isnull=True)
            .prefetch_related('subcategorias')
            .order_by('ordem', 'nome')
        )
    except Exception:
        categorias = []
    return {'categorias_menu': categorias}
