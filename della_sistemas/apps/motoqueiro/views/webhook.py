import json
import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.motoqueiro.models import SolicitacaoEntrega, SolicitacaoEntregaEvento
from apps.motoqueiro.services import loggi
from apps.motoqueiro.services.lalamove import traduzir_status, verificar_assinatura_webhook

logger = logging.getLogger("apps.motoqueiro")


@csrf_exempt
@require_POST
def webhook_lalamove(request: HttpRequest) -> HttpResponse:
    """Endpoint publico (sem login) que recebe as notificacoes de status da
    Lalamove. Sempre responde 200 rapido (evita retry em loop do lado deles),
    mas so aplica a mudanca de status se a assinatura bater."""
    raw_body = request.body
    assinatura_ok = verificar_assinatura_webhook(request.headers, raw_body)

    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        logger.warning("motoqueiro webhook: payload nao é JSON valido: %r", raw_body[:500])
        return JsonResponse({"ok": False, "erro": "payload invalido"}, status=200)

    if not assinatura_ok:
        logger.warning("motoqueiro webhook: assinatura NAO confere. payload=%s", json.dumps(payload)[:1000])
        # Loga mesmo assim (sem aplicar) para dar pra ajustar a verificacao
        # olhando o formato real que a Lalamove mandou.
        _logar_payload_bruto(payload, verificado=False)
        return JsonResponse({"ok": False, "erro": "assinatura invalida"}, status=200)

    dados = (payload.get("data") or {})
    order = dados.get("order") or dados
    order_id = order.get("orderId") or order.get("id")
    status_raw = order.get("status", "")

    if not order_id:
        logger.warning("motoqueiro webhook: sem orderId no payload: %s", json.dumps(payload)[:1000])
        return JsonResponse({"ok": False, "erro": "sem orderId"}, status=200)

    solicitacao = SolicitacaoEntrega.objects.filter(lalamove_order_id=order_id).first()
    if not solicitacao:
        logger.info("motoqueiro webhook: order_id %s nao corresponde a nenhuma solicitacao local.", order_id)
        return JsonResponse({"ok": False, "erro": "solicitacao nao encontrada"}, status=200)

    status_novo = traduzir_status(status_raw)
    status_anterior = solicitacao.status

    solicitacao.status = status_novo
    solicitacao.lalamove_status_raw = status_raw
    novo_link = order.get("shareLink") or order.get("trackingUrl") or order.get("share_link")
    if novo_link:
        solicitacao.lalamove_share_link = novo_link
    if status_novo in SolicitacaoEntrega.STATUS_FINAIS and not solicitacao.concluido_em:
        solicitacao.concluido_em = timezone.now()
    solicitacao.save(update_fields=["status", "lalamove_status_raw", "lalamove_share_link", "concluido_em", "atualizado_em"])

    SolicitacaoEntregaEvento.objects.create(
        solicitacao=solicitacao,
        status_anterior=status_anterior,
        status_novo=status_novo,
        status_raw=status_raw,
        origem="webhook",
        payload=payload,
    )
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def webhook_loggi(request: HttpRequest) -> HttpResponse:
    """Endpoint publico (sem login) que recebe as notificacoes de status da
    Loggi. ESQUELETO NAO TESTADO CONTRA PAYLOAD REAL — a Loggi autentica via
    Basic Auth (config LOGGI_WEBHOOK_USER/PASSWORD), diferente do HMAC da
    Lalamove. Sempre responde 200 rapido (evita retry em loop do lado
    deles), mas so aplica a mudanca de status se a autenticacao bater e o
    pacote for encontrado localmente."""
    raw_body = request.body
    autenticado = loggi.verificar_assinatura_webhook(request.headers)

    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        logger.warning("motoqueiro webhook loggi: payload nao é JSON valido: %r", raw_body[:500])
        return JsonResponse({"ok": False, "erro": "payload invalido"}, status=200)

    if not autenticado:
        logger.warning("motoqueiro webhook loggi: Basic Auth NAO confere. payload=%s", json.dumps(payload)[:1000])
        _logar_payload_bruto(payload, verificado=False)
        return JsonResponse({"ok": False, "erro": "autenticacao invalida"}, status=200)

    # Formato assumido a partir da doc publica (nao confirmado ao vivo):
    # {"loggiKey": "...", "trackingCode": "...", "status": {"code": 5, ...}}
    loggi_key = payload.get("loggiKey", "")
    tracking_code = payload.get("trackingCode", "")
    status_info = payload.get("status") or {}
    status_code = status_info.get("code")

    if not loggi_key and not tracking_code:
        logger.warning("motoqueiro webhook loggi: sem loggiKey/trackingCode no payload: %s", json.dumps(payload)[:1000])
        return JsonResponse({"ok": False, "erro": "sem identificador do pacote"}, status=200)

    solicitacao = SolicitacaoEntrega.objects.filter(loggi_key=loggi_key).first() if loggi_key else None
    if not solicitacao and tracking_code:
        solicitacao = SolicitacaoEntrega.objects.filter(loggi_tracking_code=tracking_code).first()
    if not solicitacao:
        logger.info("motoqueiro webhook loggi: pacote %s/%s nao corresponde a nenhuma solicitacao local.", loggi_key, tracking_code)
        return JsonResponse({"ok": False, "erro": "solicitacao nao encontrada"}, status=200)

    status_novo = loggi.traduzir_status(status_code)
    status_anterior = solicitacao.status

    solicitacao.status = status_novo
    solicitacao.loggi_status_raw = str(status_code) if status_code is not None else ""
    if not solicitacao.loggi_key and loggi_key:
        solicitacao.loggi_key = loggi_key
    if status_novo in SolicitacaoEntrega.STATUS_FINAIS and not solicitacao.concluido_em:
        solicitacao.concluido_em = timezone.now()
    solicitacao.save(update_fields=["status", "loggi_status_raw", "loggi_key", "concluido_em", "atualizado_em"])

    SolicitacaoEntregaEvento.objects.create(
        solicitacao=solicitacao,
        status_anterior=status_anterior,
        status_novo=status_novo,
        status_raw=str(status_code) if status_code is not None else "",
        origem="webhook",
        payload=payload,
    )
    return JsonResponse({"ok": True})


def _logar_payload_bruto(payload: dict, verificado: bool) -> None:
    """Loga um payload que nao pode ser aplicado (assinatura nao confere ou
    order_id nao encontrado) sem quebrar o registro de nenhuma solicitacao —
    so para depuracao do formato real do webhook."""
    logger.info("motoqueiro webhook bruto (verificado=%s): %s", verificado, json.dumps(payload, ensure_ascii=False)[:2000])
