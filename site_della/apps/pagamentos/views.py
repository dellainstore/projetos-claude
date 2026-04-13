import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


# ─── PagSeguro ────────────────────────────────────────────────────────────────

@csrf_exempt
def pagseguro_retorno(request):
    """Retorno do PagSeguro após o cliente finalizar o pagamento."""
    return HttpResponse('OK')


@csrf_exempt
def pagseguro_notificacao(request):
    """
    Webhook de notificação do PagSeguro.
    Atualiza o status do pedido conforme o status do pagamento.
    """
    from apps.pedidos.models import Pedido, HistoricoPedido

    notif_code = request.POST.get('notificationCode', '')
    notif_type = request.POST.get('notificationType', '')

    if not notif_code or notif_type != 'transaction':
        return HttpResponse('OK')

    # TODO: consultar a transação na API PagSeguro e atualizar o pedido
    logger.info('Notificação PagSeguro recebida: %s', notif_code)
    return HttpResponse('OK')


# ─── Stone ────────────────────────────────────────────────────────────────────

@csrf_exempt
def stone_webhook(request):
    """
    Webhook de eventos Stone.
    Atualiza o pedido conforme charge status.
    """
    from apps.pedidos.models import Pedido, HistoricoPedido

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = payload.get('type', '')
    logger.info('Webhook Stone recebido: %s', event_type)

    # TODO: processar eventos charge.paid, charge.failed, etc.
    return HttpResponse('OK')


# ─── Pix ──────────────────────────────────────────────────────────────────────

@require_GET
def pix_gerar(request, pedido_numero):
    """
    Gera o QR Code Pix para um pedido.
    Retorna JSON com payload e imagem base64.
    """
    from django.conf import settings
    from apps.pedidos.models import Pedido

    try:
        pedido = Pedido.objects.get(numero=pedido_numero)
    except Pedido.DoesNotExist:
        return JsonResponse({'status': 'erro', 'erro': 'Pedido não encontrado.'}, status=404)

    # Verifica acesso: só o dono, ou quem tem o número na sessão
    if pedido.cliente and request.user.is_authenticated:
        if pedido.cliente != request.user and not request.user.is_staff:
            return JsonResponse({'status': 'erro', 'erro': 'Não autorizado.'}, status=403)

    chave_pix = getattr(settings, 'PIX_CHAVE', '')
    if not chave_pix:
        return JsonResponse({
            'status':  'sem_chave',
            'mensagem': 'Chave Pix não configurada. Configure PIX_CHAVE no .env.',
        })

    try:
        from .pix import gerar_payload_pix, gerar_qrcode_base64
        payload = gerar_payload_pix(
            chave          = chave_pix,
            valor          = float(pedido.total),
            nome_recebedor = 'DELLA INSTORE',
            cidade         = 'SAO PAULO',
            txid           = pedido.numero.replace('-', ''),
            descricao      = f'Pedido {pedido.numero}',
        )
        qrcode_b64 = gerar_qrcode_base64(payload)

        return JsonResponse({
            'status':   'ok',
            'payload':  payload,
            'qrcode':   qrcode_b64,
            'valor':    str(pedido.total),
            'numero':   pedido.numero,
        })
    except Exception as e:
        logger.error('Erro ao gerar Pix %s: %s', pedido_numero, e, exc_info=True)
        return JsonResponse({'status': 'erro', 'erro': 'Erro ao gerar QR Code.'}, status=500)


@require_GET
def pix_status(request, pedido_numero):
    """
    Consulta se o pagamento Pix foi confirmado.
    Por enquanto consulta o status do Pedido no banco.
    Na integração real, consultaria o gateway.
    """
    from apps.pedidos.models import Pedido

    try:
        pedido = Pedido.objects.get(numero=pedido_numero)
    except Pedido.DoesNotExist:
        return JsonResponse({'status': 'erro'}, status=404)

    pago = pedido.status == 'pagamento_confirmado'
    return JsonResponse({
        'status':    'pago' if pago else 'pendente',
        'pedido':    pedido_numero,
        'cancelado': pedido.status == 'cancelado',
    })
