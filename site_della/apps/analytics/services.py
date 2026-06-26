import hashlib
import json

from django.db import models as _models


def _detectar_dispositivo(ua: str) -> str:
    ua_lower = ua.lower()
    if 'tablet' in ua_lower or 'ipad' in ua_lower:
        return 'tablet'
    if 'mobile' in ua_lower or 'android' in ua_lower or 'iphone' in ua_lower:
        return 'mobile'
    return 'desktop'


def _utms_do_cookie(cookie_raw: str) -> dict:
    """Le UTMs do cookie della_attr, mesmo formato de _ler_utms_atribuicao."""
    try:
        from urllib.parse import unquote_plus
        dados = json.loads(unquote_plus(cookie_raw))
        return {
            'utm_source':   str(dados.get('utm_source',   ''))[:200],
            'utm_medium':   str(dados.get('utm_medium',   ''))[:200],
            'utm_campaign': str(dados.get('utm_campaign', ''))[:200],
            'utm_content':  str(dados.get('utm_content',  ''))[:200],
            'utm_term':     str(dados.get('utm_term',     ''))[:200],
            'gclid':        str(dados.get('gclid',        ''))[:300],
            'fbclid':       str(dados.get('fbclid',       ''))[:300],
        }
    except Exception:
        return {}


def obter_ou_criar_sessao(request):
    """Retorna ou cria SessaoAnalytics para a sessao Django atual.

    Nunca levanta excecoes -- retorna None em caso de falha.
    """
    try:
        if not request.session.session_key:
            request.session.save()
        return _get_or_create_por_valores(
            session_key=request.session.session_key or '',
            ua=request.META.get('HTTP_USER_AGENT', ''),
            cookie_attr=request.COOKIES.get('della_attr', ''),
        )
    except Exception:
        return None


def obter_ou_criar_sessao_por_valores(session_key: str, ua: str, cookie_attr: str):
    """Versao thread-safe: aceita primitivos em vez do objeto request."""
    try:
        return _get_or_create_por_valores(session_key, ua, cookie_attr)
    except Exception:
        return None


def _get_or_create_por_valores(session_key: str, ua: str, cookie_attr: str):
    from apps.analytics.models import SessaoAnalytics

    if not session_key:
        return None

    sessao_hash = hashlib.sha256(session_key.encode()).hexdigest()
    utms = _utms_do_cookie(cookie_attr)

    sessao, criada = SessaoAnalytics.objects.get_or_create(
        sessao_hash=sessao_hash,
        defaults={
            'dispositivo':  _detectar_dispositivo(ua),
            'utm_source':   utms.get('utm_source',   ''),
            'utm_medium':   utms.get('utm_medium',   ''),
            'utm_campaign': utms.get('utm_campaign', ''),
            'utm_content':  utms.get('utm_content',  ''),
            'utm_term':     utms.get('utm_term',     ''),
            'gclid':        utms.get('gclid',        ''),
            'fbclid':       utms.get('fbclid',       ''),
            'total_paginas': 1,
        },
    )

    if not criada:
        SessaoAnalytics.objects.filter(pk=sessao.pk).update(
            total_paginas=_models.F('total_paginas') + 1,
            ultima_acao_em=_models.functions.Now(),
        )

    return sessao


def registrar_evento(sessao, tipo: str, **kwargs):
    """Cria EventoAnalytics. Nunca levanta excecoes."""
    try:
        from apps.analytics.models import EventoAnalytics, TIPOS_VALIDOS
        if sessao is None or tipo not in TIPOS_VALIDOS:
            return None
        # Remove campos que nao existem no model para evitar TypeError
        campos_validos = {
            'pagina_url', 'produto_slug', 'produto_nome', 'categoria_nome',
            'variacao_desc', 'quantidade', 'valor_unitario', 'valor_total',
            'pedido_numero', 'forma_pagamento', 'busca_termo',
            'busca_resultados', 'metodo', 'cupom_codigo',
        }
        dados = {k: v for k, v in kwargs.items() if k in campos_validos}
        return EventoAnalytics.objects.create(sessao=sessao, tipo=tipo, **dados)
    except Exception:
        return None
