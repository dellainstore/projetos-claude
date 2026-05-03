def categorias_menu(request):
    """
    Injeta categorias ativas e números de WhatsApp em todos os templates.
    Cache de 4 horas — invalidado automaticamente ao salvar/deletar no admin.
    """
    from django.core.cache import cache
    from django.conf import settings
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

    return {
        'categorias_menu':  categorias,
        'WHATSAPP_NUMBER_1': getattr(settings, 'WHATSAPP_NUMBER_1', ''),
        'WHATSAPP_NUMBER_2': getattr(settings, 'WHATSAPP_NUMBER_2', ''),
        'META_PIXEL_ID':     getattr(settings, 'META_PIXEL_ID', ''),
        'GA_MEASUREMENT_ID': getattr(settings, 'GA_MEASUREMENT_ID', ''),
    }
