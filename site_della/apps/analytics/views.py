import json
import logging
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

from apps.analytics.models import TIPOS_VALIDOS

_CAMPOS_PERMITIDOS = {
    'pagina_url', 'produto_slug', 'produto_nome', 'categoria_nome',
    'variacao_desc', 'quantidade', 'valor_unitario', 'valor_total',
    'pedido_numero', 'forma_pagamento', 'busca_termo',
    'busca_resultados', 'metodo', 'cupom_codigo',
}


@csrf_protect
@require_POST
def registrar_evento_ajax(request):
    """Endpoint para eventos client-side (ex: pagamento_selecionado).

    CSRF protegido. Retorna 204 No Content em caso de sucesso.
    """
    try:
        dados = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    tipo = dados.get('tipo', '')
    if tipo not in TIPOS_VALIDOS:
        return HttpResponse(status=400)

    try:
        from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
        sessao = obter_ou_criar_sessao(request)
        if sessao:
            kwargs = {k: v for k, v in dados.items() if k in _CAMPOS_PERMITIDOS}
            registrar_evento(sessao, tipo, **kwargs)
    except Exception:
        pass

    return HttpResponse(status=204)


@csrf_protect
@require_POST
def capturar_email_popup(request):
    """Captura email do popup de exit-intent, cria CarrinhoAbandonado e emite cupom 5%."""
    try:
        data  = json.loads(request.body)
        email = (data.get('email') or '').strip().lower()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'erro': 'Dados invalidos.'}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'ok': False, 'erro': 'E-mail invalido.'}, status=400)

    from apps.pedidos.carrinho import Carrinho
    cart = Carrinho(request)
    if len(cart) == 0:
        return JsonResponse({'ok': False, 'erro': 'Carrinho vazio.'}, status=400)

    # Salvar snapshot do carrinho
    try:
        from apps.pedidos.views import _salvar_carrinho_abandonado_guest
        _salvar_carrinho_abandonado_guest(request, cart, email)
    except Exception as exc:
        logger.warning('Popup: erro ao salvar carrinho abandonado para %s: %s', email, exc)

    # Gerar cupom com protecao anti-abuso
    codigo = _gerar_cupom_carrinho_popup(email, request.user if request.user.is_authenticated else None)

    return JsonResponse({'ok': True, 'codigo': codigo})


def _gerar_cupom_carrinho_popup(email, cliente=None):
    from apps.pedidos.models import Cupom, CupomEmitido
    from apps.pedidos.emails import enviar_email_cupom_carrinho_popup

    template = (
        Cupom.objects
        .filter(origem='carrinho_popup', ativo=True)
        .order_by('-id')
        .first()
    )
    if not template or not template.dias_validade_pos_emissao:
        logger.warning('Popup: nenhum template Cupom carrinho_popup ativo encontrado.')
        return None

    # Anti-abuso: maximo 2 emissoes por email em 30 dias
    limite_30d = timezone.now() - timedelta(days=30)
    emissoes_recentes = CupomEmitido.objects.filter(
        email__iexact=email,
        cupom_template__origem='carrinho_popup',
        emitido_em__gte=limite_30d,
    ).count()
    if emissoes_recentes >= 2:
        logger.info('Popup: email %s atingiu limite de 2 emissoes em 30 dias.', email)
        return None

    # Idempotente: reutiliza cupom ainda valido (nao usado, nao expirado)
    emitido = (
        CupomEmitido.objects
        .filter(email__iexact=email, cupom_template=template, usado_em__isnull=True)
        .order_by('-emitido_em')
        .first()
    )
    if emitido and not emitido.esta_expirado:
        return emitido.codigo

    cupom = CupomEmitido.objects.create(
        cupom_template=template,
        email=email,
        cliente=cliente,
    )
    try:
        enviar_email_cupom_carrinho_popup(cupom)
    except Exception as exc:
        logger.warning('Popup: erro ao enviar e-mail de cupom para %s: %s', email, exc)

    return cupom.codigo
