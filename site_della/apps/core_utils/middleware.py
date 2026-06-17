import threading

from django.conf import settings


class MetaCAPIPageViewMiddleware:
    """
    Dispara CAPI PageView em toda requisicao HTML publica - sem gate de consent.

    Com consent de marketing: envia dados enriquecidos (IP, UA, email hash, etc.)
    Sem consent: envia apenas pais ('br') como dado nao-identificavel.

    O envio e assincrono (thread daemon) para nao impactar o tempo de resposta.
    """

    _EXCLUIR_PREFIXOS = (
        '/admin/',
        '/painel/',
        '/healthz',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self._deve_rastrear(request, response):
            self._disparar_async(request)
        return response

    def _deve_rastrear(self, request, response) -> bool:
        if response.status_code != 200:
            return False
        if 'text/html' not in response.get('Content-Type', ''):
            return False
        if request.method != 'GET':
            return False
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return False
        if any(request.path.startswith(p) for p in self._EXCLUIR_PREFIXOS):
            return False
        if not getattr(settings, 'META_PIXEL_ID', ''):
            return False
        if not getattr(settings, 'META_CONVERSIONS_API_TOKEN', ''):
            return False
        return True

    def _disparar_async(self, request):
        from apps.core_utils.meta import preparar_user_data_pageview, enviar_capi_pageview
        try:
            url, user_data = preparar_user_data_pageview(request)
        except Exception:
            return
        t = threading.Thread(
            target=enviar_capi_pageview,
            kwargs={'url': url, 'user_data': user_data},
            daemon=True,
        )
        t.start()
