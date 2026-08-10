import hashlib
import json
import logging

from django.conf import settings
from django.db import models as _models
from django.utils import timezone

logger = logging.getLogger('apps.analytics')

_geoip_reader = None
_geoip_tentado = False


def _obter_geoip_reader():
    """Reader do GeoLite2-City, carregado uma vez por processo (worker).

    Nunca levanta excecao: se o banco nao existe (ainda nao rodou
    sincronizar_geoip) retorna None e a cidade fica vazia -- resto do
    tracking continua funcionando normalmente."""
    global _geoip_reader, _geoip_tentado
    if _geoip_tentado:
        return _geoip_reader
    _geoip_tentado = True
    try:
        import geoip2.database
        if settings.GEOIP_DB_PATH.exists():
            _geoip_reader = geoip2.database.Reader(str(settings.GEOIP_DB_PATH))
    except Exception:
        _geoip_reader = None
    return _geoip_reader


def _resolver_geo(ip: str) -> tuple[str, str]:
    """(cidade, estado) aproximados a partir do IP via GeoLite2. Nunca guarda
    o IP -- so o resultado da consulta, feita em memoria neste processo."""
    if not ip:
        return '', ''
    reader = _obter_geoip_reader()
    if not reader:
        return '', ''
    try:
        resp = reader.city(ip)
        cidade = (resp.city.name or '')[:100]
        estado = (resp.subdivisions.most_specific.iso_code or '')[:2]
        return cidade, estado
    except Exception:
        # IP local/privado, reservado, nao encontrado na base etc.
        return '', ''


_geoip_asn_reader = None
_geoip_asn_tentado = False

# Trechos do nome da organizacao (GeoLite2-ASN) que identificam datacenter,
# hosting ou VPN comercial -- nenhum cliente real de loja de roupa navega a
# partir dessas redes. Calibrado apos o incidente de 2026-07-10 (253 sessoes
# em 1h vindas de Council Bluffs/IA -- regiao de datacenter do Google Cloud --
# usando 121 IPs diferentes, 1-2 sessoes cada, especificamente para nao bater
# no limite de rajada por IP).
TRECHOS_ASN_DATACENTER = (
    'GOOGLE', 'AMAZON', 'MICROSOFT', 'AZURE', 'OVH', 'DIGITALOCEAN',
    'DIGITAL OCEAN', 'HETZNER', 'LINODE', 'AKAMAI', 'ALIBABA', 'TENCENT',
    'ORACLE', 'VULTR', 'SCALEWAY', 'LEASEWEB', 'CONTABO', 'M247', 'DATACAMP',
    'CHOOPA', 'PSYCHZ', 'HOSTINGER', 'CLOUDFLARE', 'FASTLY', 'HOSTWINDS',
    'HOSTPAPA', 'IONOS', 'RACKSPACE', 'UPCLOUD', 'CLOUDVPS', 'SERVERS.COM',
    'HOSTING', 'CLOUD', 'DATACENTER', 'DATA CENTER', 'VPN', 'PROXY',
    'COLOCATION',
    # Provedores pequenos/regionais confirmados como scraper em 2026-08-10:
    # "Roma" e "Amsterda" simultaneos no ao-vivo eram o MESMO scraper (AS51747,
    # UA identico, sessoes abertas no mesmo segundo em 2 paises). Nenhum
    # ficava na lista acima -- nome nao tem "hosting"/"cloud" no meio.
    'INTERNET VIKINGS', 'HOST BALTIC', 'HOSTGNOME', 'TECHOFF', 'BUCKLOG',
    'INFRALY', 'XTOM', 'CLOUVIDER', 'ZENLAYER', 'NFORCE', 'FRANTECH',
    'FLOKINET', 'WORLDSTREAM', 'SERVERIUS', 'STARK INDUSTRIES', 'IPXO',
    'PACKETHUB', 'GTHOST', 'RYMAN NETWORKS', 'GLOBAL CONNECTIVITY',
)


