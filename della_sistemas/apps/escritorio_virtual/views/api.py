"""API interna do escritório virtual. Somente leitura, somente autenticada.

Não existe rota de escrita neste app, e nem poderia: a projeção é derivada do
ponto, que continua sendo editado apenas em `/rh/ponto/`.

Além do estado ao vivo, a API aceita uma **pré-visualização**: `?data=` e
`?hora=` projetam a cena de um instante passado, usando as batidas reais que
já estão no banco. É assim que se vê o escritório movimentado fora do
expediente, sem inventar batida nenhuma (uma batida falsa entraria no banco
de horas, geraria pendência de correção e apareceria no espelho de ponto da
colaboradora como se fosse verdadeira).

Diferente das telas do painel, um erro aqui devolve JSON com o status correto
em vez do redirect HTML do `@perm_required` — quem consome é o poller.
"""

from datetime import date, datetime, time

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotModified, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.escritorio_virtual.services.projecao import (
    projetar_cena,
    ultimo_dia_com_movimento,
)
from apps.escritorio_virtual.services.serializacao import (
    calcular_etag,
    etag_corresponde,
    serializar_cena,
)

PERM_VER = "escritorio.ver"


class ParametroInvalido(ValueError):
    """Erro de entrada do usuário, devolvido como 400."""


def _checar_acesso(request: HttpRequest) -> JsonResponse | None:
    """None quando pode seguir; resposta de erro caso contrário."""
    if not getattr(settings, "ESCRITORIO_ATIVO", True):
        raise Http404("Escritório virtual desativado.")
    if not request.user.is_authenticated:
        return JsonResponse({"erro": "nao_autenticado"}, status=401)
    if not request.user.tem_perm(PERM_VER):
        return JsonResponse({"erro": "sem_permissao"}, status=403)
    return None


def _parse_data(bruto: str) -> date:
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        raise ParametroInvalido("data inválida, use AAAA-MM-DD")


def _parse_hora(bruto: str) -> time:
    partes = bruto.split(":")
    try:
        hora = int(partes[0])
        minuto = int(partes[1]) if len(partes) > 1 else 0
        return time(hora, minuto)
    except (ValueError, IndexError):
        raise ParametroInvalido("hora inválida, use HH:MM")


def _resolver_instante(request: HttpRequest) -> tuple[date | None, datetime | None, dict]:
    """Traduz `?data=`/`?hora=` em (dia, agora, bloco de preview).

    Sem parâmetro nenhum, devolve (None, None, preview desligado) e a projeção
    usa o agora de verdade."""
    bruto_data = (request.GET.get("data") or "").strip()
    bruto_hora = (request.GET.get("hora") or "").strip()

    if not bruto_data and not bruto_hora:
        return None, None, {
            "ativo": False,
            # Sugestão de data para a tela: sem isso, quem abre num sábado à
            # noite escolhe no escuro.
            "ultimoDiaComMovimento": (
                d.isoformat() if (d := ultimo_dia_com_movimento()) else None
            ),
        }

    hoje = timezone.localdate()
    dia = _parse_data(bruto_data) if bruto_data else hoje
    if dia > hoje:
        raise ParametroInvalido("a pré-visualização não olha para o futuro")

    agora = None
    if bruto_hora:
        agora = timezone.make_aware(datetime.combine(dia, _parse_hora(bruto_hora)))

    return dia, agora, {
        "ativo": True,
        "data": dia.isoformat(),
        "hora": timezone.localtime(agora).strftime("%H:%M") if agora else None,
    }


@require_GET
def view_estado(request: HttpRequest) -> HttpResponse:
    """Estado atual completo da cena (ou de um instante escolhido).

    Contrato de tempo real: o cliente SEMPRE carrega o estado inteiro por aqui
    (na abertura da página e a cada poll). Nunca depende de ter recebido um
    evento, então abrir a página depois de uma batida mostra a cena correta.
    """
    erro = _checar_acesso(request)
    if erro is not None:
        return erro

    try:
        dia, agora, preview = _resolver_instante(request)
    except ParametroInvalido as exc:
        return JsonResponse({"erro": "parametro_invalido", "detalhe": str(exc)}, status=400)

    cena = projetar_cena(dia=dia, agora=agora)
    payload = serializar_cena(cena, preview)
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
