"""
Views da integração Bling:
  /bling/autorizar/  → redireciona para OAuth do Bling (staff only)
  /bling/callback/   → recebe o code e troca por token
  /bling/webhook/    → recebe notificações do Bling (pedidos, NF-e)
"""

import hashlib
import hmac
import json
import logging
import secrets

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render

from . import oauth as bling_oauth

_BLING_STATE_SESSION_KEY = 'bling_oauth_state'

logger = logging.getLogger(__name__)


# ── OAuth2 ────────────────────────────────────────────────────────────────────

@staff_member_required
def oauth_autorizar(request):
    """
    Inicia o fluxo OAuth2: redireciona o usuário para o Bling autorizar o app.
    Acessível apenas por staff via /bling/autorizar/.

    Gera um state aleatório e guarda na sessão para validação no callback
    (proteção contra OAuth CSRF / code injection).
    """
    state = secrets.token_urlsafe(32)
    request.session[_BLING_STATE_SESSION_KEY] = state

    redirect_uri = settings.BLING_REDIRECT_URI
    url = bling_oauth.get_authorize_url(redirect_uri, state=state)
    return HttpResponseRedirect(url)


@staff_member_required
@require_GET
def oauth_callback(request):
    """
    Recebe o callback do Bling com o authorization code.
    Troca o code por access_token e salva no banco.

    Exige que o state da URL bata com o state gerado em oauth_autorizar
    (guardado na sessão). Sem esse match, rejeita o callback.
    """
    code  = request.GET.get('code')
    error = request.GET.get('error')
    state_recebido = request.GET.get('state', '')
    state_esperado = request.session.pop(_BLING_STATE_SESSION_KEY, None)

    if not state_esperado or not secrets.compare_digest(state_recebido, state_esperado):
        logger.warning(
            'Bling OAuth callback: state inválido (recebido=%r, esperado=%r)',
            state_recebido, bool(state_esperado),
        )
        return render(request, 'admin/bling_status.html', {
            'sucesso': False,
            'mensagem': 'Autorização recusada: state inválido. Refaça o fluxo em /bling/autorizar/.',
        })

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


# ── Refresh manual do token ──────────────────────────────────────────────────

@staff_member_required
def token_refresh_manual(request):
    """
    Faz refresh manual do access_token usando o refresh_token salvo.
    Chamado pelo botão "Atualizar Token" no admin de Tokens Bling.

    O access_token expira em ~1 hora (comportamento normal do Bling).
    O sistema faz refresh automático ao fazer chamadas à API.
    Use este botão apenas para verificar se o refresh_token ainda é válido.
    """
    from .models import BlingToken
    token = BlingToken.objects.order_by('-criado_em').first()
    if not token:
        messages.error(request, 'Nenhum token encontrado. Autorize a integração primeiro.')
        return redirect('/painel/bling/blingtoken/')

    try:
        novo_token = bling_oauth.refresh_token(token)
        messages.success(
            request,
            f'Token atualizado com sucesso! Novo access_token válido até '
            f'{novo_token.expira_em.strftime("%d/%m/%Y às %H:%M")}.',
        )
    except Exception as exc:
        messages.error(
            request,
            f'Falha ao atualizar o token: {exc}. '
            f'O refresh_token pode ter expirado (válido por 30 dias). '
            f'Acesse /bling/autorizar/ para re-autorizar.',
        )
    return redirect('/painel/bling/blingtoken/')


# ── Webhook ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def webhook(request):
    """
    Recebe notificações de eventos do Bling v3 (estoque, pedidos, NF-e).
    Cadastrar o servidor no app OAuth em https://developer.bling.com.br/aplicativos
    → aba Webhooks → URL: https://seudominio.com.br/bling/webhook/

    Validação de origem (doc oficial Bling v3):
      • Header:     X-Bling-Signature-256
      • Formato:    "sha256=<hex>"
      • Algoritmo:  HMAC-SHA256
      • Chave:      o próprio BLING_CLIENT_SECRET do app OAuth (não é segredo
                    separado — o Bling v3 assina com o client_secret).
    Requests sem assinatura válida são rejeitados com 401.
    """
    client_secret = getattr(settings, 'BLING_CLIENT_SECRET', '')
    if client_secret:
        header = request.headers.get('X-Bling-Signature-256', '')
        # O header sempre chega como "sha256=<hex>" — remove o prefixo.
        assinatura_recebida = header[7:] if header.startswith('sha256=') else header
        mac_esperado = hmac.new(
            client_secret.encode('utf-8'), request.body, hashlib.sha256
        ).hexdigest()
        if not (assinatura_recebida and hmac.compare_digest(assinatura_recebida, mac_esperado)):
            logger.warning(
                'Bling webhook: assinatura X-Bling-Signature-256 inválida — rejeitado '
                '(recebida=%r)',
                header[:24] + '…' if header else '(vazia)',
            )
            return HttpResponse(status=401)
    else:
        logger.warning(
            'Bling webhook: BLING_CLIENT_SECRET ausente — validação HMAC desativada.'
        )

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

    # Status do site só é alterado quando o Bling cancela o pedido. Outras transições
    # (Em andamento → Atendido) refletem etapas internas do Bling (NF, etiqueta) que
    # não significam que o cliente já recebeu — o controle de "Enviado" é feito
    # pelo operador no admin após postar nos Correios. Usamos `situacao.valor`
    # (categoria padrão Bling: 0=Em aberto, 1=Atendido, 2=Cancelado, 3=Em andamento)
    # em vez de IDs específicos para funcionar com qualquer situação custom da loja.
    valor = data.get('situacao', {}).get('valor')
    situacao_id = data.get('situacao', {}).get('id')
    if valor == 2 and pedido.status != 'cancelado':
        HistoricoPedido.objects.create(
            pedido=pedido,
            status_anterior=pedido.status,
            status_novo='cancelado',
            observacao=f'Cancelado pelo webhook Bling (situacao_id={situacao_id})',
        )
        pedido.status = 'cancelado'
        pedido.save(update_fields=['status', 'atualizado_em'])
        logger.info('Pedido %s cancelado pelo webhook Bling (situacao_id=%s)',
                    pedido.numero, situacao_id)
        try:
            from apps.bling.services import restaurar_estoque_pedido
            restaurar_estoque_pedido(pedido)
        except Exception as exc:
            logger.warning('Estoque: falha ao restaurar pedido %s após cancelamento Bling: %s',
                           pedido.numero, exc)


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
