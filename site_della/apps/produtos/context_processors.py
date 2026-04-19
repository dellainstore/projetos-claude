def categorias_menu(request):
    """
    Injeta categorias ativas em todos os templates (para o menu de navegação).
    Retorna apenas categorias-mãe (parent=None), com subcategorias pré-carregadas.
    Cache de 4 horas — invalidado automaticamente ao salvar/deletar no admin.
    """
    from django.core.cache import cache
    from apps.core_utils.cache_utils import MENU_CATEGORIAS
    from apps.produtos.models import Categoria

    categorias = cache.get(MENU_CATEGORIAS)
    if categorias is None:
        try:
            categorias = list(
                Categoria.objects
                .filter(ativa=True, parent__isnull=True)
                .prefetch_related('subcategorias')
                .order_by('ordem', 'nome')
            )
        except Exception:
            categorias = []
        cache.set(MENU_CATEGORIAS, categorias, 60 * 60 * 4)

    return {'categorias_menu': categorias}
