"""
Views da integração Bling:
  /bling/autorizar/  → redireciona para OAuth do Bling (staff only)
  /bling/callback/   → recebe o code e troca por token
  /bling/webhook/    → recebe notificações do Bling (pedidos, NF-e)
"""

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render

from . import oauth as bling_oauth

logger = logging.getLogger(__name__)


# ── OAuth2 ────────────────────────────────────────────────────────────────────

@staff_member_required
def oauth_autorizar(request):
    """
    Inicia o fluxo OAuth2: redireciona o usuário para o Bling autorizar o app.
    Acessível apenas por staff via /bling/autorizar/.
    """
    redirect_uri = settings.BLING_REDIRECT_URI
    url = bling_oauth.get_authorize_url(redirect_uri)
    return HttpResponseRedirect(url)


@require_GET
def oauth_callback(request):
    """
    Recebe o callback do Bling com o authorization code.
    Troca o code por access_token e salva no banco.
    """
    code  = request.GET.get('code')
    error = request.GET.get('error')

    if error or not code:
        descricao = request.GET.get('error_description', error or 'Código não recebido.')
        logger.error('Bling OAuth callback erro: %s', descricao)
        return render(request, 'admin/bling_status.html', {
            'sucesso': False,
            'mensagem': f'Autorização recusada: {descricao}',
        })

    try:
        token = bling_oauth.exchange_code(code, settings.BLING_REDIRECT_URI)
        logger.info('Bling OAuth: token obtido com sucesso, expira em %s', token.expira_em)
        return render(request, 'admin/bling_status.html', {
            'sucesso': True,
            'mensagem': f'Integração Bling autorizada com sucesso! Token expira em {token.expira_em.strftime("%d/%m/%Y %H:%M")}.',
        })
    except Exception as exc:
        logger.error('Bling OAuth exchange_code falhou: %s', exc)
        return render(request, 'admin/bling_status.html', {
            'sucesso': False,
            'mensagem': f'Erro ao obter token: {exc}',
        })


# ── Webhook ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def webhook(request):
    """
    Recebe notificações de eventos do Bling (pedidos, NF-e).
    Configurar no painel Bling → Integrações → Webhooks.
    URL: https://seudominio.com.br/bling/webhook/
    """
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    estrutura = payload.get('estrutura', '')
    data      = payload.get('data', {})

    logger.info('Bling webhook recebido: estrutura=%s id=%s', estrutura, data.get('id'))

    if estrutura == 'pedidoVenda':
        _processar_webhook_pedido(data)
    elif estrutura == 'notaFiscal':
        _processar_webhook_nfe(data)

    # Bling espera 200 para confirmar recebimento
    return HttpResponse(status=200)


def _processar_webhook_pedido(data: dict):
    """Atualiza rastreio / situação do pedido quando o Bling notifica mudança."""
    from apps.pedidos.models import Pedido, HistoricoPedido

    bling_id = str(data.get('id', ''))
    if not bling_id:
        return

    try:
        pedido = Pedido.objects.get(bling_pedido_id=bling_id)
    except Pedido.DoesNotExist:
        logger.warning('Bling webhook: pedido com bling_id=%s não encontrado', bling_id)
        return

    # Atualiza código de rastreio se disponível
    rastreio = (
        data.get('transporte', {}).get('codigoRastreamento')
        or data.get('codigoRastreamento', '')
    )
    if rastreio and rastreio != pedido.codigo_rastreio:
        pedido.codigo_rastreio = rastreio
        pedido.save(update_fields=['codigo_rastreio', 'atualizado_em'])
        logger.info('Pedido %s: rastreio atualizado → %s', pedido.numero, rastreio)

    # Mapeia situação do Bling → status interno
    situacao_id = data.get('situacao', {}).get('id')
    _MAPA_SITUACAO = {
        9:  'pagamento_confirmado',
        11: 'em_separacao',
        10: 'enviado',
        7:  'entregue',
        12: 'cancelado',
    }
    novo_status = _MAPA_SITUACAO.get(situacao_id)
    if novo_status and novo_status != pedido.status:
        HistoricoPedido.objects.create(
            pedido=pedido,
            status_anterior=pedido.status,
            status_novo=novo_status,
            observacao=f'Atualizado pelo webhook Bling (situacao={situacao_id})',
        )
        pedido.status = novo_status
        pedido.save(update_fields=['status', 'atualizado_em'])
        logger.info('Pedido %s: status atualizado → %s (Bling situacao=%s)',
                    pedido.numero, novo_status, situacao_id)


def _processar_webhook_nfe(data: dict):
    """Salva o ID e chave da NF-e quando o Bling confirma emissão."""
    from apps.pedidos.models import Pedido

    nfe_id    = str(data.get('id', ''))
    chave     = data.get('chaveAcesso', '')
    numero_nf = str(data.get('numero', ''))

    # O Bling envia o pedido de venda associado dentro da NF-e
    bling_pedido_id = str(
        data.get('pedidoVenda', {}).get('id', '')
        or data.get('pedidoCompra', {}).get('id', '')
        or ''
    )
    if not bling_pedido_id:
        return

    try:
        pedido = Pedido.objects.get(bling_pedido_id=bling_pedido_id)
    except Pedido.DoesNotExist:
        return

    if nfe_id and not pedido.bling_nfe_id:
        pedido.bling_nfe_id = nfe_id
        pedido.nfe_chave    = chave or ''
        pedido.save(update_fields=['bling_nfe_id', 'nfe_chave', 'atualizado_em'])
        logger.info('NF-e %s (chave=%s) salva no pedido %s', nfe_id, chave, pedido.numero)
