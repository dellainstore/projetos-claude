import threading
import time

from django.conf import settings


class Erro5xxMiddleware:
    """Captura respostas 5xx e excecoes nao tratadas para o registro estruturado.

    Atribui um correlation id por request (exposto em X-Correlation-Id e reusado
    pela telemetria client-side). Nao toca dados sensiveis: apenas caminho sem
    querystring, view name, status, duracao, UA classificada e hash de sessao.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from apps.core_utils.erros import novo_correlation_id
        request.correlation_id = novo_correlation_id()
        inicio = time.monotonic()
        request._erro5xx_inicio = inicio
        response = self.get_response(request)
        duracao_ms = int((time.monotonic() - inicio) * 1000)
        try:
            response['X-Correlation-Id'] = request.correlation_id
        except Exception:
            pass
        if response.status_code >= 500 and not getattr(request, '_erro5xx_logado', False):
            self._registrar(request, response.status_code, duracao_ms, exc_tipo='', resumo='')
        return response

    def process_exception(self, request, exception):
        # View levantou excecao nao tratada -> Django devolvera 500.
        # Registramos aqui (temos o tipo da excecao) e marcamos para o __call__
        # nao duplicar.
        duracao_ms = None
        inicio = getattr(request, '_erro5xx_inicio', None)
        if inicio is not None:
            duracao_ms = int((time.monotonic() - inicio) * 1000)
        request._erro5xx_logado = True
        self._registrar(
            request, 500, duracao_ms,
            exc_tipo=type(exception).__name__, resumo=str(exception),
        )
        return None  # deixa o Django seguir com o handler 500 normal

    def _registrar(self, request, status, duracao_ms, exc_tipo, resumo):
        from apps.core_utils.erros import registrar_evento_erro
        try:
            endpoint = ''
            match = getattr(request, 'resolver_match', None)
            if match is not None:
                endpoint = match.view_name or ''
            session_key = ''
            sess = getattr(request, 'session', None)
            if sess is not None:
                session_key = sess.session_key or ''  # nao cria sessao nova
            registrar_evento_erro(
                status=status,
                fonte='django',
                metodo=request.method,
                caminho=request.path,
                endpoint=endpoint,
                duracao_ms=duracao_ms,
                exc_tipo=exc_tipo,
                resumo=resumo,
                correlation_id=getattr(request, 'correlation_id', ''),
                cf_ray=request.headers.get('CF-Ray', ''),
                ua=request.headers.get('User-Agent', ''),
                session_key=session_key,
            )
        except Exception:
            pass


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
        '/readyz',
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
