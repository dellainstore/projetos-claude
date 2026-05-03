from django.core.cache import cache
from django.shortcuts import render

from apps.core_utils.cache_utils import MANUTENCAO_ATIVA

_CACHE_TTL = 30  # segundos — tempo máximo para o toggle refletir no site


def manutencao_middleware(get_response):
    def middleware(request):
        # Admin sempre acessível
        if request.path.startswith('/painel/'):
            return get_response(request)

        # Staff autenticado vê o site normalmente (para testar antes de abrir)
        if getattr(request, 'user', None) and request.user.is_authenticated and request.user.is_staff:
            return get_response(request)

        ativa = cache.get(MANUTENCAO_ATIVA)
        if ativa is None:
            from apps.conteudo.models import ConfiguracaoLoja
            config = ConfiguracaoLoja.objects.first()
            ativa = bool(config and config.modo_manutencao)
            cache.set(MANUTENCAO_ATIVA, ativa, _CACHE_TTL)

        if ativa:
            return render(request, 'manutencao.html', status=503)

        return get_response(request)

    return middleware
