"""API interna do escritório virtual. Somente leitura, somente autenticada.

Não existe rota de escrita neste app, e nem poderia: a projeção é derivada do
ponto, que continua sendo editado apenas em `/rh/ponto/`.

Diferente das telas do painel, um erro de autorização aqui devolve JSON com o
status correto (401/403) em vez do redirect HTML do `@perm_required` — quem
consome é o poller, não um navegador navegando.
"""

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotModified, JsonResponse
from django.views.decorators.http import require_GET

from apps.escritorio_virtual.services.projecao import projetar_cena
from apps.escritorio_virtual.services.serializacao import (
    calcular_etag,
    etag_corresponde,
    serializar_cena,
)

PERM_VER = "escritorio.ver"


def _checar_acesso(request: HttpRequest) -> JsonResponse | None:
    """None quando pode seguir; resposta de erro caso contrário."""
    if not getattr(settings, "ESCRITORIO_ATIVO", True):
        raise Http404("Escritório virtual desativado.")
    if not request.user.is_authenticated:
        return JsonResponse({"erro": "nao_autenticado"}, status=401)
    if not request.user.tem_perm(PERM_VER):
        return JsonResponse({"erro": "sem_permissao"}, status=403)
    return None


@require_GET
def view_estado(request: HttpRequest) -> HttpResponse:
    """Estado atual completo da cena.

    Contrato de tempo real: o cliente SEMPRE carrega o estado inteiro por aqui
    (na abertura da página e a cada poll). Nunca depende de ter recebido um
    evento, então abrir a página depois de uma batida mostra a cena correta.
    """
    erro = _checar_acesso(request)
    if erro is not None:
        return erro

    cena = projetar_cena()
    payload = serializar_cena(cena)
    etag = calcular_etag(payload)

    if etag_corresponde(request.headers.get("If-None-Match"), etag):
        resposta = HttpResponseNotModified()
    else:
        resposta = JsonResponse(payload)

    resposta["ETag"] = etag
    # Resposta depende da sessão: nunca pode ser cacheada por proxy
    # compartilhado. O 304 aqui é negociado pelo próprio poller, que guarda o
    # ETag em memória e reenvia em `If-None-Match` — não depende do cache do
    # navegador (que o Nginx desliga nesta origem).
    resposta["Cache-Control"] = "private, no-cache"
    resposta["Vary"] = "Cookie"
    return resposta
