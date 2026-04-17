import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _pode_acessar_pedido(request, pedido) -> bool:
    """
    Autoriza acesso ao pedido em três cenários:
      1. staff (admin)
      2. cliente logado = dono do pedido
      3. número está na sessão do visitante (guest checkout) ou é o último pedido
    Em qualquer outro caso, nega.
    """
    if request.user.is_authenticated:
        if request.user.is_staff:
            return True
        if pedido.cliente_id and pedido.cliente_id == request.user.id:
            return True

    numero = pedido.numero
    if numero == request.session.get('ultimo_pedido'):
        return True
    if numero in request.session.get('pedidos_guest', []):
        return True
    return False


# ─── PagSeguro ────────────────────────────────────────────────────────────────

@csrf_exempt
def pagseguro_retorno(request):
    """Retorno do PagSeguro após o cliente finalizar o pagamento."""
    return HttpResponse('OK')


@csrf_exempt
def pagseguro_notificacao(request):
    """
    Webhook de notificação do PagSeguro (API v4).
    Segurança: o payload recebido indica apenas qual order_id verificar.
    O status real é obtido reconsultando a API PagBank de forma autenticada,
    evitando que POSTs forjados alterem o status de pedidos.
    """
    from apps.pedidos.models import Pedido, HistoricoPedido
    from apps.pagamentos.services.pagseguro import consultar_ordem, status_interno

    if request.method != 'POST':
        return HttpResponse('OK')

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        logger.warning('PagSeguro webhook: body não é JSON válido')
        return HttpResponse(status=400)

    # O webhook informa o ID da order — usamos apenas para saber o que reconsutar
    order_id     = payload.get('id', '')
    reference_id = payload.get('reference_id', '')

    logger.info('PagSeguro webhook recebido: order_id=%s reference_id=%s', order_id, reference_id)

    if not reference_id:
        return HttpResponse('OK')

    try:
        pedido = Pedido.objects.get(numero=reference_id)
    except Pedido.DoesNotExist:
        logger.warning('PagSeguro webhook: pedido %s não encontrado', reference_id)
        return HttpResponse('OK')

    # Reconsulta a ordem na API PagBank para obter o status real (não confia no payload)
    if order_id:
        ordem_verificada = consultar_ordem(order_id)
    else:
        ordem_verificada = None

    if not ordem_verificada:
        logger.warning('PagSeguro webhook: não foi possível verificar order_id=%s — ignorando', order_id)
        return HttpResponse('OK')

    charges = ordem_verificada.get('charges', [])
    if not charges:
        return HttpResponse('OK')

    charge        = charges[0]
    charge_status = (charge.get('status') or '').upper()
    novo_status   = status_interno(charge_status)

    if novo_status and pedido.status != novo_status:
        status_anterior = pedido.status
        pedido.status   = novo_status

        charge_id = charge.get('id', '')
        if charge_id and not pedido.gateway_id:
            pedido.gateway_id = charge_id

        pedido.save(update_fields=['status', 'gateway_id'])

        HistoricoPedido.objects.create(
            pedido          = pedido,
            status_anterior = status_anterior,
            status_novo     = novo_status,
            observacao      = f'PagSeguro webhook verificado: charge {charge_id} → {charge_status}',
        )
        logger.info(
            'PagSeguro: pedido %s atualizado %s → %s (verificado via API)',
            reference_id, status_anterior, novo_status,
        )

    return HttpResponse('OK')


# ─── Stone ────────────────────────────────────────────────────────────────────

@csrf_exempt
def stone_webhook(request):
    """
    Webhook de eventos Stone.
    Atualiza o pedido conforme charge status.
    TODO: validar header X-Stone-Signature (HMAC) antes de processar.
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

    if not _pode_acessar_pedido(request, pedido):
        return JsonResponse({'status': 'erro', 'erro': 'Não autorizado.'}, status=403)

    chave_pix = getattr(settings, 'PIX_CHAVE', '')
    if not chave_pix:
        return JsonResponse({
            'status':   'sem_chave',
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
            'status':  'ok',
            'payload': payload,
            'qrcode':  qrcode_b64,
            'valor':   str(pedido.total),
            'numero':  pedido.numero,
        })
    except Exception as e:
        logger.error('Erro ao gerar Pix %s: %s', pedido_numero, e, exc_info=True)
        return JsonResponse({'status': 'erro', 'erro': 'Erro ao gerar QR Code.'}, status=500)


@require_GET
def pix_status(request, pedido_numero):
    """
    Consulta se o pagamento Pix foi confirmado.
    Consulta o status do Pedido no banco (atualizado manualmente ou via webhook).
    """
    from apps.pedidos.models import Pedido

    try:
        pedido = Pedido.objects.get(numero=pedido_numero)
    except Pedido.DoesNotExist:
        return JsonResponse({'status': 'erro'}, status=404)

    if not _pode_acessar_pedido(request, pedido):
        return JsonResponse({'status': 'erro', 'erro': 'Não autorizado.'}, status=403)

    pago = pedido.status == 'pagamento_confirmado'
    return JsonResponse({
        'status':    'pago' if pago else 'pendente',
        'pedido':    pedido_numero,
        'cancelado': pedido.status == 'cancelado',
    })
