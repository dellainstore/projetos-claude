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

    # Determina status: cartão usa charges; PIX usa qr_codes
    charges     = ordem_verificada.get('charges', [])
    qr_codes    = ordem_verificada.get('qr_codes', [])
    charge_id   = ''
    charge_status = ''

    if charges:
        charge        = charges[0]
        charge_status = (charge.get('status') or '').upper()
        charge_id     = charge.get('id', '')
    elif qr_codes:
        # PIX: quando pago, PagBank marca o qr_code como PAID
        qr = qr_codes[0]
        charge_status = (qr.get('status') or '').upper()
        charge_id     = qr.get('id', '')

    if not charge_status:
        return HttpResponse('OK')

    novo_status = status_interno(charge_status)

    if novo_status and pedido.status != novo_status:
        status_anterior = pedido.status
        pedido.status   = novo_status

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

        # Sincroniza situação com o Bling
        try:
            from apps.bling.services import (
                atualizar_situacao_bling,
                SITUACAO_ATENDIDO_SITE,
                SITUACAO_CANCELADO,
            )
            if novo_status == 'pagamento_confirmado':
                atualizar_situacao_bling(pedido, SITUACAO_ATENDIDO_SITE)
            elif novo_status == 'cancelado':
                from apps.bling.services import restaurar_estoque_pedido
                restaurar_estoque_pedido(pedido)
                atualizar_situacao_bling(pedido, SITUACAO_CANCELADO)
        except Exception as exc:
            logger.warning('Bling: não foi possível atualizar situação do pedido %s: %s', reference_id, exc)

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

def cartao_pagar_pedido(request, pedido_numero):
    """
    Processa pagamento com cartão de crédito para um pedido já existente
    (repagamento via página de detalhe do pedido).
    Recebe encrypted_card via POST e chama criar_ordem_cartao().
    """
    from apps.pedidos.models import Pedido, HistoricoPedido
    from apps.pagamentos.services.pagseguro import criar_ordem_cartao, status_interno, mensagem_recusa

    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'erro': 'Método não permitido.'}, status=405)

    try:
        pedido = Pedido.objects.get(numero=pedido_numero)
    except Pedido.DoesNotExist:
        return JsonResponse({'status': 'erro', 'erro': 'Pedido não encontrado.'}, status=404)

    if not _pode_acessar_pedido(request, pedido):
        return JsonResponse({'status': 'erro', 'erro': 'Não autorizado.'}, status=403)

    if pedido.status != 'aguardando_pagamento':
        return JsonResponse({'status': 'erro', 'erro': 'Este pedido não está aguardando pagamento.'})

    encrypted_card = request.POST.get('pagseguro_card_encrypted', '').strip()
    parcelas = int(request.POST.get('parcelas', 1) or 1)

    if not encrypted_card:
        return JsonResponse({'status': 'erro', 'erro': 'Dados do cartão não recebidos.'})

    try:
        resultado = criar_ordem_cartao(pedido, encrypted_card, parcelas)
    except Exception as exc:
        logger.error('cartao_pagar_pedido: erro ao criar ordem %s: %s', pedido_numero, exc)
        return JsonResponse({'status': 'erro', 'erro': 'Erro ao processar pagamento. Tente novamente.'})

    charges = resultado.get('charges', [])
    if not charges:
        return JsonResponse({'status': 'erro', 'erro': 'Resposta inválida do gateway.'})

    charge        = charges[0]
    charge_status = (charge.get('status') or '').upper()
    novo_status   = status_interno(charge_status)

    if novo_status and pedido.status != novo_status:
        status_anterior = pedido.status
        pedido.status   = novo_status
        pedido.gateway  = 'pagseguro'
        charge_id = charge.get('id', '')
        if charge_id and not pedido.gateway_id:
            pedido.gateway_id = charge_id
        pedido.save(update_fields=['status', 'gateway', 'gateway_id'])
        HistoricoPedido.objects.create(
            pedido=pedido,
            status_anterior=status_anterior,
            status_novo=novo_status,
            observacao=f'Cartão PagSeguro: charge {charge_id} → {charge_status}',
        )

    if charge_status in ('PAID', 'AUTHORIZED'):
        return JsonResponse({'status': 'ok', 'redirect': f'/conta/pedido/{pedido_numero}/'})

    if charge_status == 'DECLINED':
        return JsonResponse({'status': 'recusado', 'erro': mensagem_recusa(charge)})

    # IN_ANALYSIS ou WAITING — aguarda webhook
    return JsonResponse({'status': 'analise', 'mensagem': 'Pagamento em análise. Você será notificado por e-mail.'})


@require_GET
def pix_gerar(request, pedido_numero):
    """
    Gera ou regenera o QR Code Pix para um pedido.
    Tenta criar via PagBank API (webhook automático) e faz fallback para QR estático.
    Retorna JSON com payload (texto) e qrcode (base64).
    """
    from django.conf import settings
    from apps.pedidos.models import Pedido

    try:
        pedido = Pedido.objects.get(numero=pedido_numero)
    except Pedido.DoesNotExist:
        return JsonResponse({'status': 'erro', 'erro': 'Pedido não encontrado.'}, status=404)

    if not _pode_acessar_pedido(request, pedido):
        return JsonResponse({'status': 'erro', 'erro': 'Não autorizado.'}, status=403)

    # ── Tentativa 1: PagBank PIX API (gera QR dinâmico com webhook) ──────────
    try:
        from apps.pagamentos.services.pagseguro import criar_ordem_pix
        from .pix import gerar_qrcode_base64

        resposta = criar_ordem_pix(pedido)
        qr_codes = resposta.get('qr_codes', [])
        order_id = resposta.get('id', '')

        if qr_codes and order_id:
            pix_text = qr_codes[0].get('text', '')
            if pix_text:
                qrcode_b64 = gerar_qrcode_base64(pix_text)
                # Salva o order_id do PagBank para rastreamento do webhook
                if order_id and pedido.gateway_id != order_id:
                    pedido.gateway    = 'pagseguro'
                    pedido.gateway_id = order_id
                    pedido.save(update_fields=['gateway', 'gateway_id'])
                return JsonResponse({
                    'status':  'ok',
                    'payload': pix_text,
                    'qrcode':  qrcode_b64,
                    'valor':   str(pedido.total),
                    'numero':  pedido_numero,
                    'via':     'pagseguro',
                })
    except Exception as exc:
        logger.warning('PIX PagBank falhou para pedido %s, usando QR estático: %s', pedido_numero, exc)

    # ── Fallback: QR estático com chave PIX cadastrada no .env ───────────────
    chave_pix = getattr(settings, 'PIX_CHAVE', '')
    if not chave_pix:
        return JsonResponse({
            'status':   'sem_chave',
            'mensagem': 'Chave Pix não configurada.',
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
            'numero':  pedido_numero,
            'via':     'estatico',
        })
    except Exception as e:
        logger.error('Erro ao gerar Pix estático %s: %s', pedido_numero, e, exc_info=True)
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