def _obter_geoip_asn_reader():
    """Reader do GeoLite2-ASN, carregado uma vez por processo (worker).

    Nunca levanta excecao: se o banco nao existe (ainda nao rodou
    sincronizar_geoip) retorna None e a checagem de datacenter fica
    desligada -- resto do tracking continua funcionando normalmente."""
    global _geoip_asn_reader, _geoip_asn_tentado
    if _geoip_asn_tentado:
        return _geoip_asn_reader
    _geoip_asn_tentado = True
    try:
        import geoip2.database
        if settings.GEOIP_ASN_DB_PATH.exists():
            _geoip_asn_reader = geoip2.database.Reader(str(settings.GEOIP_ASN_DB_PATH))
    except Exception:
        _geoip_asn_reader = None
    return _geoip_asn_reader


def _eh_ip_datacenter(ip: str) -> bool:
    """True se o IP pertence a rede de datacenter/hosting/VPN conhecida
    (GeoLite2-ASN). Nunca guarda o IP -- so o resultado da consulta."""
    if not ip:
        return False
    reader = _obter_geoip_asn_reader()
    if not reader:
        return False
    try:
        org = (reader.asn(ip).autonomous_system_organization or '').upper()
        return any(trecho in org for trecho in TRECHOS_ASN_DATACENTER)
    except Exception:
        return False


# Limiares de deteccao comportamental de bot (UA falsificado de navegador).
# - PAGINAS: nenhum humano ve tantas paginas numa unica sessao numa loja de moda.
# - RAJADA_IP: N sessoes do mesmo IP criadas dentro de RAJADA_JANELA segundos =
#   farm de bot rotacionando sessao. Valores calibrados sobre o trafego real
#   (scrapers reais bateram 100+ paginas; rajada observada foi de 37 sessoes/min).
# Subido de 50 para 100 em 2026-07-10: uma cliente real (mobile, navegacao
# rapida por multiplas categorias) gerou ~55-60 eventos numa janela de 19min
# e foi marcada como bot por engano (pedido 2026-0010, compra real confirmada
# 1,5 dia depois). 100 ainda fica abaixo do patamar observado em scrapers reais.
LIMIAR_PAGINAS_BOT = 100
LIMIAR_RAJADA_IP   = 6
RAJADA_JANELA_SEG  = 90
# Janela usada para confirmar se o volume de paginas veio de uma rajada real
# (scraper) e nao de alguem que retorna com o mesmo cookie ao longo de dias
# (SESSION_COOKIE_AGE = 30 dias). Sem essa janela, qualquer sessao de retorno
# frequente (ex: a propria equipe testando o site) acaba marcada como bot para
# sempre so por acumular 50+ toques ao longo do tempo, nao numa rajada.
JANELA_BOT_MINUTOS = 30

# Rajada GLOBAL (site inteiro, nao por IP): scraper distribuido usando muitos
# IPs diferentes (1-2 sessoes cada) nunca bate o limite por IP individual.
# Calibrado sobre 10 dias de trafego real: pico organico observado foi de 18
# sessoes/5min (2026-07-06 10:52); o incidente de 2026-07-10 teve 246
# sessoes/5min. 25 fica acima do pico organico e bem abaixo dos incidentes
# ja observados (25-250+).
LIMIAR_RAJADA_GLOBAL = 25
RAJADA_GLOBAL_JANELA_SEG = 300


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


def extrair_ip(meta) -> str:
    """IP real do visitante. Mesma precedencia do Axes (nginx envia X-Real-IP;
    REMOTE_ADDR aqui e o socket unix do gunicorn). Pega o 1o IP do XFF."""
    try:
        ip = meta.get('HTTP_X_REAL_IP') or ''
        if not ip:
            xff = meta.get('HTTP_X_FORWARDED_FOR') or ''
            ip = xff.split(',')[0] if xff else ''
        if not ip:
            ip = meta.get('REMOTE_ADDR') or ''
        return ip.strip()
    except Exception:
        return ''


