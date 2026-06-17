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
    Recebe notificações de eventos do Bling. Suporta v1 e v3.

    **Webhook v3** (`estrutura` no root do payload):
      • Validação HMAC-SHA256 obrigatória via header `X-Bling-Signature-256`
      • Chave: `BLING_CLIENT_SECRET`
      • Estruturas: `pedidoVenda`, `notaFiscal`, `estoque`

    **Webhook v1** (formato PLANO no root: `eventId`, `event`, `data`, `version`):
      • Bling v1 envia o header `X-Bling-Signature-256` mas NÃO validamos por
        enquanto — ações são idempotentes e não destrutivas (apenas re-sincroniza
        estoque via `consultar_estoque_produto`, fonte da verdade)
      • Eventos disparam handlers: `order.*` → pedido, `stock.*` → estoque
      • Compatibilidade extra: também aceita formato aninhado `{event: {...}}`
        (visto em logs internos do suporte Bling, não em webhook real)
    """
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    # ── Detecção de versão ────────────────────────────────────────────────
    estrutura_v3 = payload.get('estrutura', '')

    # Bling v1 envia o webhook em formato PLANO (eventId, event, data, version no root).
    # O suporte às vezes mostra logs internos aninhados em `{event: {...}}` — aceitar
    # ambos por segurança.
    event_v1 = None
    if isinstance(payload.get('event'), dict):
        # Formato aninhado (raro / log interno)
        event_v1 = payload['event']
    elif payload.get('version') == 'v1' or payload.get('eventId'):
        # Formato plano (real)
        event_v1 = payload

    if estrutura_v3:
        # v3 — exige HMAC válido
        client_secret = getattr(settings, 'BLING_CLIENT_SECRET', '')
        if client_secret:
            header = request.headers.get('X-Bling-Signature-256', '')
            assinatura_recebida = header[7:] if header.startswith('sha256=') else header
            mac_esperado = hmac.new(
                client_secret.encode('utf-8'), request.body, hashlib.sha256
            ).hexdigest()
            if not (assinatura_recebida and hmac.compare_digest(assinatura_recebida, mac_esperado)):
                logger.warning(
                    'Bling webhook v3: assinatura inválida — rejeitado (recebida=%r)',
                    header[:24] + '…' if header else '(vazia)',
                )
                return HttpResponse(status=401)

        data = payload.get('data', {})
        logger.info('Bling webhook v3: estrutura=%s id=%s', estrutura_v3, data.get('id'))

        if estrutura_v3 == 'pedidoVenda':
            _processar_webhook_pedido(data)
        elif estrutura_v3 == 'notaFiscal':
            _processar_webhook_nfe(data)
        elif estrutura_v3 == 'estoque':
            _processar_webhook_estoque(data)

    elif event_v1:
        # Valida HMAC-SHA256 igual ao v3 — mesmo header, mesma chave
        client_secret = getattr(settings, 'BLING_CLIENT_SECRET', '')
        if client_secret:
            header = request.headers.get('X-Bling-Signature-256', '')
            assinatura_recebida = header[7:] if header.startswith('sha256=') else header
            mac_esperado = hmac.new(
                client_secret.encode('utf-8'), request.body, hashlib.sha256
            ).hexdigest()
            if not (assinatura_recebida and hmac.compare_digest(assinatura_recebida, mac_esperado)):
                logger.warning(
                    'Bling webhook v1: assinatura inválida — rejeitado (recebida=%r)',
                    header[:24] + '…' if header else '(vazia)',
                )
                return HttpResponse(status=401)

        evento_tipo = event_v1.get('event', '')
        data = event_v1.get('data', {}) or {}
        logger.info(
            'Bling webhook v1: evento=%s eventId=%s data.id=%s',
            evento_tipo, event_v1.get('eventId'), data.get('id'),
        )

        if evento_tipo.startswith('order.'):
            _processar_webhook_pedido_v1(data, evento_tipo)
        elif evento_tipo.startswith('stock.'):
            _processar_webhook_estoque_v1(data, evento_tipo)
    else:
        logger.info(
            'Bling webhook: payload sem `estrutura` (v3) nem `event` (v1) — ignorado. '
            'Body preview: %s',
            request.body[:200].decode('utf-8', errors='replace'),
        )

    # Bling espera 200 para confirmar recebimento
    return HttpResponse(status=200)


def _extrair_rastreio_transporte(transporte: dict) -> str:
    """Extrai código de rastreio do objeto transporte do Bling.

    O código pode estar em:
    - transporte.codigoRastreamento (campo legado)
    - transporte.volumes[].codigoRastreamento (formato atual — um código por volume)
    """
    rastreio = transporte.get('codigoRastreamento', '') or ''
    if not rastreio:
        for vol in transporte.get('volumes', []):
            cod = vol.get('codigoRastreamento', '') or ''
            if cod:
                rastreio = cod
                break
    return rastreio


def _processar_webhook_pedido(data: dict):
    """Atualiza rastreio / situação do pedido quando o Bling notifica mudança."""
    from apps.pedidos.models import Pedido, HistoricoPedido

    bling_id = str(data.get('id', ''))
    if not bling_id:
        return

    try:
        pedido = Pedido.objects.get(bling_pedido_id=bling_id)
    except Pedido.DoesNotExist:
        # Pedido não é do site (ex: venda física na loja). Disparar sync de estoque
        # dos produtos envolvidos para refletir a reserva em tempo real.
        _sincronizar_estoque_webhook_pedido_fisico(data, bling_id)
        return

    # Atualiza código de rastreio se disponível.
    # O Bling armazena o código em transporte.volumes[].codigoRastreamento (não no root).
    # Além disso, o payload do webhook pode não incluir os volumes — buscamos via GET.
    rastreio = _extrair_rastreio_transporte(data.get('transporte', {}))
    if not rastreio and not pedido.codigo_rastreio:
        try:
            from apps.bling.api import BlingAPI
            api = BlingAPI()
            resp = api.consultar_pedido_venda(bling_id, retry=False)
            rastreio = _extrair_rastreio_transporte(resp.get('data', {}).get('transporte', {}))
            if rastreio:
                logger.info('Pedido %s: rastreio obtido via GET Bling → %s', pedido.numero, rastreio)
        except Exception as exc:
            logger.warning('Pedido %s: falha ao consultar rastreio na API Bling: %s', pedido.numero, exc)
    if rastreio and rastreio != pedido.codigo_rastreio:
        pedido.codigo_rastreio = rastreio
        pedido.save(update_fields=['codigo_rastreio', 'atualizado_em'])
        logger.info('Pedido %s: rastreio atualizado → %s', pedido.numero, rastreio)

    # Transicoes de status via webhook Bling.
    # valor=1 (Atendido): NF emitida no Bling, pedido pronto para separar.
    # valor=2 (Cancelado): cancela o pedido no site.
    # Outros valores (0=Em aberto, 3=Em andamento) nao alteram o status.
    valor = data.get('situacao', {}).get('valor')
    situacao_id = data.get('situacao', {}).get('id')

    if valor == 1 and pedido.status == 'pagamento_confirmado':
        HistoricoPedido.objects.create(
            pedido=pedido,
            status_anterior='pagamento_confirmado',
            status_novo='em_separacao',
            observacao=f'NF emitida no Bling (situacao_id={situacao_id}) — pedido em separacao.',
        )
        pedido.status = 'em_separacao'
        pedido.save(update_fields=['status', 'atualizado_em'])
        logger.info('Pedido %s: pagamento_confirmado → em_separacao via webhook Bling (situacao_id=%s)',
                    pedido.numero, situacao_id)

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
        try:
            from apps.pedidos.emails import enviar_cancelamento
            enviar_cancelamento(pedido, estornado=False)
        except Exception as exc:
            logger.warning('E-mail: falha ao enviar cancelamento do pedido %s: %s',
                           pedido.numero, exc)


def _sincronizar_estoque_webhook_pedido_fisico(data: dict, bling_id: str):
    """
    Chamado quando o webhook traz um pedidoVenda que não existe no site (loja física).

    Extrai os SKUs dos itens e dispara sync de estoque apenas para variações
    com usa_sync_bling=True que correspondam a esses SKUs. Isso garante
    atualização em tempo real quando uma vendedora registra um pedido no Bling.
    """
    from apps.produtos.models import Variacao

    itens = data.get('itens') or []
    skus = [
        str(item.get('codigo') or item.get('descricao', '')).strip()
        for item in itens
        if item.get('codigo')
    ]

    if not skus:
        logger.info(
            'Bling webhook: pedido físico %s sem SKUs identificáveis — sync ignorado', bling_id
        )
        return

    variacoes = Variacao.objects.filter(
        sku_variacao__in=skus, usa_sync_bling=True, ativa=True,
    )
    if not variacoes.exists():
        logger.info(
            'Bling webhook: pedido físico %s — nenhuma variação com sync ativo para SKUs %s',
            bling_id, skus,
        )
        return

    try:
        from apps.bling.services import sincronizar_estoque_bling
        resultado = sincronizar_estoque_bling(variacoes, usar_retry=False)
        logger.info(
            'Bling webhook: sync estoque pós-pedido físico %s — %s',
            bling_id, resultado,
        )
    except Exception as exc:
        logger.warning(
            'Bling webhook: sync estoque pós-pedido físico %s falhou: %s', bling_id, exc
        )


def _processar_webhook_estoque(data: dict):
    """
    Webhook `estrutura=estoque` — disparado pelo Bling em qualquer mudança de saldo
    (pedido reservado/cancelado, ajuste manual, transferência, devolução, NF entrada).

    Filtros:
      • Só processa se a mudança for no depósito Show Room (BLING_DEPOSITO_ID).
      • Só sincroniza variações com `usa_sync_bling=True`.

    O payload Bling pode trazer `produto.id` ou `idProduto` dependendo do evento; usamos
    o id do produto/variação como chave (=`Variacao.bling_variacao_id`) e disparamos o
    sync via API — fonte da verdade continua sendo `consultar_estoque_produto`, evitando
    confiar em payloads parciais do webhook.
    """
    from apps.produtos.models import Variacao

    deposito_alvo = str(getattr(settings, 'BLING_DEPOSITO_ID', '') or '').strip()
    deposito_evento = str(
        (data.get('deposito') or {}).get('id', '')
        or data.get('idDeposito', '')
        or ''
    ).strip()

    if deposito_alvo and deposito_evento and deposito_evento != deposito_alvo:
        logger.debug(
            'Bling webhook estoque: depósito %s ignorado (alvo=%s)',
            deposito_evento, deposito_alvo,
        )
        return

    produto_id = str(
        (data.get('produto') or {}).get('id', '')
        or data.get('idProduto', '')
        or data.get('id', '')
        or ''
    ).strip()
    if not produto_id:
        logger.info('Bling webhook estoque: sem produto.id no payload — ignorado')
        return

    variacoes = Variacao.objects.filter(
        bling_variacao_id=produto_id, usa_sync_bling=True, ativa=True,
    )
    if not variacoes.exists():
        logger.debug(
            'Bling webhook estoque: produto %s sem variação com sync ativo', produto_id
        )
        return

    try:
        from apps.bling.services import sincronizar_estoque_bling
        resultado = sincronizar_estoque_bling(variacoes, usar_retry=False)
        logger.info(
            'Bling webhook estoque: produto %s (depósito %s) — %s',
            produto_id, deposito_evento or '?', resultado,
        )
    except Exception as exc:
        logger.warning(
            'Bling webhook estoque: produto %s falhou: %s', produto_id, exc
        )


def _processar_webhook_pedido_v1(data: dict, evento: str):
    """
    Webhook v1 `order.created/updated/deleted` — estrutura mínima sem `itens`.

    Para pedidos do site (bling_pedido_id encontrado): atualiza rastreio/cancela.
    Para pedidos físicos (não encontrados): apenas loga e retorna. O payload v1
    nao traz itens (impossivel filtrar SKUs) e o sync generico bloqueia o worker
    Gunicorn por mais de 60s (time.sleep no rate limit da API). O cron horario
    (0 * * * *) faz o sync completo como rede de segurança.
    """
    from apps.pedidos.models import Pedido, HistoricoPedido

    bling_id = str(data.get('id', ''))
    if not bling_id:
        return

    try:
        pedido = Pedido.objects.get(bling_pedido_id=bling_id)
    except Pedido.DoesNotExist:
        # Pedido fisico — sem itens no v1, sync delegado ao cron horario
        logger.info(
            'Bling webhook v1 %s: pedido fisico %s — sem itens, sync delegado ao cron',
            evento, bling_id,
        )
        return

    # Pedido do site: cancelamento via situacao.valor=2
    situacao_valor = (data.get('situacao') or {}).get('valor')
    if situacao_valor == 2 and pedido.status != 'cancelado':
        status_anterior = pedido.status
        pedido.status = 'cancelado'
        pedido.save(update_fields=['status', 'atualizado_em'])
        HistoricoPedido.objects.create(
            pedido=pedido,
            status_anterior=status_anterior,
            status_novo='cancelado',
            observacao=f'Cancelado pelo webhook Bling v1 ({evento})',
        )
        logger.info('Pedido %s cancelado via webhook v1 (%s)', pedido.numero, evento)
        try:
            from apps.bling.services import restaurar_estoque_pedido
            restaurar_estoque_pedido(pedido)
        except Exception as exc:
            logger.warning('Estoque: falha ao restaurar pedido %s após cancelamento Bling v1: %s',
                           pedido.numero, exc)
        try:
            from apps.pedidos.emails import enviar_cancelamento
            enviar_cancelamento(pedido, estornado=False)
        except Exception as exc:
            logger.warning('E-mail: falha ao enviar cancelamento do pedido %s: %s',
                           pedido.numero, exc)


def _processar_webhook_estoque_v1(data: dict, evento: str):
    """
    Webhook v1 `stock.created/updated/deleted` — formato exato do payload ainda
    a confirmar. Tentamos extrair `produto.id` / `idProduto` / `id` e disparar
    sync. Se não encontrar produto identificável, cai em sync genérico.
    """
    from apps.produtos.models import Variacao

    deposito_alvo = str(getattr(settings, 'BLING_DEPOSITO_ID', '') or '').strip()
    deposito_evento = str(
        (data.get('deposito') or {}).get('id', '')
        or data.get('idDeposito', '')
        or ''
    ).strip()

    if deposito_alvo and deposito_evento and deposito_evento != deposito_alvo:
        return

    produto_id = str(
        (data.get('produto') or {}).get('id', '')
        or data.get('idProduto', '')
        or data.get('id', '')
        or ''
    ).strip()

    from apps.bling.services import sincronizar_estoque_bling
    try:
        if produto_id:
            variacoes = Variacao.objects.filter(
                bling_variacao_id=produto_id, usa_sync_bling=True, ativa=True,
            )
            if variacoes.exists():
                resultado = sincronizar_estoque_bling(variacoes, usar_retry=False)
                logger.info(
                    'Bling webhook v1 %s: produto %s (%s)', evento, produto_id, resultado
                )
                return
            logger.info(
                'Bling webhook v1 %s: produto %s sem variacao com sync ativo, ignorado (cron horario cobre).',
                evento, produto_id,
            )
            return
        logger.info(
            'Bling webhook v1 %s: payload sem produto_id, ignorado (cron horario cobre).',
            evento,
        )
    except Exception as exc:
        logger.warning('Bling webhook v1 %s falhou: %s', evento, exc)


def _processar_webhook_nfe(data: dict):
    """Salva o ID e chave da NF-e quando o Bling confirma emissão."""
    from apps.pedidos.models import Pedido

    nfe_id = str(data.get('id', ''))
    chave  = data.get('chaveAcesso', '')

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
