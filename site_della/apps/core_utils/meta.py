import hashlib
import json
import logging
import time
import uuid
from urllib.parse import unquote

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

CONSENT_COOKIE_NAME = 'della_consent'


def gerar_evento_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex}'


def marketing_consent_granted(request) -> bool:
    raw = request.COOKIES.get(CONSENT_COOKIE_NAME, '')
    if not raw:
        return False
    try:
        data = json.loads(unquote(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return bool(data.get('marketing'))


def enviar_evento_meta(
    request,
    *,
    event_name: str,
    event_id: str,
    custom_data: dict,
    event_source_url: str,
    dados_cliente: dict | None = None,
    event_time: int | None = None,
    marketing_consent: bool | None = None,
) -> bool:
    pixel_id = getattr(settings, 'META_PIXEL_ID', '') or ''
    access_token = getattr(settings, 'META_CONVERSIONS_API_TOKEN', '') or ''

    if not pixel_id or not access_token:
        return False

    # Consentimento: quando vem de um request (cliente no site), le o cookie.
    # Quando disparado server-side (ex: webhook de pagamento, sem browser),
    # usa o consentimento persistido no pedido, passado em marketing_consent.
    consentido = (
        marketing_consent
        if marketing_consent is not None
        else marketing_consent_granted(request)
    )
    if not consentido:
        logger.info('Meta CAPI: envio ignorado (%s) por falta de consentimento.', event_id)
        return False

    endpoint = (
        f'https://graph.facebook.com/'
        f'{getattr(settings, "META_GRAPH_API_VERSION", "v19.0")}/{pixel_id}/events'
    )
    payload = {
        'data': [
            {
                'event_name': event_name,
                'event_time': event_time or (int(request.headers.get('X-Request-Start', '0') or 0) if request else 0) or None,
                'event_id': event_id,
                'action_source': 'website',
                'event_source_url': event_source_url,
                'user_data': _build_user_data(request, dados_cliente=dados_cliente),
                'custom_data': custom_data,
            }
        ]
    }
    if not payload['data'][0]['event_time']:
        payload['data'][0]['event_time'] = int(time.time())
    test_event_code = getattr(settings, 'META_CONVERSIONS_TEST_EVENT_CODE', '') or ''
    if test_event_code:
        payload['test_event_code'] = test_event_code

    try:
        response = requests.post(
            endpoint,
            params={'access_token': access_token},
            json=payload,
            timeout=5,
        )
        response.raise_for_status()
        logger.info('Meta CAPI: %s enviado com sucesso (%s).', event_name, event_id)
        return True
    except requests.RequestException as exc:
        detalhe = ''
        if getattr(exc, 'response', None) is not None:
            detalhe = exc.response.text[:600]
        logger.warning(
            'Meta CAPI: falha ao enviar %s (%s): %s %s',
            event_name,
            event_id,
            exc,
            detalhe,
        )
        return False


def enviar_evento_purchase(pedido, request=None) -> bool:
    items = list(pedido.itens.select_related('produto').all())
    caminho = f'/carrinho/confirmacao/{pedido.numero}/'
    if request is not None:
        event_source_url = request.build_absolute_uri(caminho)
        marketing_consent = None  # le do cookie do request
    else:
        # Disparo server-side (webhook de pagamento): sem browser, usa SITE_URL
        # e o consentimento de marketing persistido no pedido no checkout.
        event_source_url = f'{settings.SITE_URL.rstrip("/")}{caminho}'
        marketing_consent = bool(getattr(pedido, 'consentimento_marketing', False))
    return enviar_evento_meta(
        request,
        event_name='Purchase',
        event_id=f'purchase_{pedido.numero}',
        event_time=int(pedido.criado_em.timestamp()),
        event_source_url=event_source_url,
        marketing_consent=marketing_consent,
        dados_cliente={
            'nome_completo': pedido.nome_completo,
            'email': pedido.email,
            'telefone': pedido.telefone,
            'cpf': pedido.cpf,
            'cidade': pedido.cidade,
            'estado': pedido.estado,
            'cep': pedido.cep_entrega,
            'external_id': str(pedido.cliente_id or pedido.numero),
        },
        custom_data={
            'currency': 'BRL',
            'value': float(pedido.total),
            'order_id': pedido.numero,
            'content_type': 'product',
            'content_ids': [str(item.produto_id) for item in items],
            'contents': [
                {
                    'id': str(item.produto_id),
                    'quantity': item.quantidade,
                    'item_price': float(item.preco_unitario),
                }
                for item in items
            ],
            'num_items': sum(item.quantidade for item in items),
        },
    )


def _build_user_data(request, dados_cliente: dict | None = None) -> dict:
    dados_cliente = dados_cliente or {}
    usuario = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    nome = (dados_cliente.get('nome_completo') or (usuario.get_full_name() if usuario else '') or '').strip()
    first_name, last_name = _split_name(nome)
    # Sem request (disparo server-side), nao ha IP/User-Agent/cookies do browser.
    # A correspondencia segue forte pelos dados hasheados do pedido (em, ph, etc).
    user_data = {}
    if request is not None:
        user_data['client_ip_address'] = _client_ip(request)
        user_data['client_user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:1000]

    email_raw = (
        dados_cliente.get('email')
        or (getattr(usuario, 'email', '') if usuario else '')
        or ''
    )
    telefone_raw = (
        dados_cliente.get('telefone')
        or (getattr(usuario, 'telefone', '') if usuario else '')
        or ''
    )
    cpf_raw = (
        dados_cliente.get('cpf')
        or (getattr(usuario, 'cpf', '') if usuario else '')
        or ''
    )
    cidade_raw = dados_cliente.get('cidade') or ''
    estado_raw = dados_cliente.get('estado') or ''
    cep_raw = dados_cliente.get('cep') or ''
    # Enriquece a correspondência: para usuário logado sem dados de endereço
    # explícitos, usa o endereço principal cadastrado (cidade/estado/CEP).
    if usuario and not (cidade_raw and estado_raw and cep_raw):
        endereco = _endereco_principal_usuario(usuario)
        cidade_raw = cidade_raw or endereco.get('cidade', '')
        estado_raw = estado_raw or endereco.get('estado', '')
        cep_raw = cep_raw or endereco.get('cep', '')
    external_id_raw = dados_cliente.get('external_id') or (str(usuario.pk) if usuario else '')

    email = _sha256(email_raw.strip().lower())
    telefone = _sha256(_normalize_phone(telefone_raw))
    cpf = _sha256(_digits_only(cpf_raw))
    first_name_hash = _sha256(first_name.lower())
    last_name_hash = _sha256(last_name.lower())
    city = _sha256(cidade_raw.strip().lower())
    state = _sha256(estado_raw.strip().lower())
    zip_code = _sha256(_digits_only(cep_raw))
    country = _sha256('br')
    external_id = _sha256(str(external_id_raw))

    if email:
        user_data['em'] = [email]
    if telefone:
        user_data['ph'] = [telefone]
    if cpf:
        user_data['external_id'] = cpf
    elif external_id:
        user_data['external_id'] = external_id
    if first_name_hash:
        user_data['fn'] = [first_name_hash]
    if last_name_hash:
        user_data['ln'] = [last_name_hash]
    if city:
        user_data['ct'] = [city]
    if state:
        user_data['st'] = [state]
    if zip_code:
        user_data['zp'] = [zip_code]
    if country:
        user_data['country'] = [country]

    if request is not None:
        fbp = request.COOKIES.get('_fbp', '').strip()
        fbc = request.COOKIES.get('_fbc', '').strip()
        if not fbc:
            fbclid = request.GET.get('fbclid', '').strip()
            if fbclid:
                fbc = f'fb.1.{int(time.time() * 1000)}.{fbclid}'
        if fbp:
            user_data['fbp'] = fbp
        if fbc:
            user_data['fbc'] = fbc

    return user_data


def _endereco_principal_usuario(usuario) -> dict:
    """Cidade/estado/CEP do endereço principal do usuário logado (enriquece o CAPI).

    Falha silenciosa: se não houver endereço ou a relação não existir, retorna {}.
    """
    try:
        endereco = usuario.enderecos.order_by('-principal', '-criado_em').first()
    except Exception:
        return {}
    if not endereco:
        return {}
    return {
        'cidade': getattr(endereco, 'cidade', '') or '',
        'estado': getattr(endereco, 'estado', '') or '',
        'cep': getattr(endereco, 'cep', '') or '',
    }


def _client_ip(request) -> str:
    forwarded = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()
    return (request.META.get('REMOTE_ADDR') or '').strip()


def _split_name(nome: str) -> tuple[str, str]:
    partes = [p for p in nome.split() if p]
    if not partes:
        return '', ''
    if len(partes) == 1:
        return partes[0], partes[0]
    return partes[0], partes[-1]


def _digits_only(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def _normalize_phone(value: str) -> str:
    digits = _digits_only(value).lstrip('0')
    if not digits:
        return ''
    if len(digits) in (10, 11) and not digits.startswith('55'):
        return f'55{digits}'
    return digits


def _sha256(value: str) -> str:
    normalized = (value or '').strip()
    if not normalized:
        return ''
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# CAPI PageView - sempre ativo (sem gate de consent)
# ---------------------------------------------------------------------------

def preparar_user_data_pageview(request) -> tuple[str, dict]:
    """
    Lê dados do request no thread principal e retorna (url, user_data).
    Sem consent: apenas pais (nao e dado pessoal isolado).
    Com consent: IP, UA, cookies Meta e dados hasheados do usuario logado.
    Nao acessa banco de dados - seguro para chamar em toda requisicao.
    """
    url = request.build_absolute_uri()
    tem_consent = marketing_consent_granted(request)

    if not tem_consent:
        return url, {'country': [_sha256('br')]}

    user_data = {'country': [_sha256('br')]}

    ip = _client_ip(request)
    ua = request.META.get('HTTP_USER_AGENT', '')[:1000]
    if ip:
        user_data['client_ip_address'] = ip
    if ua:
        user_data['client_user_agent'] = ua

    fbp = request.COOKIES.get('_fbp', '').strip()
    fbc = request.COOKIES.get('_fbc', '').strip()
    # Fallback: primeiro clique de anuncio - cookie ainda nao existe, mas fbclid esta na URL
    if not fbc:
        fbclid = request.GET.get('fbclid', '').strip()
        if fbclid:
            fbc = f'fb.1.{int(time.time() * 1000)}.{fbclid}'
    if fbp:
        user_data['fbp'] = fbp
    if fbc:
        user_data['fbc'] = fbc

    # Dados do usuario autenticado ja estao em memoria (AuthMiddleware)
    # Nao faz query no banco aqui.
    usuario = (
        request.user
        if getattr(request, 'user', None) and request.user.is_authenticated
        else None
    )
    if usuario:
        email_raw = (getattr(usuario, 'email', '') or '').strip().lower()
        phone_raw = getattr(usuario, 'telefone', '') or ''
        cpf_raw   = getattr(usuario, 'cpf', '') or ''
        nome_raw  = (usuario.get_full_name() or '').strip()
        fn_raw, ln_raw = _split_name(nome_raw)

        em  = _sha256(email_raw)
        ph  = _sha256(_normalize_phone(phone_raw))
        cpf = _sha256(_digits_only(cpf_raw))
        ext = cpf or _sha256(str(usuario.pk))

        if em:
            user_data['em'] = [em]
        if ph:
            user_data['ph'] = [ph]
        if ext:
            user_data['external_id'] = ext
        if fn_raw:
            user_data['fn'] = [_sha256(fn_raw.lower())]
        if ln_raw:
            user_data['ln'] = [_sha256(ln_raw.lower())]

    return url, user_data


def enviar_capi_pageview(*, url: str, user_data: dict) -> bool:
    """
    Envia PageView para a CAPI Meta.
    Nao acessa o objeto request - pode ser chamado em thread daemon.
    """
    pixel_id     = getattr(settings, 'META_PIXEL_ID', '') or ''
    access_token = getattr(settings, 'META_CONVERSIONS_API_TOKEN', '') or ''
    if not pixel_id or not access_token:
        return False

    endpoint = (
        f'https://graph.facebook.com/'
        f'{getattr(settings, "META_GRAPH_API_VERSION", "v19.0")}/{pixel_id}/events'
    )
    event_id = gerar_evento_id('pageview')
    payload = {
        'data': [{
            'event_name':       'PageView',
            'event_time':       int(time.time()),
            'event_id':         event_id,
            'action_source':    'website',
            'event_source_url': url,
            'user_data':        user_data,
        }]
    }
    test_event_code = getattr(settings, 'META_CONVERSIONS_TEST_EVENT_CODE', '') or ''
    if test_event_code:
        payload['test_event_code'] = test_event_code

    try:
        resp = requests.post(
            endpoint,
            params={'access_token': access_token},
            json=payload,
            timeout=5,
        )
        resp.raise_for_status()
        logger.debug('Meta CAPI PageView enviado (%s).', event_id)
        return True
    except requests.RequestException as exc:
        logger.warning('Meta CAPI PageView: falha (%s): %s', event_id, exc)
        return False
