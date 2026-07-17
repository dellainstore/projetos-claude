"""
Health checks da aplicacao.

/healthz  -> liveness: apenas confirma que o processo responde. Nao toca banco,
             cache nem servicos externos, nao cria sessao, nao loga.
/readyz   -> readiness: banco e cache respondendo, com timeout curto. Nao chama
             PagBank/Bling/Correios/Melhor Envio (esses sao verificados de forma
             assincrona pelo painel de Monitoramento, nunca a cada request).

checar_prontidao() e reaproveitada pelo painel de Monitoramento (Saude do
sistema) para nao duplicar a logica de verificacao.
"""
import logging

from django.core.cache import cache
from django.db import connections
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger('apps.core_utils')

_READY_CACHE_KEY = 'readyz_probe'


def checar_prontidao() -> dict:
    """Verifica banco e cache sem levantar excecao.

    Retorna {'db': bool, 'cache': bool, 'ready': bool}. Seguro para uso em
    endpoint publico e no painel: nunca expoe detalhe interno nem dado sensivel.
    """
    db_ok = False
    try:
        with connections['default'].cursor() as cur:
            cur.execute('SELECT 1')
            db_ok = cur.fetchone() is not None
    except Exception:
        # Sem exc_info/dado sensivel — apenas sinaliza indisponibilidade.
        logger.warning('readyz: banco nao respondeu')
        db_ok = False

    cache_ok = False
    try:
        cache.set(_READY_CACHE_KEY, '1', 10)
        cache_ok = cache.get(_READY_CACHE_KEY) == '1'
    except Exception:
        logger.warning('readyz: cache nao respondeu')
        cache_ok = False

    return {'db': db_ok, 'cache': cache_ok, 'ready': db_ok and cache_ok}


def healthz(_request):
    """Liveness. Resposta minima, sem tocar banco/cache."""
    return HttpResponse('ok', content_type='text/plain')


def readyz(_request):
    """Readiness. 200 quando banco e cache respondem; 503 quando degradado."""
    estado = checar_prontidao()
    return JsonResponse(
        {
            'status': 'ready' if estado['ready'] else 'degraded',
            'db': estado['db'],
            'cache': estado['cache'],
        },
        status=200 if estado['ready'] else 503,
    )
