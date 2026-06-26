import threading


class AnalyticsMiddleware:
    """Registra pagina_vista para toda requisicao HTML publica GET 200.

    Execucao assincrona (thread daemon) para nao impactar o tempo de resposta.
    Apenas primitivos sao passados para a thread -- nunca o objeto request.
    """

    _EXCLUIR_PREFIXOS = (
        '/admin/',
        '/painel/',
        '/healthz',
        '/static/',
        '/media/',
        '/favicon',
        '/analytics/',
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
        if request.headers.get('HX-Request'):
            return False
        if any(request.path.startswith(p) for p in self._EXCLUIR_PREFIXOS):
            return False
        return True

    def _disparar_async(self, request):
        # Extrai apenas primitivos antes de sair do escopo da request
        session_key  = request.session.session_key or ''
        pagina_url   = request.path[:500]
        ua           = request.META.get('HTTP_USER_AGENT', '')
        cookie_attr  = request.COOKIES.get('della_attr', '')

        t = threading.Thread(
            target=_executar_pagina_vista,
            args=(session_key, pagina_url, ua, cookie_attr),
            daemon=True,
        )
        t.start()


def _executar_pagina_vista(session_key: str, pagina_url: str, ua: str, cookie_attr: str):
    try:
        from apps.analytics.services import obter_ou_criar_sessao_por_valores, registrar_evento
        sessao = obter_ou_criar_sessao_por_valores(session_key, ua, cookie_attr)
        if sessao:
            registrar_evento(sessao, 'pagina_vista', pagina_url=pagina_url)
    except Exception:
        pass