def _hash_ip(ip: str) -> str:
    """Hash salgado do IP (pseudonimo). Nunca guardamos o IP em texto."""
    if not ip:
        return ''
    return hashlib.sha256(f'{settings.SECRET_KEY}|{ip}'.encode()).hexdigest()


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
            ip=extrair_ip(request.META),
        )
    except Exception:
        logger.exception('Falha ao obter/criar sessao (obter_ou_criar_sessao)')
        return None


def obter_ou_criar_sessao_por_valores(session_key: str, ua: str, cookie_attr: str,
                                      url_utms: dict | None = None, ip: str = ''):
    """Versao thread-safe: aceita primitivos em vez do objeto request."""
    try:
        return _get_or_create_por_valores(session_key, ua, cookie_attr, url_utms, ip)
    except Exception:
        logger.exception('Falha ao obter/criar sessao (obter_ou_criar_sessao_por_valores)')
        return None


def _ip_em_rajada(ip_hash: str) -> bool:
    """True se este IP criou muitas sessoes na ultima janela (farm de bot)."""
    if not ip_hash:
        return False
    from apps.analytics.models import SessaoAnalytics
    desde = timezone.now() - timezone.timedelta(seconds=RAJADA_JANELA_SEG)
    recentes = SessaoAnalytics.objects.filter(ip_hash=ip_hash, iniciada_em__gte=desde)
    if recentes.count() >= LIMIAR_RAJADA_IP - 1:
        # Marca tambem as irmas ja gravadas dessa rajada (corrige retroativo).
        recentes.filter(is_bot=False).update(is_bot=True)
        return True
    return False


def _rajada_global() -> bool:
    """True se o SITE INTEIRO recebeu volume anormal de sessoes novas na
    janela recente -- sinal de scraper distribuido usando muitos IPs
    diferentes (1-2 sessoes cada), que nunca bate o limiar de _ip_em_rajada
    por ser por-IP. Ver incidente 2026-07-10 (253 sessoes/1h, 121 IPs
    distintos, quase todos de datacenter)."""
    from apps.analytics.models import SessaoAnalytics
    desde = timezone.now() - timezone.timedelta(seconds=RAJADA_GLOBAL_JANELA_SEG)
    recentes = SessaoAnalytics.objects.filter(iniciada_em__gte=desde)
    if recentes.count() >= LIMIAR_RAJADA_GLOBAL - 1:
        # Marca tambem as irmas ja gravadas dessa rajada (corrige retroativo).
        recentes.filter(is_bot=False).update(is_bot=True)
        return True
    return False


def _paginas_em_rajada(sessao) -> bool:
    """True se o volume de paginas da sessao veio de uma rajada recente
    (scraper real), nao acumulado aos poucos ao longo de dias com o mesmo
    cookie (ex: alguem que volta a testar o site com o mesmo navegador)."""
    from apps.analytics.models import EventoAnalytics
    desde = timezone.now() - timezone.timedelta(minutes=JANELA_BOT_MINUTOS)
    recentes = EventoAnalytics.objects.filter(sessao=sessao, ocorrido_em__gte=desde).count()
    return (recentes + 1) >= LIMIAR_PAGINAS_BOT


