import hashlib
import json

from django.db import models as _models


# Fragmentos de User-Agent que identificam bots, crawlers, scrapers e monitores.
# Sem este filtro, todo acesso de robo (que chega sem utm_source) era contado
# como sessao "Direto / Outros", inflando o trafego organico e o contador "ao
# vivo" de forma irreal -- especialmente acessos desktop, sinal classico de
# trafego nao-humano num e-commerce de moda mobile-first.
_BOT_UA_FRAGMENTS = (
    'bot', 'crawl', 'spider', 'slurp', 'mediapartners', 'adsbot',
    'facebookexternalhit', 'facebot', 'ia_archiver', 'archive.org',
    'semrush', 'ahrefs', 'mj12', 'dotbot', 'petalbot', 'yandex',
    'baidu', 'sogou', 'exabot', 'bingpreview', 'duckduck', 'applebot',
    'pinterest', 'telegrambot', 'whatsapp', 'discord', 'twitterbot',
    'linkedinbot', 'embedly', 'python-requests', 'python-httpx',
    'aiohttp', 'curl/', 'wget', 'go-http-client', 'java/', 'okhttp',
    'libwww', 'httpclient', 'headless', 'phantomjs', 'puppeteer',
    'playwright', 'scrapy', 'lighthouse', 'gtmetrix', 'pingdom',
    'uptimerobot', 'statuscake', 'datadog', 'newrelic', 'node-fetch',
    'axios', 'guzzlehttp',
)


def eh_bot(ua: str) -> bool:
    """True se o User-Agent for de bot/crawler/scraper. UA vazio = trata como bot
    (navegador legitimo sempre envia User-Agent)."""
    if not ua:
        return True
    ua_lower = ua.lower()
    return any(frag in ua_lower for frag in _BOT_UA_FRAGMENTS)


def _detectar_dispositivo(ua: str) -> str:
    ua_lower = ua.lower()
    if 'tablet' in ua_lower or 'ipad' in ua_lower:
        return 'tablet'
    if 'mobile' in ua_lower or 'android' in ua_lower or 'iphone' in ua_lower:
        return 'mobile'
    return 'desktop'


# Limites de cada campo de atribuicao (espelham o max_length do model SessaoAnalytics)
_LIMITES_UTM = {
    'utm_source':   200,
    'utm_medium':   200,
    'utm_campaign': 200,
    'utm_content':  200,
    'utm_term':     200,
    'gclid':        300,
    'fbclid':       300,
}


def _utms_do_cookie(cookie_raw: str) -> dict:
    """Le UTMs do cookie della_attr, mesmo formato de _ler_utms_atribuicao."""
    try:
        from urllib.parse import unquote_plus
        dados = json.loads(unquote_plus(cookie_raw))
        return {
            campo: str(dados.get(campo, ''))[:limite]
            for campo, limite in _LIMITES_UTM.items()
        }
    except Exception:
        return {}


def utms_da_url(get_params) -> dict:
    """Le UTMs/click ids direto da query string da requisicao de entrada.

    A UTM da URL chega ja na primeira requisicao (o clique no anuncio), antes do
    JS gravar o cookie della_attr. Por isso e a fonte mais confiavel para atribuir
    o trafego pago. Aceita request.GET (QueryDict) ou qualquer mapping.
    """
    utms = {}
    try:
        for campo, limite in _LIMITES_UTM.items():
            valor = get_params.get(campo)
            if valor:
                utms[campo] = str(valor)[:limite]
    except Exception:
        return {}
    return utms


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
            url_utms=utms_da_url(request.GET),
        )
    except Exception:
        return None


def obter_ou_criar_sessao_por_valores(session_key: str, ua: str, cookie_attr: str,
                                      url_utms: dict | None = None):
    """Versao thread-safe: aceita primitivos em vez do objeto request."""
    try:
        return _get_or_create_por_valores(session_key, ua, cookie_attr, url_utms)
    except Exception:
        return None


def _get_or_create_por_valores(session_key: str, ua: str, cookie_attr: str,
                               url_utms: dict | None = None):
    from apps.analytics.models import SessaoAnalytics

    if not session_key:
        return None

    # Filtro de bots no ponto unico de criacao de sessao: cobre TODOS os caminhos
    # (middleware pagina_vista, produto_visualizado na PDP, eventos de carrinho e
    # o endpoint AJAX). Sem isso, um bot bloqueado no middleware ainda criava
    # sessao via produto_visualizado -- aparecendo no "ao vivo" sem pagina_vista
    # (por isso o contador subia mas nenhuma pagina era listada).
    if eh_bot(ua):
        return None

    sessao_hash = hashlib.sha256(session_key.encode()).hexdigest()
    # A UTM da URL tem prioridade sobre o cookie: o cookie della_attr so e gravado
    # pelo JS a partir da 2a pagina, enquanto a URL ja traz a atribuicao no clique
    # de entrada do anuncio.
    utms = _utms_do_cookie(cookie_attr)
    for campo, valor in (url_utms or {}).items():
        if valor:
            utms[campo] = valor

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
        campos_update = {
            'total_paginas':  _models.F('total_paginas') + 1,
            'ultima_acao_em': _models.functions.Now(),
        }
        # Backfill de atribuicao: se a sessao foi criada sem UTM (1a pagina, antes
        # do cookie/JS) e agora chegou uma utm_source, preenche os campos vazios.
        # Nunca sobrescreve atribuicao ja registrada (first-touch preservado).
        if not sessao.utm_source and utms.get('utm_source'):
            for campo in _LIMITES_UTM:
                if utms.get(campo):
                    campos_update[campo] = utms[campo]
        SessaoAnalytics.objects.filter(pk=sessao.pk).update(**campos_update)

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