def _get_or_create_por_valores(session_key: str, ua: str, cookie_attr: str,
                               url_utms: dict | None = None, ip: str = ''):
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
    ip_hash = _hash_ip(ip)
    # A UTM da URL tem prioridade sobre o cookie: o cookie della_attr so e gravado
    # pelo JS a partir da 2a pagina, enquanto a URL ja traz a atribuicao no clique
    # de entrada do anuncio.
    utms = _utms_do_cookie(cookie_attr)
    for campo, valor in (url_utms or {}).items():
        if valor:
            utms[campo] = valor

    # Resolvida so na criacao (cidade nao muda durante a sessao) e so a partir
    # do IP em memoria -- o IP em si nunca e persistido, so cidade/estado.
    cidade, estado = _resolver_geo(ip)

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
            'ip_hash':       ip_hash,
            'cidade':        cidade,
            'estado':        estado,
            # Datacenter/hosting/VPN (ASN), rajada do mesmo IP, ou rajada
            # global (muitos IPs diferentes, 1-2 sessoes cada) = bot.
            'is_bot':        _eh_ip_datacenter(ip) or _ip_em_rajada(ip_hash) or _rajada_global(),
        },
    )

    if not criada:
        campos_update = {
            'total_paginas':  _models.F('total_paginas') + 1,
            'ultima_acao_em': _models.functions.Now(),
        }
        # Volume anormal de paginas EM POUCO TEMPO = scraper (UA falsificado).
        # Usa total_paginas so como gatilho barato (evita checar toda vez); a
        # decisao real usa a janela de tempo, pra nao punir sessao de retorno
        # frequente que so acumulou o total aos poucos ao longo de dias.
        if not sessao.is_bot and (sessao.total_paginas + 1) >= LIMIAR_PAGINAS_BOT:
            if _paginas_em_rajada(sessao):
                campos_update['is_bot'] = True
        # Preenche o ip_hash se a sessao foi criada antes (ex: sem IP no 1o hit).
        if ip_hash and not sessao.ip_hash:
            campos_update['ip_hash'] = ip_hash
        # Backfill de cidade/estado: sessoes de cookie longevo criadas antes do
        # GeoLite2 estar disponivel (ou com IP nao resolvivel no 1o hit) ficavam
        # para sempre sem cidade -- por isso nunca apareciam no bloco "Cidades
        # dos visitantes" do Ao Vivo mesmo com paginas recentes.
        if not sessao.cidade and cidade:
            campos_update['cidade'] = cidade
            campos_update['estado'] = estado
        # Backfill de atribuicao: se a sessao foi criada sem UTM (1a pagina, antes
        # do cookie/JS) e agora chegou uma utm_source, preenche os campos vazios.
        # Nunca sobrescreve atribuicao ja registrada (first-touch preservado).
        if not sessao.utm_source and utms.get('utm_source'):
            for campo in _LIMITES_UTM:
                if utms.get(campo):
                    campos_update[campo] = utms[campo]
        SessaoAnalytics.objects.filter(pk=sessao.pk).update(**campos_update)

    return sessao


def migrar_sessao_analytics(old_session_key: str, new_session_key: str):
    """Preserva a continuidade do funil quando o Django troca o session_key.

    `django.contrib.auth.login()` chama `request.session.cycle_key()`, que gera
    uma chave nova mas mantem os dados da sessao (carrinho etc). Sem isso, a
    SessaoAnalytics amarrada ao hash da chave antiga ficava orfa: eventos como
    produto_adicionado registrados antes do login/cadastro deixavam de aparecer
    ligados ao pedido feito depois (era o caso do pedido 0008, investigado em
    2026-07-08). Renomear o sessao_hash preserva o mesmo registro e seus
    eventos -- nao duplica nem copia nada.
    """
    if not old_session_key or not new_session_key or old_session_key == new_session_key:
        return
    try:
        from apps.analytics.models import SessaoAnalytics
        novo_hash = hashlib.sha256(new_session_key.encode()).hexdigest()
        # A chave nova acabou de ser gerada pelo cycle_key(), entao nunca ja existe
        # uma SessaoAnalytics para ela -- update() e seguro, sem risco de colisao.
        antigo_hash = hashlib.sha256(old_session_key.encode()).hexdigest()
        SessaoAnalytics.objects.filter(sessao_hash=antigo_hash).update(sessao_hash=novo_hash)
    except Exception:
        logger.exception('Falha ao migrar sessao de analytics no login')


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
